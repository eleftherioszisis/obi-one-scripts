"""Benchmark the VPM_TC me-model (the cell behind jdcourcol's breakdown in
prod-circuit-simulation#231) as a single-neuron simulation on staging.

Reproduces the workload of simulation config 9f79b01e-55ea-40e8-8b97-eaa151bef4ee:
  me-model  MEM__jy180314_B_idA__dNAD_ltb_VPM_TC (public)
  tstop     1000 ms
  stimulus  constant somatic current clamp, 200 ms, amplitude 0.1
"""

import logging
from pathlib import Path

import obi_one as obi
from obi_one.types import TaskType

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

MEMODEL_ID = "9f521816-d2f5-4257-bf77-7da1de301063"  # VPM_TC, public on staging
SIM_DURATION = 1000.0
CLAMP_DURATION = 200.0
CLAMP_AMPLITUDE = 0.1

OUTPUT_DIR = Path(__file__).parent / "out/single_neuron_sim_vpmtc/cloud"


def create_config(manager):
    db_client = manager.db_client

    sim_conf = obi.MEModelSimulationScanConfig.empty_config()

    sim_conf.set(
        obi.Info(
            campaign_name="VPM_TC single neuron benchmark",
            campaign_description="Reproduces the VPM_TC single-neuron workload for timing analysis",
        ),
        name="info",
    )

    timestamps = obi.RegularTimestamps(
        start_time=0.0,
        number_of_repetitions=1,
        interval=SIM_DURATION,
    )
    sim_conf.add(timestamps, name="Timestamps")

    sim_conf.add(
        obi.ConstantCurrentClampSomaticStimulus(
            timestamps=timestamps.ref,
            duration=CLAMP_DURATION,
            amplitude=CLAMP_AMPLITUDE,
        ),
        name="CurrentClampInput",
    )

    sim_conf.set(
        obi.MEModelSimulationScanConfig.Initialize(
            circuit=obi.MEModelFromID(id_str=MEMODEL_ID),
            simulation_length=SIM_DURATION,
        ),
        name="initialize",
    )

    validated = sim_conf.validated_config()

    grid_scan = obi.GridScanGenerationTask(
        form=validated,
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.execute(db_client=db_client)

    # Generates the SONATA simulation_config.json asset. Without this the execution task
    # fails in stage_simulation with "Iterable is empty." (no sonata_simulation_config asset).
    obi.run_tasks_for_generated_scan(grid_scan, db_client=db_client)

    return grid_scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.single_neuron_simulation_execution,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
    )

    config = create_config(manager)
    L.info("CONFIG_ID=%s", config.id)
    print(f"CONFIG_ID={config.id}", flush=True)

    manager.run_task(config_id=config.id, check_mode="obi-one")
