import os
import json
import shutil
from datetime import datetime, UTC
from typing import Literal

import httpx
import entitysdk
from obi_auth import get_token
from rich import print
from enum import StrEnum, auto


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
    ):

        data = get_vlab_proj(
            subdomain=subdomain,
            deployment=db_deployment,
        )
        self._virtual_lab_id = data["virtual_lab_id"]
        self._project_id = data["project_id"]

        self._token_manager = os.environ["ACCESS_TOKEN"]
        #self._token_manager = get_token(environment=launch_system_deployment)

        self.output_dir = clean_dir_if_exists(output_dir)
        self._task_type = task_type
        self._obi_one_deployment = obi_one_deployment
        self._launch_system_deployment = launch_system_deployment
        self._db_deployment = db_deployment

    @property
    def launch_system_client(self):
        return get_launch_system_client(
            deployment=self._launch_system_deployment,
            token=self._token_manager,
        )

    @property
    def obi_one_client(self):
        return get_obi_one_client(
            virtual_lab_id=self._virtual_lab_id,
            project_id=self._project_id,
            deployment=self._obi_one_deployment,
            token=self._token_manager,
        )

    def get_db_client(self):
        return entitysdk.Client(
            project_context=entitysdk.ProjectContext(
                virtual_lab_id=self._virtual_lab_id,
                project_id=self._project_id,
                environment=self._db_deployment,
            ),
            token_manager=self._token_manager,
            environment=self._db_deployment,
        )

    def run_task(self, *, config_id):
        data = self.obi_one_client.launch_task(task_type=self._task_type, config_id=config_id)


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
    def __init__(self, http_client):
        self._http_client = http_client

    def stream_messages(self, job_id: str):
        with self._http_client.stream(
            "GET",
            f"/job/{job_id}/stream",
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
        }
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
    return OBIClient(http_client)


def get_launch_system_client(deployment, token: str) -> httpx.Client:
    base_url = {
        "local": "http://127.0.0.1:8001",
        "staging": "https://staging.cell-a.openbraininstitute.org/api/launch-system",
    }[deployment]
    http_client = httpx.Client(
        base_url=base_url, headers={"Authorization": f"Bearer {token}"}
    )
    return LaunchClient(http_client)


def run_cloud_task(task_type, config_id, subdomain, environment):

    token = os.environ["ACCESS_TOKEN"]

    data = get_vlab_proj(subdomain, "staging")
    vlab_id = data["virtual_lab_id"]
    proj_id = data["project_id"]

    obi_client = get_obi_one_client(
        virtual_lab_id=vlab_id,
        project_id=proj_id,
        deployment=environment,
        token=token,
    )
    ls_client = get_launch_system_client("staging", token=token)

    data = obi_client.launch_task(task_type=task_type, config_id=config_id)

    ls_client.pprint_messages(data["job_id"])
