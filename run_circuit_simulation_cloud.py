import os
import httpx
from time import sleep

from utils import get_obi_one_client, get_launch_system_client

# cell_a
VLAB_ID = "84258ff5-114f-4865-9a2d-258575c23909"
PROJ_ID = "da749e43-9c11-4671-8a05-7e709cc4a97d"

CONFIG_ID = "95817298-631a-4c14-a5a4-f0109a632d0f"

# cell_b
#VLAB_ID = "47280b42-f521-4343-adda-8a2aef504f0c"
#PROJ_ID = "afa210d1-ed66-429f-b0b4-3df85e667f4d"

#CONFIG_ID = "3ff3ead5-1b9b-4d61-8175-3a9868f29dcd"


TOKEN = os.environ["ACCESS_TOKEN"]

"""
http_client = httpx.Client(base_url="https://staging.cell-a.openbraininstitute.org/api/auth-manager/v1", headers={"Authorization": f"Bearer {TOKEN}"})


res = http_client.get("/offline-token").raise_for_status()

breakpoint()
"""

obi_client = get_obi_one_client(
    virtual_lab_id=VLAB_ID,
    project_id=PROJ_ID,
    deployment="staging",
    token=TOKEN,
)
data = obi_client.launch_task(task_type="circuit_simulation", config_id=CONFIG_ID)

ls_client = get_launch_system_client(deployment="staging", token=TOKEN)
ls_client.pprint_messages(data["job_id"])
