"""Launch ion channel model simulation via local obi-one + staging launch-system.

Replaces the legacy in-process ``run_task_type`` flow. Config matches
``run_icm_cloud.py`` / the ion channel modeling examples.
"""

import logging
import subprocess
from pathlib import Path

import obi_one as obi
from entitysdk import models
from obi_one import IonChannelModelSimulationScanConfig
from obi_one.core.info import Info
from obi_one.scientific.blocks.ion_channel_model.ion_channel_model import (
    IonChannelModelWithConductance,
)
from obi_one.scientific.blocks.recordings.soma import SomaVoltageRecording
from obi_one.scientific.blocks.stimuli.stimulus import SEClampSomaticStimulus
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.types import TaskType

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/icm/local"

L = logging.getLogger(__name__)

# K_TST on staging
ION_CHANNEL_MODEL_ID = "8c60dccf-8dfc-48a4-a2db-358b9643e3fb"

# Set to relaunch without create_config()
CONFIG_ID: str | None = None


def create_config(manager):
    output_root = manager.output_dir
    db_client = manager.db_client

    subprocess.run(["rm", "-rf", "arm64"], check=False)

    sim_conf = IonChannelModelSimulationScanConfig(
        initialize=IonChannelModelSimulationScanConfig.Initialize(
            simulation_length=200,
            temperature=35,
            v_init=-80,
            random_seed=1,
        ),
        info=Info(
            campaign_name="Ion Channel Simulation Campaign Test 001",
            campaign_description="Test",
        ),
        ion_channel_models={
            "icm1": IonChannelModelWithConductance(
                ion_channel_model=IonChannelModelFromID(id_str=ION_CHANNEL_MODEL_ID),
                conductance=0.12,
            )
        },
        stimuli={
            "seclamp1": SEClampSomaticStimulus(
                level1_duration=50,
                level1_voltage=-80,
                level2_duration=100,
                level2_voltage=0,
                level3_duration=50,
                level3_voltage=-80,
            )
        },
        recordings={
            "rec_voltage": SomaVoltageRecording(
                neuron_set=None,
                dt=0.1,
            )
        },
        timestamps={},
    )

    with open(output_root / "simulate_ion_channel_scan_config.json", "w") as f:
        f.write(sim_conf.model_dump_json(indent=4))

    validated_sim_config = sim_conf.validated_config()

    grid_scan = obi.GridScanGenerationTask(
        form=validated_sim_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=output_root,
    )
    grid_scan.multiple_value_parameters(display=True)
    grid_scan.coordinate_parameters(display=True)
    grid_scan.execute(db_client=db_client)
    obi.run_tasks_for_generated_scan(grid_scan, db_client=db_client)

    campaign_id = grid_scan.form.campaign.id

    entity = (
        db_client.search_entity(
            entity_type=models.SimulationGeneration,
            query={"used__id": str(campaign_id)},
        )
        .one()
        .generated[0]
    )
    return entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.ion_channel_model_simulation_execution,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
    )

    if CONFIG_ID is None:
        config = create_config(manager)
        config_id = config.id
        L.info("Config: %s", config)
    else:
        config_id = CONFIG_ID
        L.info("Using existing config_id: %s", config_id)

    manager.run_task(
        config_id=config_id,
        activity_type=models.SimulationExecution,
        check_mode="obi-one",
    )
