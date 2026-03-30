import logging
from pathlib import Path
import subprocess
import obi_one as obi

from obi_one.core.info import Info
from obi_one.types import TaskType
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.blocks.ion_channel_model import IonChannelModelWithConductance
from obi_one.scientific.blocks.recording import (
    SomaVoltageRecording,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    SEClampSomaticStimulus,
)
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationScanConfig,
)
from entitysdk import models

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "out/icm/cloud"

#simulation_id = "42b1247e-57d1-4161-8b24-9ddc8af2ed0f"


def create_config(manager):
    output_root = manager.output_dir
    db_client = manager.db_client

    subprocess.run(["rm", "-rf", "arm64"])

    # ion channel models
    id_1 = "8c60dccf-8dfc-48a4-a2db-358b9643e3fb"  # K_TST staging

    # most simple case
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
                ion_channel_model=IonChannelModelFromID(id_str=id_1),
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

    with open(f"./{output_root}/simulate_ion_channel_scan_config.json", "w") as f:
        f.write(sim_conf.model_dump_json(indent=4))

    # all of the following can be done in the task manager script

    # validate
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
            entity_type=models.SimulationGeneration, query={"used__id": str(campaign_id)}
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
        obi_one_deployment="staging",
        launch_system_deployment="staging",
        db_deployment="staging",
    )

    config = create_config(manager)
    L.info("Config: %s", config)
    manager.run_task(config_id=config.id)
