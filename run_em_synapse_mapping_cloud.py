import logging
from pathlib import Path

import obi_one as obi
from obi_one.types import TaskType
from entitysdk import models
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingScanConfig

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/em_synapse_mapping/cloud"

L = logging.getLogger(__name__)


def create_config(manager):
    db_client = manager.db_client
    skeletonized_morphology = db_client.search_entity(
        entity_type=models.CellMorphology, query={"subject__name": 'IARPA MICrONS mouse'}
    ).first()
    scan = obi.GridScanGenerationTask(
        form=EMSynapseMappingScanConfig(
            initialize=EMSynapseMappingScanConfig.Initialize(
                spiny_neuron=obi.CellMorphologyFromID(id_str=str(skeletonized_morphology.id))
            ),
            info=obi.Info(
                campaign_name="EM Synapse Mapping Single Test",
                campaign_description="Testing EM Synapse Mapping Single Task"
            ),
        ),
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    scan.execute(db_client=db_client)
    return scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(leve=logging.DEBUG)
    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.em_synapse_mapping,
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
        check_mode="job",
    )
