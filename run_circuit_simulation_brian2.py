import os
import httpx
import logging
import webbrowser
from pathlib import Path
from obi_one.types import TaskType
from entitysdk import models
from entitysdk.types import ContentType, AssetLabel

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data/simulation_brian2"

domains = {
    "cell_a": {
        "virtual_lab_id": "84258ff5-114f-4865-9a2d-258575c23909",
        "project_id": "da749e43-9c11-4671-8a05-7e709cc4a97d",
    },
    "cell_b": {},
}

# cell_a
CONFIG_ID = "48a57ae8-893e-439a-88f7-ae5b0dad05db"

# cell_b
# CONFIG_ID = "3ff3ead5-1b9b-4d61-8175-3a9868f29dcd"


def create_config(manager):

    db_client = manager.db_client
    circuit_id = "a5d839e1-3a65-4237-a2b4-41710edfab0a"

    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)

    campaign = db_client.register_entity(
        entity=models.SimulationCampaign(
            name="Test Campaign Flywire",
            description="Test Campaign for Flywire circuit `nbs1_hexo_100_hex`",
            entity_id=circuit_id,
            scan_parameters={},
        )
    )
    simulation = db_client.register_entity(
        entity=models.Simulation(
            name="Test Simulation Flywire",
            description="Test Simulation for Flywire circuit `nbs1_hexo_100_hex`",
            simulation_campaign_id=campaign.id,
            entity_id=circuit_id,
            scan_parameters={},
            number_neurons=circuit.number_neurons,
        )
    )
    db_client.upload_file(
        entity_id=simulation.id,
        entity_type=models.Simulation,
        file_path=DATA_DIR / "simulation_config.json",
        file_name="simulation_config.json",
        file_content_type=ContentType.application_json,
        asset_label=AssetLabel.sonata_simulation_config,
    )
    L.info("Simulation config id: %s", simulation.id)
    return simulation.id


OUTPUT_DIR = Path(__file__).parent / "out/circuit_simulation_brian2/cloud"

TOKEN = os.environ["ACCESS_TOKEN"]

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_simulation,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=domains,
    )
    # config_id = create_config(manager)

    task = manager.submit_task(
        config_id=CONFIG_ID,
    )
    manager.monitor_task(task=task, check_mode="obi-one")
