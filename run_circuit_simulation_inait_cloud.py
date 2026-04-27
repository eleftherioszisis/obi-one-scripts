import os
import httpx
import json
import logging
import webbrowser
from pathlib import Path
from obi_one.types import TaskType
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

domains = {
    "cell_a": {
        "virtual_lab_id": "84258ff5-114f-4865-9a2d-258575c23909",
        "project_id": "b3d4ac06-f636-465c-a6e6-72dd098509a1",
    },
    "cell_b": {
        "virtual_lab_id": "47280b42-f521-4343-adda-8a2aef504f0c",
        "project_id": "afa210d1-ed66-429f-b0b4-3df85e667f4d",
    },
}

# cell_a
#CONFIG_ID = "95817298-631a-4c14-a5a4-f0109a632d0f"
#CONFIG_ID = "24dc0545-d058-4716-ad43-3a588d40a2a1"
#CONFIG_ID = "65d9fb29-666d-49e1-bf24-c481ee9f1db2"

# cell_b
#CONFIG_ID = "3ff3ead5-1b9b-4d61-8175-3a9868f29dcd"

OUTPUT_DIR = Path(__file__).parent / "out/circuit_extraction/cloud"
DATA_DIR = Path(__file__).parent / "data/simulation"

TOKEN = os.environ["ACCESS_TOKEN"]

SIMULATION_CONFIG = {
  "manifest": {
    "$BASE_DIR": ".",
    "$OUTPUT_DIR": "$BASE_DIR/output"
  },
  "target_simulator": "LearningEngine",

  "run": {
    "tstart": 0.0,
    "tstop": 3000.0,
    "dt": 0.1,
    "random_seed": 1,
    "spike_threshold": -15
  },

  "conditions": {
    "celsius": 34.0,
    "v_init": -80,
    "spike_location": "soma"
  },

  "network": "nbs1_hexo_100_hex/circuit_config.json",

  "output": {
    "output_dir": "$OUTPUT_DIR",
    "spikes_file": "spikes.h5"
  },

  "inputs": {
    "spikes": {
      "input_type": "spikes",
      "module": "synapse_replay",
      "spike_file": "/home/mgevaert/src/inait-partnership/scripts/simulate-circuits/test/spikes.h5",
      "delay": 0,
      "duration": 100,
      "node_set": "All"
    },
    "Linear": {
      "input_type": "current_clamp",
      "module": "linear",
      "node_set": "All",
      "amp_start": 0.1000,
      "amp_end": 0.1000,
      "delay": 10.0,
      "duration": 2000.0
    },
    "RelativeLinear": {
      "input_type": "current_clamp",
      "module": "relative_linear",
      "node_set": "All",
      "percent_start": 20,
      "percent_end": 20,
      "delay": 500.0,
      "duration": 2000.0
    },
    "Pulse": {
        "input_type": "current_clamp",
        "module": "pulse",
        "node_set": "All",
        "frequency": 100,
        "amp_start": 2,
        "width": 1,
        "delay": 10,
        "duration": 80
    },
    "Sinusoidal": {
        "input_type": "current_clamp",
        "module": "sinusoidal",
        "node_set": "All",
        "frequency": 24,
        "amp_start": 0.2,
        "dt": 0.25,
        "delay": 10,
        "duration": 80
    },
    "Subthreshold": {
        "input_type": "current_clamp",
        "module": "subthreshold",
        "node_set": "All",
        "percent_less": 80,
        "delay": 10,
        "duration": 80
    }
  },
  "todo": {
      "OrnsteinUhlenbeck": {
          "input_type": "current_clamp",
          "module": "ornstein_uhlenbeck",
          "node_set": "one",
          "delay": 50,
          "duration": 200,
          "tau": 2.8,
          "reversal": 10,
          "mean": 50,
          "sigma": 5
      },
      "RelativeOrnsteinUhlenbeck": {
          "input_type": "current_clamp",
          "module": "relative_ornstein_uhlenbeck",
          "node_set": "one",
          "delay": 50,
          "duration": 200,
          "tau": 2.8,
          "mean_percent": 70,
          "sd_percent": 10,
          "random_seed": 230522
      }
  },
  "todo_impl": {
    "Hyperpolarizing": {
        "input_type": "current_clamp",
        "module": "hyperpolarizing",
        "node_set": "All",
        "delay": 0,
        "duration": 1000
    },
    "Noise": {
        "input_type": "current_clamp",
        "module": "noise",
        "node_set": "All",
        "mean_percent": 0.01,
        "mean": None,
        "variance": 0.001,
        "delay": 1.0,
        "duration": 2000.0
    },
    "ShotNoise": {
        "input_type": "current_clamp",
        "module": "shot_noise",
        "node_set": "one",
        "delay": 0,
        "duration": 1000,
        "decay_time": 4,
        "reversal": 10,
        "rise_time": 0.4,
        "amp_mean": 70,
        "amp_var": 40,
        "rate": 4
    },
    "RelativeShotNoise": {
        "input_type": "current_clamp",
        "module": "relative_shot_noise",
        "node_set": "one",
        "delay": 0,
        "duration": 1000,
        "decay_time": 4,
        "rise_time": 0.4,
        "mean_percent": 70,
        "sd_percent": 40,
        "random_seed": 230522
    },
    "AbsoluteShotNoise": {
        "input_type": "conductance",
        "module": "absolute_shot_noise",
        "node_set": "one",
        "delay": 0,
        "duration": 1000,
        "decay_time": 4,
        "reversal": 10,
        "rise_time": 0.4,
        "relative_skew": 0.1,
        "mean": 50,
        "sigma": 5,
        "represents_physical_electrode": True
    }
  },
  "reports": {
      "soma_report": {
        "cells": "All",
        "sections": "soma",
        "type": "compartment",
        "compartments": "center",
        "variable_name": "v",
        "unit": "mV",
        "dt": 0.1,
        "start_time": 0.0,
        "end_time": 3000.0
      }
    },
  "node_sets_file":"./node_sets.json"
}

NODE_SETS = {
    "All": {"population": "core"},
    "low-odd": {"node_id": [1, 3, 5, 7]},
    "zero": {"node_id": [0]},
    "one": {"node_id": [1]}
}


def create_config(manager):
    db_client = manager.db_client
    circuit_id = "617ec95c-09c6-4a6b-a97d-3eafc86826c3"
    campaign = db_client.register_entity(entity=models.SimulationCampaign(
        name="Test Campaign INAIT",
        description="Test Campaign for INAIT circuit `nbs1_hexo_100_hex`",
        entity_id=circuit_id,
        scan_parameters={},
    ))
    simulation = db_client.register_entity(
        entity=models.Simulation(
            name="Test Simulation INAIT",
            description="Test Simulation for INAIT circuit `nbs1_hexo_100_hex`",
            simulation_campaign_id=campaign.id,
            entity_id=circuit_id,
            scan_parameters={},
            number_neurons=100,
        )
    )
    db_client.upload_content(
        entity_id=simulation.id,
        entity_type=models.Simulation,
        file_content=json.dumps(SIMULATION_CONFIG),
        file_name="simulation_config.json",
        file_content_type=ContentType.application_json,
        asset_label=AssetLabel.sonata_simulation_config,
    )
    db_client.upload_content(
        entity_id=simulation.id,
        entity_type=models.Simulation,
        file_name="node_sets.json",
        file_content=json.dumps(NODE_SETS),
        file_content_type=ContentType.application_json,
        asset_label=AssetLabel.custom_node_sets,
    )
    db_client.upload_file(
        entity_id=simulation.id,
        entity_type=models.Simulation,
        file_path=DATA_DIR / "spikes.h5",
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.replay_spikes,

    )
    return simulation



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
    #config_id = create_config(manager).id
    config_id = "1ae8ed54-b185-48f7-ae9f-4041f9c6e78c"
    L.info("Simulation: %s", config_id)

    manager.run_task(
        config_id=config_id,
        check_mode="job",
        activity_type=models.SimulationExecution,
    )
