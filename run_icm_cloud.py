import os
import httpx
import obi_one as obi
from entitysdk import Client, ProjectContext, models, LocalAssetStore
from http import HTTPStatus
from obi_one.scientific.tasks.skeletonization import SkeletonizationTask
import shutil
import logging

from utils import run_cloud_task

L = logging.getLogger(__name__)

subdomain = "cell_a"
environment = "local"
simulation_id = "65235f18-c18e-40e6-8c16-b1fdff9da6ce"

run_cloud_task(
    task_type="ion_channel_model_simulation_execution",
    config_id=simulation_id,
    subdomain=subdomain,
    environment=environment,
)
