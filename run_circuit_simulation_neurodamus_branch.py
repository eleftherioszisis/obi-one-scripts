"""Neurodamus circuit simulation against an obi-one service running a branch.

Point OBI_ONE_URL at that service (default http://127.0.0.1:8101). The service decides which
obi-one code the worker checks out, so it must submit a ``commit:<sha>`` ref for a branch test.
"""

import logging
import os
from pathlib import Path

import httpx
from obi_one.core.info import Info
from obi_one.core.scan_generation import GridScanGenerationTask
from entitysdk import models
from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.blocks.recordings.soma import SomaVoltageRecording
from obi_one.scientific.blocks.stimuli.stimulus import ConstantCurrentClampSomaticStimulus
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)
from obi_one.types import TaskType

import utils
from utils import OBIClient, RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/circuit_simulation_neurodamus_branch/cloud"
OBI_ONE_URL = os.environ.get("OBI_ONE_URL", "http://127.0.0.1:8101")

# nbS1-HEX0-L1 extraction, 9 neurons.
CIRCUIT_ID = "817b1b4d-a90c-439e-a482-e7bb143c94aa"

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
    sim_conf = CircuitSimulationScanConfig.empty_config()
    sim_conf.set(
        Info(
            campaign_name="PR 1245 neurodamus e2e",
            campaign_description="Branch test of neurodamus mechanism compilation",
        ),
        name="info",
    )
    neurons = AllBiophysicalNeurons()
    sim_conf.add(neurons, name="AllBiophysicalNeurons")
    sim_conf.add(
        ConstantCurrentClampSomaticStimulus(neuron_set=neurons.ref, amplitude=0.1, duration=100.0),
        name="CurrentClamp",
    )
    sim_conf.add(SomaVoltageRecording(neuron_set=neurons.ref), name="VoltageRecording")
    sim_conf.set(
        CircuitSimulationScanConfig.Initialize(
            circuit=CircuitFromID(id_str=CIRCUIT_ID),
            node_set=neurons.ref,
            simulation_length=200.0,
        ),
        name="initialize",
    )

    grid_scan = GridScanGenerationTask(
        form=sim_conf.validated_config(),
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.execute(db_client=manager.db_client)
    return grid_scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_simulation_neurodamus_machine,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=DOMAINS,
    )
    # Relaunch an existing Simulation by setting CONFIG_ID instead of generating a new one.
    config_id = os.environ.get("CONFIG_ID") or create_config(manager).id
    logging.info("Simulation entity: %s", config_id)
    manager.run_task(
        config_id=config_id,
        check_mode="job",
        activity_type=models.SimulationExecution,
    )
