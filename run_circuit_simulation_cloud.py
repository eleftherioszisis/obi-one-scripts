import os
import httpx
import logging
import webbrowser
from pathlib import Path
from obi_one.types import TaskType
from entitysdk import models

from utils import RemoteTaskManager

domains = {
    "cell_a": {
        "virtual_lab_id": "84258ff5-114f-4865-9a2d-258575c23909",
        "project_id": "da749e43-9c11-4671-8a05-7e709cc4a97d",
    },
    "cell_b": {
        "virtual_lab_id": "47280b42-f521-4343-adda-8a2aef504f0c",
        "project_id": "afa210d1-ed66-429f-b0b4-3df85e667f4d",
    },
}

# cell_a
#CONFIG_ID = "95817298-631a-4c14-a5a4-f0109a632d0f"
#CONFIG_ID = "24dc0545-d058-4716-ad43-3a588d40a2a1"
CONFIG_ID = "fc19aa7e-6049-49a0-a9ff-cf0fe427e025"

# cell_b
#CONFIG_ID = "3ff3ead5-1b9b-4d61-8175-3a9868f29dcd"

OUTPUT_DIR = Path(__file__).parent / "out/circuit_extraction/cloud"

TOKEN = os.environ["ACCESS_TOKEN"]

"""
http_client = httpx.Client(
    base_url="https://staging.cell-a.openbraininstitute.org/api/auth-manager/v1",
    headers={"Authorization": f"Bearer {TOKEN}"},
)

res = http_client.get("/offline-token").raise_for_status().json()
webbrowser.open(res["data"]["consent_url"])
"""

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_simulation,
        subdomain="cell_a",
        obi_one_deployment="staging",
        launch_system_deployment="staging",
        db_deployment="staging",
    )
    manager.run_task(
        config_id=CONFIG_ID,
        check_mode="job",
        activity_type=models.SimulationExecution,
    )
