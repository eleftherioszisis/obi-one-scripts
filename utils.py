import os
import json
import shutil
import logging
from time import sleep
from functools import partial
from datetime import datetime, UTC
from obi_auth import get_token

import httpx
import entitysdk
from entitysdk.token_manager import TokenManager, TokenFromFunction
from rich import print
from enum import StrEnum, auto

L = logging.getLogger(__name__)

DEFAULT_DOMAINS = {
    "cell_a": {
        "virtual_lab_id": "594fd60d-7a38-436f-939d-500feaa13bba",
        "project_id": "54aa306a-b7db-4087-82ec-c6dec1617df4",
    },
    "cell_b": {
        "virtual_lab_id": "47280b42-f521-4343-adda-8a2aef504f0c",
        "project_id": "afa210d1-ed66-429f-b0b4-3df85e667f4d",
    },
}


def clean_dir_if_exists(path):

    if path.exists():
        shutil.rmtree(path)

    path.mkdir(parents=True)

    return path


class TokenMode(StrEnum):
    access_token_platform = auto()
    access_token_keycloak = auto()


class RemoteTaskManager:
    def __init__(
        self,
        *,
        output_dir,
        task_type,
        subdomain,
        obi_one_deployment,
        launch_system_deployment,
        db_deployment,
        domains=DEFAULT_DOMAINS,
    ):
        data = domains[subdomain]
        self._virtual_lab_id = data["virtual_lab_id"]
        self._project_id = data["project_id"]

        # from the platform, needed for auth-manager dependent services
        # like launch_system / obi_one
        self._token = os.environ["ACCESS_TOKEN"]

        # from obi_auth, for long lasting operations as it refreshes the token
        self._token_manager = TokenFromFunction(
            partial(
                get_token,
                environment=db_deployment,
            ),
        )

        self.output_dir = clean_dir_if_exists(output_dir)
        self._task_type = task_type
        self._obi_one_deployment = obi_one_deployment
        self._launch_system_deployment = launch_system_deployment
        self._db_deployment = db_deployment
        self._domains = domains

    @property
    def obi_one_client(self):
        return get_obi_one_client(
            virtual_lab_id=self._virtual_lab_id,
            project_id=self._project_id,
            deployment=self._obi_one_deployment,
            token=self._token,
        )

    @property
    def launch_system_client(self):
        """Get launch-system client.

        Note: Using token manager because jobs are submitted from obi-one.
        This means that we don't need to pass persistent-token stuff here.
        """
        return get_launch_system_client(
            deployment=self._launch_system_deployment,
            token_manager=self._token_manager,
        )

    @property
    def db_client(self):
        return DBClient(
            project_context=entitysdk.ProjectContext(
                virtual_lab_id=self._virtual_lab_id,
                project_id=self._project_id,
                environment=self._db_deployment,
            ),
            token_manager=self._token_manager,
            environment=self._db_deployment,
        )

    def run_task(self, *, config_id, check_mode: str, **kwargs):
        data = self.obi_one_client.launch_task(
            task_type=self._task_type, config_id=config_id
        )
        L.info("Job succefully submitted: %s", data)
        match check_mode:
            case "stream":
                self.launch_system_client.pprint_messages(data["job_id"])
            case "activity":
                self.db_client.poll_status(
                    activity_id=data["activity_id"],
                    activity_type=kwargs["activity_type"],
                )
            case "job":
                while True:
                    job = self.launch_system_client.get_job(data["job_id"])
                    print(f"STATUS: {job['status']}, LOGS: {job['logs']}")
                    if job["status"] in {"pending", "running"}:
                        sleep(2)


class OBIClient:
    def __init__(self, http_client):
        self._http_client = http_client

    def launch_task(self, task_type: str, config_id: str):
        payload = {"task_type": task_type, "config_id": str(config_id)}
        return (
            self._http_client.post("/declared/task/launch", json=payload, timeout=300.0)
            .raise_for_status()
            .json()
        )


class LaunchClient:
    def __init__(self, http_client, token_manager):
        self._http_client = http_client
        self._token_manager = token_manager

    def _get_token(self):
        return (
            self._token_manager
            if isinstance(self._token_manager, str)
            else self._token_manager.get_token()
        )

    def get_job(self, job_id: str):
        token = self._get_token()
        return (
            self._http_client.get(
                url=f"/job/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            .raise_for_status()
            .json()
        )

    def stream_messages(self, job_id: str):
        token = self._get_token()
        with self._http_client.stream(
            "GET",
            url=f"/job/{job_id}/stream",
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(
                connect=10.0,
                read=None,
                write=10.0,
                pool=60.0,
            ),
        ) as response:
            response.raise_for_status()
            for msg in response.iter_lines():
                dct = json.loads(msg)
                yield dct

    def pprint_messages(self, job_id: str):
        for dct in self.stream_messages(job_id):
            match dct["message_type"]:
                case "stdout":
                    print(f"[white]STDOUT: {dct['stdout']}[/white]")
                case "stderr":
                    print(f"[orange1]STDERR: {dct['stderr']}[/orange1]")
                case "log":
                    msg = f"{dct['level']}:{dct['message']}"
                    match dct["level"]:
                        case "INFO":
                            print(f"[dodger_blue1]{msg}[/dodger_blue1]")
                        case "WARNING":
                            print(f"[yellow]{msg}[/yellow]")
                        case "DEBUG":
                            print(f"[sky_blue1]{msg}[/sky_blue1]")
                        case "ERROR":
                            print(f"[red]{msg}[/red]")
                        case "CRITICAL":
                            print(f"[bold white on red]{msg}[/bold white on red]")
                        case _:
                            print(msg)
                case "status":
                    print(f"[magenta]STATUS: {dct['status']}[/magenta]")
                case _:
                    print(dct)


class DBClient(entitysdk.Client):
    def poll_status(self, activity_id, activity_type):
        while True:
            activity = self.get_entity(entity_type=activity_type, entity_id=activity_id)
            print(f"Status: {activity.status}")
            if activity.status in {"pending", "running"}:
                sleep(2)


def create_activity(
    *,
    client,
    activity_type,
    activity_status: str = "created",  # TODO: Use ActivityStatus when available
    used,
):
    """Creates and registers an activity of the given type."""
    activity = activity_type(
        start_time=datetime.now(UTC),
        used=used,
        status=activity_status,
        authorized_public=False,
    )
    activity = client.register_entity(activity)
    L.info(f"Activity {activity.id} of type '{activity_type.__name__}' created")
    return activity


def get_vlab_proj(subdomain, deployment):
    assert deployment == "staging"
    return {
        "cell_a": {
            "virtual_lab_id": "594fd60d-7a38-436f-939d-500feaa13bba",
            "project_id": "54aa306a-b7db-4087-82ec-c6dec1617df4",
        },
        "cell_b": {
            "virtual_lab_id": "47280b42-f521-4343-adda-8a2aef504f0c",
            "project_id": "afa210d1-ed66-429f-b0b4-3df85e667f4d",
        },
    }[subdomain]


def get_obi_one_client(virtual_lab_id, project_id, deployment, token) -> httpx.Client:
    headers = {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": str(virtual_lab_id),
        "project-id": str(project_id),
    }
    base_url = {
        "local": "http://127.0.0.1:8100",
        "staging": "https://staging.cell-a.openbraininstitute.org/api/obi-one",
    }[deployment]

    http_client = httpx.Client(base_url=base_url, headers=headers)
    L.info(
        "OBI client base_url=%s, vlab_id=%s, proj_id=%s",
        base_url,
        virtual_lab_id,
        project_id,
    )
    return OBIClient(http_client)


def get_launch_system_client(
    deployment, token_manager: str | TokenManager
) -> httpx.Client:
    base_url = {
        "local": "http://127.0.0.1:8001",
        "staging": "https://127.0.0.1:4444/api/launch-system",
    }[deployment]
    http_client = httpx.Client(
        base_url=base_url,
        verify=False,
    )
    L.info("launch-system client base_url=%s", base_url)
    return LaunchClient(http_client=http_client, token_manager=token_manager)


def get_db_client(*, subdomain, token, project_context=None):

    if project_context is None:
        data = get_vlab_proj(subdomain, "staging")
        vlab_id = data["virtual_lab_id"]
        proj_id = data["project_id"]

        project_context = entitysdk.ProjectContext(
            virtual_lab_id=vlab_id, project_id=proj_id, environment="staging"
        )

    L.info("DB client project_context=%s", project_context)
    return DBClient(
        project_context=project_context,
        token_manager=token,
        environment="staging",
    )


def run_cloud_task(
    task_type, config_id, subdomain, environment, check_mode="launch-system"
):

    token = os.environ["ACCESS_TOKEN"]

    data = get_vlab_proj(subdomain, "staging")
    vlab_id = data["virtual_lab_id"]
    proj_id = data["project_id"]

    L.info("vlab-proj: %s", data)

    obi_client = get_obi_one_client(
        virtual_lab_id=vlab_id,
        project_id=proj_id,
        deployment=environment,
        token=token,
    )
    ls_client = get_launch_system_client("staging", token=token)

    data = obi_client.launch_task(task_type=task_type, config_id=config_id)

    L.info("OBI response: %s", data)

    ls_client.pprint_messages(data["job_id"])
