import obi_one as obi


project_id = "54aa306a-b7db-4087-82ec-c6dec1617df4"
virtual_lab_id = "594fd60d-7a38-436f-939d-500feaa13bba"
environment = "staging"

manager = TaskManager(
    virtual_lab_id=virtual_lab_id,
    project_id=project_id,
    environment=environment,
    token_mode=TokenMode.access_token_keycloak,
)

client = manager.get_db_client()


CIRCUIT_ID = "0182b55e-2f38-4e06-bbd0-b11e70449804"


def create_config(output_dir):

    circuit_from_id = obi.CircuitFromID(id_str=CIRCUIT_ID)
    # circuit_entity = circuit_from_id.entity(db_client=client)

    initialize = obi.CircuitExtractionScanConfig.Initialize(circuit=circuit_from_id)

    # Create a CircuitExtractionScanConfig object with the initialize object
    neuron_set = obi.PredefinedNeuronSet(node_set="Excitatory", sample_percentage=50)
    info = obi.Info(
        campaign_name="EXC-Extraction",
        campaign_description="Extraction of percentages of EXC neurons",
    )
    scan_config = obi.CircuitExtractionScanConfig(
        initialize=initialize, neuron_set=neuron_set, info=info
    )

    # Create the grid scan object
    output_root = output_dir / "circuit_extraction_on_launch_system/grid_scan"
    scan = obi.GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=output_root,
    )
    scan.execute(db_client=client)

    single_config_entity = scan.single_configs[0].single_entity

    return single_config_entity


config = create_config
