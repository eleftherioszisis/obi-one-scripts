import os
import httpx
import json
import logging
import webbrowser
from pathlib import Path
from obi_one.types import TaskType
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType
import obi_one

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

domains = {
    "cell_a": {
        "virtual_lab_id": obi_one.LAB_ID_STAGING_TEST,
        "project_id": obi_one.PROJECT_ID_STAGING_TEST,
    },
}

# cell_a
#CONFIG_ID = "95817298-631a-4c14-a5a4-f0109a632d0f"
#CONFIG_ID = "24dc0545-d058-4716-ad43-3a588d40a2a1"
#CONFIG_ID = "65d9fb29-666d-49e1-bf24-c481ee9f1db2"

# cell_b
#CONFIG_ID = "3ff3ead5-1b9b-4d61-8175-3a9868f29dcd"

OUTPUT_DIR = Path(__file__).parent / "out/plasticity"
DATA_DIR = Path(__file__).parent / "input_spikes"
CIRCUIT_ID = "866e2e65-f565-49c2-86c3-f57f1ffce7ff"
CIRCUIT_NAME="nbS1-O1-plastic"
TEST_NAME = "Test plasticity sim v4"
TEST_DESCRIPTION = f"Test plasticity simulation with {CIRCUIT_NAME}"

Target_Number=("hex0", 30190)

SIMULATION_CONFIG = {
    "manifest": {
        "$CURRENT_DIR": "."
    },
    "run": {
        "dt": 0.025,
        "tstop": 1000.0,
        "random_seed": 12345
    },
    "conditions": {
        "extracellular_calcium": 1.05,
        "v_init": -80.0,
        "spike_location": "AIS",
        "mechanisms": {
            "ProbAMPANMDA_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            },
            "ProbGABAAB_EMS": {
                "init_depleted": True,
                "minis_single_vesicle": True
            },
            "GluSynapse": {
                "init_depleted": True,
                "minis_single_vesicle": True,
                "cao_CR": 1.05,
                "tau_effca_GB": 278.3177658387,
                "gamma_d_GB" : 101.5387594661,
                "gamma_p_GB" : 216.1841700668
            }
        }
    },
    "target_simulator": "CORENEURON",
    "node_set": Target_Number[0],
    "output": {
        "output_dir": "output",
        "spikes_file": "spikes.h5"
    },
    "reports": {
        "soma": {
            "cells": "hex0",
            "type": "compartment",
            "variable_name": "v",
            "unit": "mV",
            "dt": 1.0,
            "start_time": 0.0,
            "end_time": 122500.0
        },
        "rho": {
            "cells": "hex_O1ExcitatoryPlastic",
            "type": "synapse",
            "sections": "all",
            "variable_name": "GluSynapse.rho_GB",
            "unit": "nd",
            "dt": 1000.0,
            "start_time": 0.0,
            "end_time": 122500.0
        },
        "gmax_AMPA": {
            "cells": "hex_O1ExcitatoryPlastic",
            "type": "synapse",
            "sections": "all",
            "variable_name": "GluSynapse.gmax_AMPA",
            "unit": "nS",
            "dt": 10000.0,
            "start_time": 0.0,
            "end_time": 122500.0
        }
    },
    "inputs": {
        "Stimulus gExc_L1": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 2.703,
            "sd_percent": 1.081,
            "node_set": "Layer1Inhibitory"
        },
        "Stimulus gExc_L23E": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 18.018,
            "sd_percent": 7.207,
            "node_set": "Layer23Excitatory"
        },
        "Stimulus gExc_L23I": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 2.302,
            "sd_percent": 0.921,
            "node_set": "Layer23Inhibitory"
        },
        "Stimulus gExc_L4E": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 8.709,
            "sd_percent": 3.483,
            "node_set": "Layer4Excitatory"
        },
        "Stimulus gExc_L4I": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 2.803,
            "sd_percent": 1.121,
            "node_set": "Layer4Inhibitory"
        },
        "Stimulus gExc_L5E": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 16.016,
            "sd_percent": 6.406,
            "node_set": "Layer5Excitatory"
        },
        "Stimulus gExc_L5I": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 4.304,
            "sd_percent": 1.722,
            "node_set": "Layer5Inhibitory"
        },
        "Stimulus gExc_L6E": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 2.002,
            "sd_percent": 0.801,
            "node_set": "Layer6Excitatory"
        },
        "Stimulus gExc_L6I": {
            "input_type": "conductance",
            "module": "relative_ornstein_uhlenbeck",
            "delay": 250.0,
            "duration": 122500.0,
            "reversal": 0.0,
            "tau": 2.7,
            "mean_percent": 2.402,
            "sd_percent": 0.961,
            "node_set": "Layer6Inhibitory"
        },
        "VPM_spikes": {
            "input_type": "spikes",
            "module": "synapse_replay",
            "delay": 0.0,
            "duration": 122500.0,
            "spike_file": "vpm_spikes.h5",
            "node_set": "hex_O1"
            },
        "POm_spikes": {
            "input_type": "spikes",
            "module": "synapse_replay",
            "delay": 0.0,
            "duration": 122500.0,
            "spike_file": "pom_spikes.h5",
            "node_set": "hex_O1"
        }
    },
    "connection_overrides": [
        {
            "name": "plasticity",
            "source": "hex_O1Excitatory",
            "target": "hex_O1Excitatory",
            "modoverride": "GluSynapse",
            "weight": 1.0
        },
        {
            "name": "init",
            "source": "hex_O1",
            "target": "hex_O1",
            "weight": 1.0
        },
        {
            "name": "VPM_init",
            "source": "proj_Thalamocortical_VPM_Source",
            "target": "hex_O1",
            "spont_minis": 0.0,
            "weight": 1.0
        },
        {
            "name": "POm_init",
            "source": "proj_Thalamocortical_POM_Source",
            "target": "hex_O1",
            "spont_minis": 0.0,
            "weight": 1.0
        },
        {
            "name": "disconnect",
            "source": "hex_O1",
            "target": "hex_O1",
            "delay": 0.025,
            "weight": 0.0
        },
        {
            "name": "reconnect",
            "source": "hex_O1",
            "target": "hex_O1",
            "delay": 1000.0,
            "weight": 1.0
        }
    ]
}


# NODE_SETS = {
#     "All": {"population": "core"},
#     "low-odd": {"node_id": [1, 3, 5, 7]},
#     "zero": {"node_id": [0]},
#     "one": {"node_id": [1]}
# }



def create_config(manager):
    db_client = manager.db_client
    circuit_id = CIRCUIT_ID
    campaign = db_client.register_entity(entity=models.SimulationCampaign(
        name=TEST_NAME,
        description=TEST_DESCRIPTION,
        entity_id=circuit_id,
        scan_parameters={},
    ))
    simulation = db_client.register_entity(
        entity=models.Simulation(
            name=TEST_NAME,
            description=TEST_DESCRIPTION,
            simulation_campaign_id=campaign.id,
            entity_id=circuit_id,
            scan_parameters={},
            number_neurons=Target_Number[1],
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
    db_client.upload_file(
        entity_id=simulation.id,
        entity_type=models.Simulation,
        file_path=DATA_DIR / "vpm_spikes.h5",
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.replay_spikes,
    )
    db_client.upload_file(
        entity_id=simulation.id,
        entity_type=models.Simulation,
        file_path=DATA_DIR / "pom_spikes.h5",
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.replay_spikes,
    )
    return simulation



if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Consent for offline token, required for manager.run_task
    # TOKEN = os.environ["ACCESS_TOKEN"]
    # http_client = httpx.Client(
    #     base_url="https://staging.cell-a.openbraininstitute.org/api/auth-manager/v1",
    #     headers={"Authorization": f"Bearer {TOKEN}"},
    # )

    # res = http_client.get("/offline-token").raise_for_status().json()
    # webbrowser.open(res["data"]["consent_url"])
    
    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_simulation,
        subdomain="cell_a",
        obi_one_deployment="staging",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=domains,
    )
    config_id = create_config(manager).id
    L.info("Simulation: %s", config_id)

    manager.run_task(
        config_id=config_id,
        check_mode="obi-one",
        activity_type=models.SimulationExecution,
    )
