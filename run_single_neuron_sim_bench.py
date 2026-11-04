"""Benchmark run of a single-neuron simulation on staging via the local obi-one service.

Mirrors run_single_neuron_sim.py but points at a config that exists on staging, so the
per-stage timings can be compared against the breakdown in
prod-circuit-simulation#231 (scheduling, deps, stage circuit, compile mods, simulate).
"""

import logging
from pathlib import Path

from obi_one.types import TaskType

from utils import RemoteTaskManager

L = logging.getLogger(__name__)

# Public MEModelSimulationSingleConfig on staging: tstop=1000ms, dt=0.025
CONFIG_ID = "837508fc-8c91-43e3-a20e-ff4e584c587a"
OUTPUT_DIR = Path(__file__).parent / "out/single_neuron_sim_bench/cloud"


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

    manager.run_task(config_id=CONFIG_ID, check_mode="obi-one")
