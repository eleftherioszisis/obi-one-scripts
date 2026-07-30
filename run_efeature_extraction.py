import logging
from pathlib import Path
from typing import get_args

import obi_one as obi
from entitysdk import models
from obi_one.core.info import Info
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.initialize import (
    ExtractionInitialize,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (
    ProtocolAndFeatureSelection,
    SelectEFeaturesByProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.settings import (
    Settings,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (
    ProtocolUnion,
)
from obi_one.types import TaskType
from obi_one.utils.db_sdk import get_recording_amplitudes, get_recording_protocols

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent / "out/efeature_extraction/cloud"

# ElectricalCellRecording entities from the staging test project
RECORDING_IDS = (
    "e010cdba-e518-4379-8e6b-c51e119ccd33",
    "2229f1f4-f561-4859-98a4-33cce182631d",
)

# Optional validation amplitudes, e.g. {("IDRestProtocol", 0.25)}
VALIDATION_AMPLITUDES: set[tuple[str, float]] = set()

PROTOCOL_CLASSES = {
    cls.__name__: cls for cls in get_args(get_args(ProtocolUnion)[0])
}

domains = {
    "cell_a": {
        "virtual_lab_id": obi.LAB_ID_STAGING_TEST,
        "project_id": obi.PROJECT_ID_STAGING_TEST,
    }
}


def _build_protocols(db_client, recording_ids: tuple[str, ...]):
    """Discover protocols/amplitudes from recordings and build Protocol instances."""
    by_recording = get_recording_protocols(
        recording_ids=list(recording_ids),
        db_client=db_client,
    )
    amplitudes_by_protocol = get_recording_amplitudes(
        recording_ids=list(recording_ids),
        db_client=db_client,
    )
    protocol_union = sorted({p for protocols in by_recording.values() for p in protocols})

    L.info("Discovered %s protocols: %s", len(protocol_union), protocol_union)
    for rid, protocols in by_recording.items():
        L.info("  %s...: %s", rid[:8], protocols)
    for proto, amps in amplitudes_by_protocol.items():
        L.info("  %s: %s amplitudes", proto, len(amps))

    protocols_list = []
    for class_name in protocol_union:
        if class_name not in PROTOCOL_CLASSES:
            L.warning("No Protocol class for %s, skipping", class_name)
            continue

        protocol = PROTOCOL_CLASSES[class_name]()
        amps = amplitudes_by_protocol.get(class_name, [])
        protocol.extraction_amplitudes = tuple(
            (amp, (class_name, amp) in VALIDATION_AMPLITUDES) for amp in amps
        )
        protocols_list.append(protocol)

    L.info("Built %s protocols with amplitudes", len(protocols_list))
    for protocol in protocols_list:
        n_val = sum(1 for _, is_val in protocol.extraction_amplitudes if is_val)
        L.info(
            "  %s (protocol_name=%r): %s amplitudes (%s validation), %s features",
            type(protocol).__name__,
            protocol.protocol_name,
            len(protocol.extraction_amplitudes),
            n_val,
            len(protocol.features),
        )
    return protocols_list


def create_config(manager):
    db_client = manager.db_client
    protocols_list = _build_protocols(db_client, RECORDING_IDS)

    scan_config = obi.EModelEFeatureExtractionScanConfig(
        info=Info(
            campaign_name="L5PC eFeature Extraction",
            campaign_description="Extract e-features from staging test recordings.",
        ),
        initialize=ExtractionInitialize(
            electrical_cell_recording=tuple(
                obi.ElectricalCellRecordingFromID(id_str=rid) for rid in RECORDING_IDS
            ),
        ),
        settings=Settings(),
        efeatures_by_protocol=ProtocolAndFeatureSelection(
            selection=SelectEFeaturesByProtocol(protocols=tuple(protocols_list))
        ),
    )

    grid_scan = obi.GridScanGenerationTask(
        form=scan_config,
        output_root=manager.output_dir,
        coordinate_directory_option="ZERO_INDEX",
    )
    grid_scan.execute(db_client=db_client)

    campaign = grid_scan.form.campaign
    single = grid_scan.single_configs[0].single_entity
    L.info("Campaign TaskConfig: %s", campaign.id if campaign else None)
    L.info("Single TaskConfig:   %s", single.id if single else None)
    return single


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.efeature_extraction,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=domains,
    )
    config = create_config(manager)
    L.info("Config: %s", config)
    manager.run_task(
        config_id=config.id,
        activity_type=models.TaskActivity,
        check_mode="obi-one",
    )
