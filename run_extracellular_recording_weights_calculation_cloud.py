import logging
from pathlib import Path

import obi_one as obi
from obi_one.types import TaskType
from entitysdk import models

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/extracellular_recording_weights_calculation/cloud"

L = logging.getLogger(__name__)

CIRCUIT_ID = "7d007c43-201f-42d6-960d-93f6229fe935"


def create_config(manager):
    db_client = manager.db_client

    scan_config = obi.CreateExtracellularRecordingArrayScanConfig(
        info=obi.Info(
            campaign_name="Extracellular Recording Array Weights",
            campaign_description="LineSource weights calculation for a linear electrode array.",
        ),
        initialize=obi.CreateExtracellularRecordingArrayScanConfig.Initialize(
            circuit=obi.CircuitFromID(id_str=CIRCUIT_ID),
            calculation_method="LineSource",
        ),
        electrode_locations=obi.LinearExtracellularLocations(
            n_electrodes=16,
            spacing=20.0,
            origin_x=0.0,
            origin_y=0.0,
            origin_z=0.0,
        )
    )

    validated_sim_conf = scan_config.validated_config()

    grid_scan = obi.GridScanGenerationTask(
        form=validated_sim_conf,
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.multiple_value_parameters(display=True)
    grid_scan.coordinate_parameters(display=True)
    grid_scan.execute(db_client=db_client)

    campaign_id = grid_scan.form.campaign.id

    entity = (
        db_client.search_entity(
            entity_type=models.TaskActivity,
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
        task_type=TaskType.extracellular_recording_weights_calculation,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
    )
    config = create_config(manager)
    L.info("Config: %s", config)
    manager.run_task(
        config_id=config.id,
        activity_type=models.TaskActivity,
        check_mode="obi-one",
    )
