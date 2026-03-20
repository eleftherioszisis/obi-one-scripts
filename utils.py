import os
import json
from datetime import datetime, UTC
from typing import Literal

import httpx
from entitysdk import ProjectContext
from rich import print


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


def get_project_context(
    subdomain: Literal["cell_a", "cell_b"], environment
) -> ProjectContext:
    return {
        "cell_a": ProjectContext(
            virtual_lab_id="594fd60d-7a38-436f-939d-500feaa13bba",
            project_id="54aa306a-b7db-4087-82ec-c6dec1617df4",
            environment=environment,
        ),
        "cell_b": ProjectContext(
            virtual_lab_id="47280b42-f521-4343-adda-8a2aef504f0c",
            project_id="afa210d1-ed66-429f-b0b4-3df85e667f4d",
            environment=environment,
        ),
    }[subdomain]


def get_obi_one_client(project_context, environment) -> httpx.Client:
    token = os.environ["ACCESS_TOKEN"]
    headers = {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": str(project_context.virtual_lab_id),
        "project-id": str(project_context.project_id),
    }
    base_url = {
        "local": "http://127.0.0.1:8100",
        "staging": "https://staging.cell-a.openbraininstitute.org/api/obi-one",
    }[environment]

    http_client = httpx.Client(base_url=base_url, headers=headers)
    return OBIClient(http_client)


def get_launch_system_client(project_context, environment) -> httpx.Client:
    token = os.environ["ACCESS_TOKEN"]
    base_url = {
        "local": "http://127.0.0.1:8001",
        "staging": "https://staging.cell-a.openbraininstitute.org/api/launch-system/",
    }[environment]
    http_client = httpx.Client(
        base_url=base_url, headers={"Authorization": f"Bearer {token}"}
    )
    return LaunchClient(http_client)


def run_cloud_task(*, task_type: str, config_id: str, subdomain: str, environment: str):
    access_token = os.environ["ACCESS_TOKEN"]

    project_context = get_project_context(subdomain, "staging")

    obi_client = get_obi_one_client(project_context, environment)
    ls_client = get_launch_system_client(project_context, "staging")

    data = obi_client.launch_task(
        task_type=task_type, config_id=config_id
    )

    for dct in ls_client.stream_messages(data["job_id"]):
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
