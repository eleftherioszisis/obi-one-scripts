"""create obi form"""
# have to install the following branches:
# https://github.com/openbraininstitute/obi-one/tree/simulate-icm

import json
import pathlib
import subprocess
from datetime import datetime, UTC

from entitysdk import models

from obi_one.core.info import Info
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.blocks.ion_channel_model import IonChannelModelWithConductance
from obi_one.scientific.blocks.recording import (
    IonChannelVariableRecording,
    SomaVoltageRecording,
)
from obi_one.scientific.blocks.stimuli.stimulus import (
    SEClampSomaticStimulus,
    ConstantCurrentClampSomaticStimulus,
)
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationScanConfig,
)

from obi_one.scientific.tasks.ion_channel_model_simulation import (
    IonChannelModelSimulationTask,
    IonChannelModelSimulationExecutionConfig,
)

import obi_one as obi

import logging

logging.basicConfig(level=logging.INFO)


def create_activity(
    *,
    client,
    activity_type,
    activity_status: str = "created",  # TODO: Use ActivityStatus when available
    used,
):
    """Creates and registers an activity of the given type."""
    activity = activity_type(
        start_time=datetime.now(UTC),
        used=used,
        status=activity_status,
        authorized_public=False,
    )
    activity = client.register_entity(activity)
    return activity


# simulate = False
simulate = True
local = False

output_root = "./out"
subprocess.run(["rm", "-rf", output_root])
subprocess.run(["rm", "-rf", "arm64"])
pathlib.Path(output_root).mkdir(exist_ok=True)

# ion channel models
id_1 = "8c60dccf-8dfc-48a4-a2db-358b9643e3fb"  # K_TST staging


# most simple case
sim_conf = IonChannelModelSimulationScanConfig(
    initialize=IonChannelModelSimulationScanConfig.Initialize(
        simulation_length=200,
        temperature=35,
        v_init=-80,
        random_seed=1,
    ),
    info=Info(
        campaign_name="Ion Channel Simulation Campaign Test 001",
        campaign_description="Test",
    ),
    ion_channel_models={
        "icm1": IonChannelModelWithConductance(
            ion_channel_model=IonChannelModelFromID(id_str=id_1),
            conductance=0.12,
        )
    },
    stimuli={
        # do not use SEClamp for now
        "seclamp1": SEClampSomaticStimulus(
            duration=100,
            initial_voltage=-80,
            step_voltage=0,
            step_duration=40,
            neuron_set=None,
            timestamp_offset=20,
        )
        # "step1": ConstantCurrentClampSomaticStimulus(
        #     duration=100,
        #     neuron_set=None,
        #     timestamp_offset=20,
        #     amplitude=0.1,
        # )
    },
    recordings={
        # do not use current recordings for now
        # "rec1": IonChannelVariableRecording(
        #     variable_name={
        #         "variable": "ik",
        #         "unit": "mA/cm2",
        #     },
        #     neuron_set=None,
        #     dt=0.1,
        # )
        "rec_voltage": SomaVoltageRecording(
            neuron_set=None,
            dt=0.1,
        )
    },
    timestamps={},
)

with open(f"./{output_root}/simulate_ion_channel_scan_config.json", "w") as f:
    f.write(sim_conf.model_dump_json(indent=4))

# all of the following can be done in the task manager script

# validate
validated_sim_conf = sim_conf.validated_config()

# create the client
from entitysdk import Client, ProjectContext
from obi_auth import get_token


project_id = "54aa306a-b7db-4087-82ec-c6dec1617df4"
virtual_lab_id = "594fd60d-7a38-436f-939d-500feaa13bba"
public_virtual_lab_id = "a98b7abc-fc46-4700-9e3d-37137812c730"  # for staging AND prod
public_project_id = "0dbced5f-cc3d-488a-8c7f-cfb8ea039dc6"  # for staging AND prod
access_token = get_token(environment="staging")
client = Client(
    project_context=ProjectContext(
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        # project_id=public_project_id,
        # virtual_lab_id=public_virtual_lab_id,
    ),
    environment="staging",
    token_manager=access_token,
)

grid_scan = obi.GridScanGenerationTask(
    form=validated_sim_conf,
    coordinate_directory_option="ZERO_INDEX",
    output_root=output_root,
)
# grid_scan = obi.GridScanGenerationTask(form=validated_sim_conf, coordinate_directory_option="ZERO_INDEX", output_root=temp_dir)
grid_scan.multiple_value_parameters(display=True)
grid_scan.coordinate_parameters(display=True)
grid_scan.execute(db_client=client)
obi.run_tasks_for_generated_scan(grid_scan, db_client=client)


campaign_id = grid_scan.form.campaign.id

entity = (
    client.search_entity(
        entity_type=models.SimulationGeneration, query={"used__id": str(campaign_id)}
    )
    .one()
    .generated[0]
)
# entity_id = '6e390cd2-1cd8-4e4c-bee4-7f992ac82828'
entity_id = entity.id
single_config_entity = client.get_entity(
    entity_id=entity_id, entity_type=models.Simulation
)

activity = create_activity(
    client=client,
    activity_type=models.SimulationExecution,
    activity_status="pending",
    used=[single_config_entity],
)


config = IonChannelModelSimulationExecutionConfig(coordinate_output_root=output_root)
config.single_entity = single_config_entity

task = IonChannelModelSimulationTask(config=config)
# task.execute(db_client=client, execution_activity_id=None)
task.execute(db_client=client, execution_activity_id=activity.id)
