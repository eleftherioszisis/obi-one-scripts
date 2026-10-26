"""Launch Task 3 e-model validation via local obi-one + staging launch-system.

Config construction mirrors
``examples/obi_one/scientific/tasks/emodel_building/03_emodel_validation.ipynb``
(``EModelValidationScanConfig`` with an EModel and a target e-features TaskResult).
"""

import logging
import os
from pathlib import Path

import obi_auth
from entitysdk import models
from obi_one.core.info import Info
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.from_id.emodel_from_id import EModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.blocks import (
    EModelInput,
    ValidationSettings,
    ValidationTargetEFeaturesInput,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
    EModelValidationScanConfig,
)
from obi_one.types import TaskType

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/emodel_validation/cloud"

L = logging.getLogger(__name__)

# Set to relaunch an existing TaskConfig without running create_config().
CONFIG_ID: str | None = None

# Staging test project entities.
# EModel from DM_19Oct2026_1215 optimisation; use a *different* extraction so Task 3
# treats all of its protocols as validation protocols (own extraction has none held out).
EMODEL_ID = "5b04f71b-cf9a-4452-9f3a-263d4779a18e"
TARGET_EFEATURES_TASK_RESULT_ID = "743c1709-af3e-4433-816c-d38bd994ed70"

# Same staging test project as run_emodel_feature_extraction.py / run_emodel_optimization.py
DOMAINS = {
    "cell_a": {
        "virtual_lab_id": "e6030ed8-a589-4be2-80a6-f975406eb1f6",
        "project_id": "2720f785-a3a2-4472-969d-19a53891c817",
    }
}


def _build_scan_config() -> EModelValidationScanConfig:
    return EModelValidationScanConfig(
        info=Info(
            campaign_name="EModel validation (other extraction)",
            campaign_description=(
                f"BluePyEModel score validation of EModel {EMODEL_ID} "
                f"against extraction {TARGET_EFEATURES_TASK_RESULT_ID}."
            ),
        ),
        emodel=EModelInput(emodel=EModelFromID(id_str=EMODEL_ID)),
        target_efeatures=ValidationTargetEFeaturesInput(
            task_result=TaskResultFromID(id_str=TARGET_EFEATURES_TASK_RESULT_ID)
        ),
        settings=ValidationSettings(
            validation_protocols_only=True,
            validation_function="max_score",
            validation_threshold=5.0,
        ),
    )


def create_config(manager):
    db_client = manager.db_client
    scan_config = _build_scan_config()

    L.info(
        "Validation settings: protocols_only=%s function=%s threshold=%s",
        scan_config.settings.validation_protocols_only,
        scan_config.settings.validation_function,
        scan_config.settings.validation_threshold,
    )
    L.info("EModel: %s", EMODEL_ID)
    L.info("Target e-features TaskResult: %s", TARGET_EFEATURES_TASK_RESULT_ID)

    grid_scan = GridScanGenerationTask(
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
        task_type=TaskType.emodel_validation,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=DOMAINS,
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
        activity_type=models.TaskActivity,
        check_mode="obi-one",
    )
