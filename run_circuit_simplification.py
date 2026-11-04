import logging
from pathlib import Path

import obi_one as obi
from entitysdk import models
from obi_one.core.info import Info
from obi_one.scientific.blocks.simplification_algorithms import (
    SingleCompartmentAlgorithm,
)
from obi_one.types import TaskType

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/circuit_simplification/cloud"

L = logging.getLogger(__name__)

# From run_simplification_local.ipynb (paired neuron, staging)
CIRCUIT_ID = "ed096991-4171-4cfc-b54e-756323fc62e7"


def create_config(manager):
    db_client = manager.db_client

    scan_config = obi.CircuitSimplificationScanConfig(
        info=Info(
            campaign_name="Circuit Simplification Test",
            campaign_description="Testing circuit simplification",
        ),
        initialize=obi.CircuitSimplificationScanConfig.Initialize(
            circuit=obi.CircuitFromID(id_str=CIRCUIT_ID),
        ),
        algorithms={
            "single_compartment": SingleCompartmentAlgorithm(),
        },
    )

    grid_scan = obi.GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.execute(db_client=db_client)

    campaign_entity = grid_scan.form.campaign
    L.info(
        "Campaign '%s' (ID %s): %s",
        campaign_entity.name,
        campaign_entity.id,
        campaign_entity.description,
    )

    for cfg in grid_scan.single_configs:
        L.info(
            "  Coordinate %s: '%s' (ID %s)",
            cfg.idx,
            cfg.single_entity.name,
            cfg.single_entity.id,
        )

    return grid_scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_simplification,
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
