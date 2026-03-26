from pathlib import Path

import obi_one as obi
from obi_one.types import TaskType

from utils import clean_dir_if_exists, RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/circuit_extraction/cloud"

CIRCUIT_ID = "0182b55e-2f38-4e06-bbd0-b11e70449804"

manager = RemoteTaskManager(
    output_dir=OUTPUT_DIR,
    task_type=TaskType.circuit_extraction,
    subdomain="cell_a",
    obi_one_deployment="local",
    launch_system_deployment="staging",
    db_deployment="staging",
)


def create_config(manager):

    db_client = manager.get_db_client()

    circuit_from_id = obi.CircuitFromID(id_str=CIRCUIT_ID)
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
    config = create_config(manager)
    manager.run_task(config_id=config.id)
