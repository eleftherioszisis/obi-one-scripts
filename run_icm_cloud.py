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
simulation_id = "6e390cd2-1cd8-4e4c-bee4-7f992ac82828"

run_cloud_task(
    task_type="ion_channel_model_simulation",
    config_id=simulation_id,
    subdomain=subdomain,
    environment=environment,
)
