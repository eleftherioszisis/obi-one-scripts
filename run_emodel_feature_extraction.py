import logging
from pathlib import Path

from obi_one.types import TaskType

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

CONFIG_ID = "9de8292b-e89a-4f27-a514-98758c05b632"
OUTPUT_DIR = Path(__file__).parent / "out/efeature_extraction/cloud"


domains = {
    "cell_a": {
        "virtual_lab_id": "e6030ed8-a589-4be2-80a6-f975406eb1f6",
        "project_id": "2720f785-a3a2-4472-969d-19a53891c817",
    }
}

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

    #config = create_config(manager)

    #L.info("Config: %s", config)
    manager.run_task(config_id=CONFIG_ID, check_mode="obi-one")
