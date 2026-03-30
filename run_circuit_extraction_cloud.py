import logging
from pathlib import Path

import obi_one as obi
from obi_one.types import TaskType

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/circuit_extraction/cloud"


def create_config(manager):

    db_client = manager.db_client()
    circuit_id = "0182b55e-2f38-4e06-bbd0-b11e70449804"

    circuit_from_id = obi.CircuitFromID(id_str=circuit_id)
    circuit_entity = circuit_from_id.entity(db_client=db_client)

    initialize = obi.CircuitExtractionScanConfig.Initialize(circuit=circuit_from_id)

    # Create a CircuitExtractionScanConfig object with the initialize object
    neuron_set = obi.PredefinedNeuronSet(node_set="Excitatory", sample_percentage=50)
    info = obi.Info(campaign_name="EXC-Extraction", campaign_description="Extraction of percentages of EXC neurons")
    scan_config = obi.CircuitExtractionScanConfig(initialize=initialize, neuron_set=neuron_set, info=info)

    # Create the grid scan object
    scan = obi.GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    scan.execute(db_client=db_client)

    return scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_extraction,
        subdomain="cell_a",
        obi_one_deployment="staging",
        launch_system_deployment="staging",
        db_deployment="staging",
    )
    config = create_config(manager)
    L.info("Config: %s", config)
    manager.run_task(config_id=config.id)
