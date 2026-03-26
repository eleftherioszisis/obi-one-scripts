import os
from rich import print
import json
from datetime import datetime, UTC
import httpx
import obi_one as obi
from entitysdk import Client, ProjectContext, models, LocalAssetStore
from http import HTTPStatus
from obi_one.scientific.tasks.skeletonization import SkeletonizationTask
import shutil
import logging

from utils import get_obi_one_client, get_launch_system_client

L = logging.getLogger(__name__)

token = os.environ["ACCESS_TOKEN"]
environment = "staging"
virtual_lab_id = "de9018bf-d6b5-4a01-a0bc-b23ca4579166"
project_id = "86873a11-1c2c-4e17-8ce1-0eb472f36880"

OBI_ONE_API_URL = "http://127.0.0.1:8100"
headers = {
    "Authorization": f"Bearer {token}",
    "virtual-lab-id": virtual_lab_id,
    "project-id": project_id,
}
api_client = httpx.Client(base_url=OBI_ONE_API_URL, headers=headers)
ls_client = httpx.Client(
    #base_url="http://127.0.0.1:8001",
    base_url="https://staging.cell-a.openbraininstitute.org/api/launch-system",
    headers={"Authorization": f"Bearer {token}"},
)
project_context = ProjectContext(virtual_lab_id=virtual_lab_id, project_id=project_id)
db_client = Client(environment=environment, project_context=project_context, token_manager=token)

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

def create_config():

    mesh_id = "6dd9bb20-255c-4eb6-a88a-dcb49fddc65e"
    mesh_from_id = obi.EMCellMeshFromID(id_str=mesh_id)
    mesh_entity = mesh_from_id.entity(db_client=db_client)

    initialize = obi.SkeletonizationScanConfig.Initialize(cell_mesh=mesh_from_id)
    info = obi.Info(campaign_name="Skeletonization Campaign", campaign_description="Skeletonization of a morphology mesh.")

    scan_config = obi.SkeletonizationScanConfig(initialize=initialize, info=info)

    output_root = "./out"

    scan = obi.GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=output_root,
    )

    scan.execute(db_client=db_client)

    campaign_entity = scan.form.campaign
    print(f"Campaign '{campaign_entity.name}' (ID {campaign_entity.id}): {campaign_entity.description}")

    for cfg in scan.single_configs:
        print(f"  Coordinate {cfg.idx}: '{cfg.single_entity.name}' (ID {cfg.single_entity.id})")

    return scan.single_configs[0].single_entity


config_id = create_config().id

TOKEN = os.environ["ACCESS_TOKEN"]


obi_client = get_obi_one_client(
    virtual_lab_id=virtual_lab_id,
    project_id=project_id,
    deployment="local",
    token=TOKEN,
)
data = obi_client.launch_task(task_type="morphology_skeletonization", config_id=config_id)

ls_client = get_launch_system_client(deployment="staging", token=TOKEN)
ls_client.pprint_messages(data["job_id"])
