import json
import logging
from pathlib import Path
from uuid import UUID  # 1. Make sure UUID is explicitly imported

from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationSingleConfig
from obi_one.types import TaskType
from entitysdk import models
from utils import RemoteTaskManager

# 2. Rebuild the Pydantic model structure to resolve the type definitions
MeshLodGenerationSingleConfig.model_rebuild()

OUTPUT_DIR = Path(__file__).parent / "out/mesh_lod_generation/cloud"
L = logging.getLogger(__name__)

def create_config(manager):
    db_client = manager.db_client

    entity_id='cba24bb4-fb6f-4e3d-8263-f6a54ef34124'
    mesh_asset_id='e0438ed2-72f5-477a-9b35-d7cdeaa34fa3'
    mesh_format="glb"

    # 1. Instantiate the LOD task configuration model
    lod_config = MeshLodGenerationSingleConfig(
        entity_id=entity_id,
        mesh_asset_id=mesh_asset_id,
        mesh_format=mesh_format
    )
    # 2. Register the TaskConfig object matching its required schema fields
    config_entity = db_client.register_entity(
        models.TaskConfig(
            name="Mesh LOD Generation Config",
            description="LOD configuration for target entity",
            # Updated to match the permitted Enum values
            task_config_type="mesh_lod_generation__config", 
            meta={
                "scan_parameters": lod_config.model_dump(mode="json")
            },
            inputs=[]  # <--- FIX: Explicitly pass an empty list here to satisfy the 422 schema check
        )
    )
    # 3. Serialize and upload the local file payload as before
    from obi_one.core.serialization_constants import COORDINATE_CONFIG_FILENAME
    local_config_file = manager.output_dir / COORDINATE_CONFIG_FILENAME
    local_config_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(local_config_file, "w", encoding="utf-8") as f:
        json.dump(lod_config.model_dump(mode="json"), f, indent=4)

    db_client.upload_file(
        entity_id=config_entity.id,
        entity_type=models.TaskConfig,
        file_path=local_config_file,
        asset_label="task_config",
        file_content_type="application/json",  # <--- FIX: Add this keyword argument
    )

    return config_entity

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    domains = {
	"cell_a": {
            "virtual_lab_id": "bf7d398c-b812-408a-a2ee-098f633f7798",
            "project_id": "100a9a8a-5229-4f3d-aef3-6a4184c59e74",
	}
    }
    # Initialize the RemoteTaskManager pointing to the proper configuration variant string
    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.mesh_lod_generation,  # Change back to the pure enum/string "mesh_lod_generation"
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=domains,
    )
    
    # Generate the config entity upstream
    config = create_config(manager)
    L.info("Config Entity Created: %s", config)
    
    # 3. Remote launch and execution tracking
    import httpx

    try:
        manager.run_task(
            config_id=config.id,
            activity_type=models.TaskActivity,
            check_mode="obi-one",
        )
    except httpx.HTTPStatusError as e:
        L.error("Launch System rejected request with status 422.")
        try:
            # Print the detailed validation errors returned by the server
            L.error("Validation details: %s", e.response.json())
        except Exception:
            L.error("Response body text: %s", e.response.text)
        raise e

    L.info("Task submitted")
