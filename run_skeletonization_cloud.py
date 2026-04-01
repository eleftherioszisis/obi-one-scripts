import logging
from pathlib import Path

import obi_one as obi
from obi_one.types import TaskType

from utils import RemoteTaskManager


OUTPUT_DIR = Path(__file__).parent / "out/morphology_skeletonization/cloud"


def create_config(manager):

    db_client = manager.db_client

    mesh_id = "6dd9bb20-255c-4eb6-a88a-dcb49fddc65e"
    mesh_from_id = obi.EMCellMeshFromID(id_str=mesh_id)
    # mesh_entity = mesh_from_id.entity(db_client=db_client)

    initialize = obi.SkeletonizationScanConfig.Initialize(cell_mesh=mesh_from_id)
    info = obi.Info(
        campaign_name="Skeletonization Campaign",
        campaign_description="Skeletonization of a morphology mesh.",
    )

    scan_config = obi.SkeletonizationScanConfig(initialize=initialize, info=info)

    output_root = manager.output_dir

    scan = obi.GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=output_root,
    )

    scan.execute(db_client=db_client)

    campaign_entity = scan.form.campaign
    print(
        f"Campaign '{campaign_entity.name}' (ID {campaign_entity.id}): {campaign_entity.description}"
    )

    for cfg in scan.single_configs:
        print(
            f"  Coordinate {cfg.idx}: '{cfg.single_entity.name}' (ID {cfg.single_entity.id})"
        )

    return scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.morphology_skeletonization,
        subdomain="cell_a",
        obi_one_deployment="staging",
        launch_system_deployment="staging",
        db_deployment="staging",
    )

    config = create_config(manager)
    manager.run_task(config_id=config.id)
