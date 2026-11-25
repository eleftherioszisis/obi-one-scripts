"""Single-neuron simulation against an obi-one service running a branch.

Point OBI_ONE_URL at that service (default http://127.0.0.1:8101). The service decides which
obi-one code the worker checks out, so it must submit a ``commit:<sha>`` ref for a branch test.
Set CONFIG_ID to relaunch an existing Simulation instead of generating a new one.
"""

import logging
import os
from pathlib import Path

import httpx
from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST
from obi_one.core.info import Info
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.stimuli.stimulus import ConstantCurrentClampSomaticStimulus
from obi_one.scientific.blocks.timestamps.regular import RegularTimestamps
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
)
from obi_one.types import TaskType

import utils
from utils import OBIClient, RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/single_neuron_sim_branch/cloud"
OBI_ONE_URL = os.environ.get("OBI_ONE_URL", "http://127.0.0.1:8101")

MEMODEL_ID = "9f521816-d2f5-4257-bf77-7da1de301063"  # VPM_TC, public on staging
SIM_DURATION = 300.0

DOMAINS = {
    "cell_a": {
        "virtual_lab_id": LAB_ID_STAGING_TEST,
        "project_id": PROJECT_ID_STAGING_TEST,
    }
}


def get_obi_one_client(virtual_lab_id, project_id, deployment, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": str(virtual_lab_id),
        "project-id": str(project_id),
    }
    return OBIClient(httpx.Client(base_url=OBI_ONE_URL, headers=headers, timeout=60))


utils.get_obi_one_client = get_obi_one_client


def create_config(manager):
    db_client = manager.db_client
    sim_conf = MEModelSimulationScanConfig.empty_config()
    sim_conf.set(
        Info(
            campaign_name="PR 1245 single neuron e2e",
            campaign_description="Branch test of neurodamus mechanism compilation",
        ),
        name="info",
    )
    timestamps = RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=SIM_DURATION)
    sim_conf.add(timestamps, name="Timestamps")
    sim_conf.add(
        ConstantCurrentClampSomaticStimulus(
            timestamps=timestamps.ref, duration=200.0, amplitude=0.1
        ),
        name="CurrentClampInput",
    )
    sim_conf.set(
        MEModelSimulationScanConfig.Initialize(
            circuit=MEModelFromID(id_str=MEMODEL_ID), simulation_length=SIM_DURATION
        ),
        name="initialize",
    )

    grid_scan = GridScanGenerationTask(
        form=sim_conf.validated_config(),
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.execute(db_client=db_client)
    # Generates the sonata_simulation_config asset the execution task stages.
    run_tasks_for_generated_scan(grid_scan, db_client=db_client)
    return grid_scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.single_neuron_simulation_execution,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=DOMAINS,
    )
    config_id = os.environ.get("CONFIG_ID") or create_config(manager).id
    print(f"CONFIG_ID={config_id}", flush=True)
    manager.run_task(config_id=config_id, check_mode="obi-one")
