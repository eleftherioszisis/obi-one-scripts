"""Launch emodel optimisation via local obi-one + staging launch-system.

Config construction mirrors the current
``examples/obi_one/scientific/tasks/emodel_building/02_emodel_optimization.ipynb``
in obi-one (Task 2: ``EModelOptimizationScanConfig`` with entity inputs on
``OptimizationInitialize``).
"""

import logging
import os
from pathlib import Path
import obi_auth

import obi_one as obi
from entitysdk import models
from obi_one.core.info import Info
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    CustomDistanceDependentDistribution,
    EModelOptimisationParameters,
    GlobalParameterSelection,
    MechanismRegionSelection,
    OptimizationInitialize,
    OptimizationParams,
    OptimizationSettings,
    OptimizationValue,
    ParameterSelection,
    ParametersSelection,
)
from obi_one.types import TaskType

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/emodel_optimization/cloud"

L = logging.getLogger(__name__)

# Set to relaunch an existing TaskConfig without running create_config().
CONFIG_ID: str | None = None

# From 02_emodel_optimization.ipynb (SSCx C060109A1-SR-C1 staging dataset)
EXTRACTION_TASK_RESULT_ID = "743c1709-af3e-4433-816c-d38bd994ed70"
ETYPE_ID = "75703892-27a4-4588-9f12-145b08051db5"  # cADpyr
MORPHOLOGY_ID = "de34e33d-594d-4227-83d1-4e5bb657cf0c"  # C060114A5, rat

ION_CHANNEL_MODEL_IDS = {
    "CaDynamics_DC0": "3d371a7e-ff6a-45a0-9f32-34505ac940df",
    "Ca_HVA2": "21ebb7ab-b41b-441d-b494-6665075d26b0",
    "Ca_LVAst": "91cfc99a-9dc7-462c-9b08-330dfb4db871",
    "Ih": "af9eef69-40a3-4e41-9c3f-542a9ff689fc",
    "K_Pst": "bdc5d10e-fd25-403b-83cd-81853676ca35",
    "K_Tst": "8c60dccf-8dfc-48a4-a2db-358b9643e3fb",
    "Nap_Et2": "7decbf75-9414-4754-bf54-5fa787097206",
    "NaTg": "13c947c3-cb76-4a9a-91f4-146e95bd25f3",
    "SK_E2": "e1090418-c607-4901-88ae-a5ceb5bfb75a",
    "SKv3_1": "a014a0f6-217a-4e18-935f-aa298e35c9d1",
}

# Same staging test project as 02_emodel_optimization.ipynb / run_emodel_feature_extraction.py
DOMAINS = {
    "cell_a": {
        "virtual_lab_id": "e6030ed8-a589-4be2-80a6-f975406eb1f6",
        "project_id": "2720f785-a3a2-4472-969d-19a53891c817",
    }
}


def _fixed(value):
    return ParameterSelection(value=OptimizationValue(value=value))


def _bounds(lower, upper, distribution="uniform"):
    return ParameterSelection(
        value=OptimizationValue(mode="bounds", bounds=(lower, upper)),
        distribution=distribution,
    )


def _build_scan_config():
    ion_channel_models = {
        name: IonChannelModelFromID(id_str=entity_id)
        for name, entity_id in ION_CHANNEL_MODEL_IDS.items()
    }

    def channel(name, parameters=None):
        return MechanismRegionSelection(
            ion_channel_model=ion_channel_models[name],
            parameters=parameters or {},
        )

    return obi.EModelOptimizationScanConfig(
        info=Info(
            campaign_name="L5PC Optimisation",
            campaign_description="Optimise L5PC model against extracted e-features.",
        ),
        initialize=OptimizationInitialize(
            emodel="L5PC",
            etype=ETypeClassFromID(id_str=ETYPE_ID),
            target_efeatures=TaskResultFromID(id_str=EXTRACTION_TASK_RESULT_ID),
            morphology=obi.CellMorphologyFromID(id_str=MORPHOLOGY_ID),
        ),
        emodel_optimisation_parameters=EModelOptimisationParameters.from_parameters_selection(
            ParametersSelection(
                ion_channel_models=[
                    IonChannelModelFromID(id_str=icm_id)
                    for icm_id in ION_CHANNEL_MODEL_IDS.values()
                ],
                global_parameters={
                    "v_init": GlobalParameterSelection(
                        value=OptimizationValue(value=-80.0)
                    ),
                    "celsius": GlobalParameterSelection(
                        value=OptimizationValue(value=34.0)
                    ),
                },
                base_parameters={
                    "myelinated": {"cm": _fixed(0.02)},
                    "all": {
                        "Ra": _fixed(100.0),
                        "g_pas": _bounds(1e-5, 6e-5),
                        "e_pas": _bounds(-95.0, -60.0),
                    },
                    "axonal": {
                        "cm": _fixed(1.0),
                        "ena": _fixed(50.0),
                        "ek": _fixed(-90.0),
                    },
                    "somatic": {
                        "cm": _fixed(1.0),
                        "ena": _fixed(50.0),
                        "ek": _fixed(-90.0),
                    },
                    "apical": {
                        "cm": _fixed(2.0),
                        "ena": _fixed(50.0),
                        "ek": _fixed(-90.0),
                    },
                    "basal": {"cm": _fixed(2.0)},
                },
                mechanism_regions={
                    "allact": (
                        channel("CaDynamics_DC0"),
                        channel("Ca_HVA2"),
                        channel("Ca_LVAst"),
                    ),
                    "somaxon": (
                        channel("SKv3_1"),
                        channel("SK_E2"),
                        channel("K_Pst"),
                        channel("K_Tst"),
                    ),
                    "axonal": (
                        channel(
                            "CaDynamics_DC0",
                            {
                                "decay": _bounds(20.0, 300.0),
                                "gamma": _bounds(0.005, 0.05),
                            },
                        ),
                        channel(
                            "NaTg",
                            {
                                "vshifth": _fixed(15.0),
                                "slopem": _fixed(7.0),
                                "gNaTgbar": _bounds(0.0, 1.5),
                            },
                        ),
                        channel("Nap_Et2", {"gNap_Et2bar": _bounds(0.0, 0.02)}),
                        channel("K_Pst", {"gK_Pstbar": _bounds(0.0, 1.0)}),
                        channel("K_Tst", {"gK_Tstbar": _bounds(0.0, 0.2)}),
                        channel("SKv3_1", {"gSKv3_1bar": _bounds(0.0, 1.0)}),
                        channel("Ca_HVA2", {"gCa_HVAbar": _bounds(0.0, 0.001)}),
                        channel("Ca_LVAst", {"gCa_LVAstbar": _bounds(0.0, 0.01)}),
                        channel("SK_E2", {"gSK_E2bar": _bounds(0.0, 0.1)}),
                    ),
                    "somatic": (
                        channel(
                            "CaDynamics_DC0",
                            {
                                "decay": _bounds(20.0, 300.0),
                                "gamma": _bounds(0.005, 0.05),
                            },
                        ),
                        channel(
                            "NaTg",
                            {
                                "vshiftm": _fixed(13.0),
                                "vshifth": _fixed(15.0),
                                "slopem": _fixed(7.0),
                                "gNaTgbar": _bounds(0.0, 0.3),
                            },
                        ),
                        channel("K_Pst", {"gK_Pstbar": _bounds(0.0, 0.2)}),
                        channel("K_Tst", {"gK_Tstbar": _bounds(0.0, 0.1)}),
                        channel("SKv3_1", {"gSKv3_1bar": _bounds(0.0, 1.0)}),
                        channel("Ca_HVA2", {"gCa_HVAbar": _bounds(0.0, 0.001)}),
                        channel("Ca_LVAst", {"gCa_LVAstbar": _bounds(0.0, 0.01)}),
                        channel("SK_E2", {"gSK_E2bar": _bounds(0.0, 0.1)}),
                    ),
                    "apical": (
                        channel(
                            "NaTg",
                            {
                                "vshiftm": _fixed(6.0),
                                "vshifth": _fixed(6.0),
                                "gNaTgbar": _bounds(0.0, 0.1, "decay"),
                            },
                        ),
                        channel("SKv3_1", {"gSKv3_1bar": _bounds(0.0, 0.003)}),
                        channel("Ca_HVA2", {"gCa_HVAbar": _bounds(0.0, 0.0001)}),
                        channel("Ca_LVAst", {"gCa_LVAstbar": _bounds(0.0, 0.001)}),
                    ),
                    "somadend": (
                        channel("Ih", {"gIhbar": _bounds(0.0, 0.0002, "exp")}),
                    ),
                    "basal": (
                        channel("CaDynamics_DC0", {"gamma": _bounds(0.005, 0.05)}),
                        channel("Ca_HVA2", {"gCa_HVAbar": _bounds(0.0, 0.0001)}),
                        channel("Ca_LVAst", {"gCa_LVAstbar": _bounds(0.0, 0.001)}),
                    ),
                },
                distribution_parameters={
                    "decay": {
                        "constant": OptimizationValue(mode="bounds", bounds=(-0.1, 0.0)),
                    },
                },
            ),
        ),
        distance_dependent_distributions={
            "decay": CustomDistanceDependentDistribution(
                name="decay",
                function="math.exp({distance}*{constant})*{value}",
                parameters=["constant"],
            ),
        },
        optimization_settings=OptimizationSettings(
            optimiser="SO-CMA",
            max_ngen=1,
            optimisation_timeout=300.0,
            validation_threshold=5.0,
            seed=1,
        ),
        optimization_params=OptimizationParams(
            offspring_size=2,
        ),
    )


def create_config(manager):
    db_client = manager.db_client
    scan_config = _build_scan_config()

    L.info(
        "Optimisation settings: %s",
        scan_config.optimization_settings.to_dict(scan_config.optimization_params),
    )
    L.info(
        "Mechanism regions: %s",
        list(scan_config.parameters_selection.mechanism_regions),
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

    token = obi_auth.get_token(offline=True)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.emodel_optimization,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=DOMAINS,
        token=token,
    )

    if CONFIG_ID is None:
        config = create_config(manager)
        config_id = config.id
        L.info("Config: %s", config)
    else:
        config_id = CONFIG_ID
        L.info("Using existing config_id: %s", config_id)

    if "ACCESS_TOKEN" not in os.environ:
        L.warning(
            "ACCESS_TOKEN is not set; export a staging platform token before launch."
        )

    manager.run_task(
        config_id=config_id,
        activity_type=models.TaskActivity,
        check_mode="obi-one",
    )
