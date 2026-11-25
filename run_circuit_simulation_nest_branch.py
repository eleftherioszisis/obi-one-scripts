"""Cloud end-to-end NEST test against an obi-one service running a branch.

1. ``circuit_simplification`` (``adex_nest``) of a staging circuit, launched through the
   branch service. The worker registers a SONATA-extension ``Circuit`` with
   ``target_simulator=NEST``.
2. A NEST ``Simulation`` of that circuit, registered here in the same shape the NEURON
   simulation generation registers (``SimulationCampaign`` + ``Simulation`` +
   ``SimulationGeneration``, assets ``sonata_simulation_config`` / ``custom_node_sets`` /
   ``replay_spikes``) and with a SONATA config shaped like the one the NEURON generator writes:
   Poisson ``synapse_replay`` into every virtual population, a somatic ``linear`` current clamp
   and a soma voltage report. obi-one has no NEST simulation-generation config yet.
3. The Simulation is estimated and launched through the branch service as the UI does, with
   the generic ``circuit_simulation`` task type, which the service must dispatch to
   ``circuit_simulation_nest_machine``. The worker registers a ``SimulationResult`` (spike
   report + voltage reports).
4. The result assets are downloaded and checked with libsonata.

Point OBI_ONE_URL at the branch service (default http://127.0.0.1:8101, see
serve_obi_one_branch.py). ACCESS_TOKEN is used when set, else an ``obi_auth`` staging token.

Usage::

    python run_circuit_simulation_nest_branch.py
    python run_circuit_simulation_nest_branch.py --simplified-circuit-id <uuid>
    python run_circuit_simulation_nest_branch.py --simulation-id <uuid>   # relaunch only
"""

import argparse
import json
import logging
import os
import shutil
import time
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

import entitysdk
import h5py
import httpx
import libsonata
import numpy as np
from entitysdk import models
from entitysdk.staging.circuit import stage_circuit
from entitysdk.token_manager import TokenFromFunction
from entitysdk.types import AssetLabel, ContentType
from obi_auth import get_token

from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST
from obi_one.core.info import Info
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.algorithms.models import (
    ALGORITHM_BLOCK_CLASSES,
)
from obi_one.scientific.tasks.circuit_simplification.config import (
    CircuitSimplificationScanConfig,
)
from obi_one.types import TaskType

L = logging.getLogger("nest_e2e")

OBI_ONE_URL = os.environ.get("OBI_ONE_URL", "http://127.0.0.1:8101")
OUTPUT_DIR = Path(__file__).parent / "out/circuit_simulation_nest_branch/cloud"

# Same staging circuit as run_circuit_simplification_nest_e2e.py
CIRCUIT_ID = os.environ.get("CIRCUIT_ID", "82bae430-aff9-46b1-8ce7-e616bc733ed2")
ALGORITHM = os.environ.get("SIMPLIFICATION_ALGORITHM", "adex_nest")

TSTOP = 500.0
DT = 0.1
RANDOM_SEED = 1
INPUT_RATE_HZ = 10.0
CLAMP_AMPLITUDE_NA = 0.3
CLAMP_DELAY = 100.0
CLAMP_DURATION = 300.0
REPORT_NAME = "SomaVoltageRecording"
CLAMP_NAME = "CurrentClamp"
SIMULATED_NODE_SET = "AllSimulatedNeurons"
INPUT_SPIKES_FILENAME = "input_spikes.h5"
POLL_SECONDS = 15
TERMINAL_JOB_STATES = {"done", "error", "failed", "cancelled", "timeout", "completed"}


def get_db_client() -> entitysdk.Client:
    return entitysdk.Client(
        environment="staging",
        project_context=entitysdk.ProjectContext(
            virtual_lab_id=LAB_ID_STAGING_TEST, project_id=PROJECT_ID_STAGING_TEST
        ),
        token_manager=TokenFromFunction(partial(get_token, environment="staging")),
    )


def obi_one_headers() -> dict:
    token = os.environ.get("ACCESS_TOKEN") or get_token(environment="staging")
    return {
        "Authorization": f"Bearer {token}",
        "virtual-lab-id": str(LAB_ID_STAGING_TEST),
        "project-id": str(PROJECT_ID_STAGING_TEST),
    }


def launch_and_wait(
    task_type: TaskType,
    config_id: UUID,
    log_name: str,
    *,
    expected_task_type: TaskType | None = None,
) -> dict:
    """Estimate and submit through the branch service, poll quietly, save the full job logs.

    The service may map *task_type* to another one (``circuit_simulation`` is mapped from the
    simulation's ``target_simulator``); both the estimate and the launch must resolve to
    *expected_task_type*, which defaults to *task_type*.
    """
    expected_task_type = expected_task_type or task_type
    payload = {"task_type": str(task_type), "config_id": str(config_id)}
    with httpx.Client(base_url=OBI_ONE_URL, headers=obi_one_headers(), timeout=120) as http:
        response = http.post("/declared/task/estimate", json=payload, timeout=300)
        if response.is_error:
            raise RuntimeError(f"Estimate failed {response.status_code}: {response.text}")
        estimate = response.json()
        L.info("Estimate for %s: %s", task_type, estimate)
        if estimate["task_type"] != expected_task_type:
            raise RuntimeError(f"Estimate resolved {task_type} to {estimate['task_type']}")

        response = http.post("/declared/task/launch", json=payload, timeout=300)
        if response.is_error:
            raise RuntimeError(f"Launch failed {response.status_code}: {response.text}")
        submitted = response.json()
        L.info("Submitted %s: %s", task_type, submitted)
        if submitted["task_type"] != expected_task_type:
            raise RuntimeError(f"Launch resolved {task_type} to {submitted['task_type']}")
        job_id = submitted["job_id"]
        status = None
        while True:
            http.headers.update(obi_one_headers())
            job = http.get(f"/declared/task/{job_id}").json()
            if job.get("status") != status:
                status = job.get("status")
                L.info("Job %s status: %s", job_id, status)
            if status in TERMINAL_JOB_STATES or status not in {"created", "pending", "running"}:
                break
            time.sleep(POLL_SECONDS)

    lines = []
    for entry in (job.get("logs") or {}).get("stream", []):
        kind = entry.get("message_type")
        lines.append(f"[{kind}] {entry.get(kind) or entry}")
    (OUTPUT_DIR / f"{log_name}.log").write_text("\n".join(lines))
    L.info("Job logs: %s", OUTPUT_DIR / f"{log_name}.log")
    if status != "done":
        print("\n".join(lines[-80:]))
        raise RuntimeError(f"{task_type} job {job_id} ended with status {status!r}")
    return {
        "requested_task_type": str(task_type),
        "launched_task_type": submitted["task_type"],
        "estimate": estimate,
        "job_id": job_id,
        "activity_id": submitted.get("activity_id"),
        "status": status,
    }


def simplify(db_client: entitysdk.Client, summary: dict) -> UUID:
    parent = db_client.get_entity(entity_id=CIRCUIT_ID, entity_type=models.Circuit)
    summary["input_circuit"] = entity_row(parent)
    scan_config = CircuitSimplificationScanConfig(
        info=Info(
            campaign_name="NEST branch e2e simplification",
            campaign_description=f"Simplify {CIRCUIT_ID} with '{ALGORITHM}' for NEST",
        ),
        initialize=CircuitSimplificationScanConfig.Initialize(
            circuit=CircuitFromID(id_str=CIRCUIT_ID)
        ),
        algorithm=ALGORITHM_BLOCK_CLASSES[ALGORITHM](),
    )
    grid_scan = GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=OUTPUT_DIR / "simplification",
    )
    grid_scan.execute(db_client=db_client)
    config = grid_scan.single_configs[0].single_entity
    summary["simplification_config"] = entity_row(config)

    job = launch_and_wait(TaskType.circuit_simplification, config.id, "simplification_job")
    activity = db_client.get_entity(entity_id=job["activity_id"], entity_type=models.TaskActivity)
    summary["simplification_activity"] = activity_row(activity)
    if not activity.generated:
        raise RuntimeError(f"Simplification activity {activity.id} generated nothing")
    return activity.generated[0].id


def write_simulation_inputs(circuit_config_path: Path, out_dir: Path) -> int:
    """Write a NEURON-generator-shaped SONATA simulation config for a NEST circuit."""
    circuit = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    virtual_pops, simulated_pops, number_neurons = [], [], 0
    for name in sorted(circuit.node_populations):
        if circuit.node_population_properties(name).type == "virtual":
            virtual_pops.append(name)
        else:
            simulated_pops.append(name)
            number_neurons += circuit.node_population(name).size
    L.info("Virtual populations %s, simulated %s", virtual_pops, simulated_pops)

    rng = np.random.default_rng(RANDOM_SEED)
    node_sets = {SIMULATED_NODE_SET: {"population": simulated_pops}}
    inputs = {}
    if virtual_pops:
        with h5py.File(out_dir / INPUT_SPIKES_FILENAME, "w") as h5:
            spikes = h5.create_group("spikes")
            for name in virtual_pops:
                size = circuit.node_population(name).size
                counts = rng.poisson(INPUT_RATE_HZ * TSTOP / 1000.0, size)
                node_ids = np.repeat(np.arange(size, dtype=np.uint64), counts)
                times = rng.uniform(0.0, TSTOP, node_ids.size)
                order = np.argsort(times)
                group = spikes.create_group(name)
                group.create_dataset("node_ids", data=node_ids[order])
                group.create_dataset("timestamps", data=times[order]).attrs["units"] = "ms"
        # Read it back the way the simulators do, before it is uploaded.
        reader = libsonata.SpikeReader(str(out_dir / INPUT_SPIKES_FILENAME))
        for name in virtual_pops:
            reader[name].get_dict()
        replay_set = "AllSimulatedNeuronsReplay"
        node_sets[replay_set] = {"population": simulated_pops}
        inputs["PoissonReplay"] = {
            "input_type": "spikes",
            "module": "synapse_replay",
            "delay": 0.0,
            "duration": TSTOP,
            "node_set": replay_set,
            "spike_file": INPUT_SPIKES_FILENAME,
        }
    inputs[CLAMP_NAME] = {
        "module": "linear",
        "input_type": "current_clamp",
        "amp_start": CLAMP_AMPLITUDE_NA,
        "delay": CLAMP_DELAY,
        "duration": CLAMP_DURATION,
        "node_set": SIMULATED_NODE_SET,
        "represents_physical_electrode": False,
    }
    simulation_config = {
        "version": 2.4,
        "target_simulator": "NEST",
        "network": "circuit_config.json",
        "node_sets_file": "node_sets.json",
        "run": {"dt": DT, "random_seed": RANDOM_SEED, "tstop": TSTOP},
        "conditions": {"v_init": -80.0},
        "output": {"output_dir": "output", "spikes_file": "spikes.h5"},
        "inputs": inputs,
        "reports": {
            REPORT_NAME: {
                "cells": SIMULATED_NODE_SET,
                "sections": "soma",
                "type": "compartment",
                "compartments": "center",
                "variable_name": "v",
                "unit": "mV",
                "dt": DT,
                "start_time": 0.0,
                "end_time": TSTOP,
            }
        },
    }
    (out_dir / "node_sets.json").write_text(json.dumps(node_sets, indent=2))
    (out_dir / "simulation_config.json").write_text(json.dumps(simulation_config, indent=2))
    return number_neurons


def register_simulation(db_client: entitysdk.Client, circuit: models.Circuit, summary: dict):
    config_dir = OUTPUT_DIR / "simulation_config"
    config_dir.mkdir(parents=True)
    staged = stage_circuit(db_client, model=circuit, output_dir=OUTPUT_DIR / "staged_circuit")
    number_neurons = write_simulation_inputs(Path(staged), config_dir)

    campaign = db_client.register_entity(
        models.SimulationCampaign(
            name="NEST branch e2e simulation campaign",
            description=f"Poisson replay + current clamp on {circuit.name}",
            entity_id=circuit.id,
            scan_parameters={},
        )
    )
    simulation = db_client.register_entity(
        models.Simulation(
            name="Simulation 0",
            description=f"{TSTOP} ms NEST simulation of {circuit.name}",
            simulation_campaign_id=campaign.id,
            entity_id=circuit.id,
            scan_parameters={},
            number_neurons=number_neurons,
        )
    )
    uploads = [
        ("node_sets.json", ContentType.application_json, AssetLabel.custom_node_sets),
        (INPUT_SPIKES_FILENAME, ContentType.application_x_hdf5, AssetLabel.replay_spikes),
        ("simulation_config.json", ContentType.application_json, AssetLabel.sonata_simulation_config),
    ]
    for file_name, content_type, label in uploads:
        if (config_dir / file_name).exists():
            db_client.upload_file(
                entity_id=simulation.id,
                entity_type=models.Simulation,
                file_path=config_dir / file_name,
                file_content_type=content_type,
                asset_label=label,
            )
    generation = db_client.register_entity(
        models.SimulationGeneration(
            start_time=datetime.now(UTC), used=[campaign], generated=[simulation]
        )
    )
    summary["simulation_campaign"] = entity_row(campaign)
    summary["simulation"] = entity_row(
        db_client.get_entity(entity_id=simulation.id, entity_type=models.Simulation)
    )
    summary["simulation_generation"] = activity_row(generation)
    return simulation


def check_results(db_client: entitysdk.Client, activity_id: UUID, summary: dict) -> None:
    activity = db_client.get_entity(entity_id=activity_id, entity_type=models.SimulationExecution)
    summary["simulation_execution"] = activity_row(activity)
    if len(activity.generated or []) != 1:
        raise RuntimeError(f"Expected one generated SimulationResult, got {activity.generated}")
    result = db_client.get_entity(
        entity_id=activity.generated[0].id, entity_type=models.SimulationResult
    )
    summary["simulation_result"] = entity_row(result)
    summary["simulation_result"]["simulation_id"] = str(result.simulation_id)

    results_dir = OUTPUT_DIR / "results"
    results_dir.mkdir()
    checks = {}
    for asset in result.assets:
        path = db_client.download_file(
            entity_id=result.id,
            entity_type=models.SimulationResult,
            asset_id=asset.id,
            output_path=results_dir / asset.path,
        )
        if asset.label == AssetLabel.spike_report:
            reader = libsonata.SpikeReader(str(path))
            for pop in reader.get_population_names():
                pairs = np.asarray(reader[pop].get(), dtype=float).reshape(-1, 2)
                node_ids, times = pairs[:, 0], pairs[:, 1]
                checks[f"spikes:{pop}"] = {
                    "n_spikes": int(len(times)),
                    "n_active_nodes": int(np.unique(node_ids).size),
                    "t_max": float(np.max(times)) if len(times) else None,
                    "sorting": str(reader[pop].sorting),
                }
        elif asset.label == AssetLabel.voltage_report:
            reader = libsonata.SomaReportReader(str(path))
            for pop in reader.get_population_names():
                data = reader[pop].get()
                values = np.asarray(data.data)
                checks[f"voltage:{asset.path}:{pop}"] = {
                    "shape": list(values.shape),
                    "times": [float(data.times[0]), float(data.times[-1])],
                    "units": [reader[pop].time_units, reader[pop].data_units],
                    "v_range": [float(values.min()), float(values.max())],
                }
    summary["result_checks"] = checks


def entity_row(entity) -> dict:
    row = {"type": type(entity).__name__, "id": str(entity.id), "name": getattr(entity, "name", None)}
    for attr in ("target_simulator", "number_neurons", "number_synapses", "entity_id"):
        if (value := getattr(entity, attr, None)) is not None:
            row[attr] = str(value)
    if assets := getattr(entity, "assets", None):
        row["assets"] = sorted(f"{a.label}:{a.path}:{a.content_type}" for a in assets)
    return row


def activity_row(activity) -> dict:
    return {
        "type": type(activity).__name__,
        "id": str(activity.id),
        "status": str(getattr(activity, "status", None)),
        "used": [f"{type(u).__name__}:{u.id}" for u in activity.used or []],
        "generated": [f"{type(g).__name__}:{g.id}" for g in activity.generated or []],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--simplified-circuit-id", help="Skip simplification, use this circuit.")
    parser.add_argument("--simulation-id", help="Skip registration, relaunch this Simulation.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    db_client = get_db_client()
    summary: dict = {"obi_one_url": OBI_ONE_URL}
    try:
        if args.simulation_id:
            simulation_id = UUID(args.simulation_id)
        else:
            if args.simplified_circuit_id:
                circuit_id = UUID(args.simplified_circuit_id)
            else:
                circuit_id = simplify(db_client, summary)
            circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)
            summary["simplified_circuit"] = entity_row(circuit)
            if circuit.target_simulator != "NEST":
                raise RuntimeError(f"Circuit {circuit.id} targets {circuit.target_simulator}")
            simulation_id = register_simulation(db_client, circuit, summary).id

        # Launch as the UI does: the generic circuit_simulation, which the service must
        # dispatch to the NEST task from the simulation's target_simulator.
        job = launch_and_wait(
            TaskType.circuit_simulation,
            simulation_id,
            "simulation_job",
            expected_task_type=TaskType.circuit_simulation_nest_machine,
        )
        summary["simulation_job"] = job
        check_results(db_client, UUID(job["activity_id"]), summary)
    finally:
        (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
