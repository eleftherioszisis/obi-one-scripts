import os
import httpx
import obi_one as obi
from entitysdk import Client, ProjectContext, models, LocalAssetStore
from http import HTTPStatus
import shutil
import logging

from utils import run_cloud_task

L = logging.getLogger(__name__)

subdomain = "cell_a"
environment = "local"
simulation_id = "42b1247e-57d1-4161-8b24-9ddc8af2ed0f"

run_cloud_task(
    task_type="ion_channel_model_simulation_execution",
    config_id=simulation_id,
    subdomain=subdomain,
    environment="local",
)
