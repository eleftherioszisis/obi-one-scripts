"""End-to-end: simplify a staging circuit to NEST, register it, simulate it with NEST, register results.

Runs the obi-one tasks in-process (the same entry point the launch-system worker uses,
``obi_one.core.run_tasks.run_task_type``) against the staging entitycore, in the staging
test virtual lab / project, authenticating with ``obi_auth``.

Stages:
1. Circuit simplification (``TaskType.circuit_simplification``) with a NEST point-neuron
   algorithm. Registers the campaign/config ``TaskConfig`` entities, a
   ``circuit_simplification__execution`` ``TaskActivity`` and the simplified ``Circuit``
   (SONATA-extension NEST format, ``target_simulator=NEST``).
2. NEST simulation (``TaskType.circuit_simulation_nest_machine``). obi-one has no NEST
   simulation-generation config yet, so the ``SimulationCampaign`` / ``Simulation`` /
   ``SimulationGeneration`` entities are registered here directly, with a SONATA
   simulation config that replays Poisson spikes into every virtual population. A
   ``SimulationExecution`` activity is created and the task registers the spike report as a
   ``SimulationResult``.

Requires obi-one with the NEST support (openbraininstitute/obi-one#1172), libsonata with
NEST support (openbraininstitute/libsonata#75) and sonata-simplify with the
SONATA-extension NEST export (openbraininstitute/sonata-simplify#27).

Usage::

    python run_circuit_simplification_nest_e2e.py
    # Reuse an already simplified NEST circuit and only run the simulation stage:
    python run_circuit_simplification_nest_e2e.py --simplified-circuit-id <uuid>
"""

import argparse
import contextlib
import json
import logging
import shutil
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from uuid import UUID

import entitysdk
import h5py
import libsonata
import numpy as np
from entitysdk import models
from entitysdk.staging.circuit import stage_circuit
from entitysdk.token_manager import TokenFromFunction
from entitysdk.types import ActivityStatus, AssetLabel, ContentType, TaskActivityType
from obi_auth import get_token

from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST
from obi_one.core.info import Info
from obi_one.core.run_tasks import run_task_type
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.db_sdk import db_sdk
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.tasks.circuit_simplification.algorithms.models import (
    ALGORITHM_BLOCK_CLASSES,
)
from obi_one.scientific.tasks.circuit_simplification.config import (
    CircuitSimplificationScanConfig,
)
from obi_one.types import TaskType

L = logging.getLogger(__name__)

CIRCUIT_ID = "82bae430-aff9-46b1-8ce7-e616bc733ed2"
ALGORITHM = "adex_nest"
OUTPUT_DIR = Path(__file__).parent / "out/circuit_simplification_nest_e2e"

TSTOP = 1000.0
DT = 0.1
INPUT_RATE_HZ = 5.0
RANDOM_SEED = 1
INPUT_SPIKES_FILENAME = "input_spikes.h5"


def get_db_client() -> entitysdk.Client:
    return entitysdk.Client(
        environment="staging",
        project_context=entitysdk.ProjectContext(
            virtual_lab_id=LAB_ID_STAGING_TEST,
            project_id=PROJECT_ID_STAGING_TEST,
        ),
        token_manager=TokenFromFunction(partial(get_token, environment="staging")),
    )


def run_tracked_task(
    db_client: entitysdk.Client,
    *,
    task_type: TaskType,
    config_entity: models.Entity,
    activity: models.Activity,
    scan_output_root: Path,
) -> models.Activity:
    """Run a task as the launch-system worker does: running -> execute -> done/error."""
    activity_type = type(activity)
    db_sdk.update_activity_status(
        client=db_client,
        activity_id=activity.id,
        activity_type=activity_type,
        status=ActivityStatus.running,
    )
    try:
        run_task_type(
            task_type=task_type,
            entity_type=type(config_entity),
            entity_id=str(config_entity.id),
            scan_output_root=str(scan_output_root),
            db_client=db_client,
            entity_cache=True,
            execution_activity_id=str(activity.id),
        )
    except Exception:
        db_sdk.finalize_activity(
            client=db_client,
            activity_id=activity.id,
            activity_type=activity_type,
            status=ActivityStatus.error,
        )
        raise
    db_sdk.finalize_activity(
        client=db_client,
        activity_id=activity.id,
        activity_type=activity_type,
        status=ActivityStatus.done,
    )
    return db_client.get_entity(entity_id=activity.id, entity_type=activity_type)


def simplify(db_client: entitysdk.Client, output_dir: Path, summary: dict) -> UUID:
    parent = db_client.get_entity(entity_id=CIRCUIT_ID, entity_type=models.Circuit)
    summary["input_circuit"] = _entity_row(parent)

    scan_config = CircuitSimplificationScanConfig(
        info=Info(
            campaign_name="NEST e2e simplification",
            campaign_description=f"Simplify circuit {CIRCUIT_ID} with '{ALGORITHM}' for NEST",
        ),
        initialize=CircuitSimplificationScanConfig.Initialize(
            circuit=CircuitFromID(id_str=CIRCUIT_ID),
        ),
        algorithms={ALGORITHM: ALGORITHM_BLOCK_CLASSES[ALGORITHM]()},
    )
    grid_scan = GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=output_dir / "simplification",
    )
    grid_scan.execute(db_client=db_client)

    campaign = grid_scan.form.campaign
    config = grid_scan.single_configs[0].single_entity
    summary["simplification_campaign"] = _entity_row(campaign)
    summary["simplification_config"] = _entity_row(config)

    activity = db_sdk.create_generic_activity(
        client=db_client,
        used=[config],
        activity_status=ActivityStatus.pending,
        activity_type=TaskActivityType.circuit_simplification__execution,
    )
    activity = run_tracked_task(
        db_client,
        task_type=TaskType.circuit_simplification,
        config_entity=config,
        activity=activity,
        scan_output_root=output_dir / "simplification_run",
    )
    summary["simplification_activity"] = _activity_row(activity)

    if not activity.generated:
        msg = f"Simplification activity {activity.id} generated no circuit"
        raise RuntimeError(msg)
    return activity.generated[0].id


def write_simulation_inputs(circuit_config_path: Path, out_dir: Path) -> tuple[dict, int]:
    """Write the NEST simulation config, node sets and Poisson replay spikes for *circuit*."""
    circuit = libsonata.CircuitConfig.from_file(str(circuit_config_path))

    virtual_pops = []
    number_neurons = 0
    for name in sorted(circuit.node_populations):
        if circuit.node_population_properties(name).type == "virtual":
            virtual_pops.append(name)
        else:
            number_neurons += circuit.node_population(name).size
    if not virtual_pops:
        msg = f"No virtual populations to drive in {circuit_config_path}"
        raise RuntimeError(msg)

    rng = np.random.default_rng(RANDOM_SEED)
    node_sets = {}
    inputs = {}
    with h5py.File(out_dir / INPUT_SPIKES_FILENAME, "w") as h5:
        spikes = h5.create_group("spikes")
        for name in virtual_pops:
            size = circuit.node_population(name).size
            counts = rng.poisson(INPUT_RATE_HZ * TSTOP / 1000.0, size)
            node_ids = np.repeat(np.arange(size, dtype=np.uint64), counts)
            times = rng.uniform(0.0, TSTOP, node_ids.size)
            order = np.argsort(times)
            group = spikes.create_group(name)
            group.attrs["sorting"] = np.array(2, dtype=np.uint8)  # by_time
            group.create_dataset("node_ids", data=node_ids[order])
            group.create_dataset("timestamps", data=times[order])

            node_sets[name] = {"population": name}
            inputs[f"replay_{name}"] = {
                "input_type": "spikes",
                "module": "synapse_replay",
                "delay": 0.0,
                "duration": TSTOP,
                "node_set": name,
                "spike_file": INPUT_SPIKES_FILENAME,
            }

    (out_dir / "node_sets.json").write_text(json.dumps(node_sets, indent=2))
    simulation_config = {
        "version": 2.4,
        "target_simulator": "NEST",
        "network": "circuit_config.json",
        "node_sets_file": "node_sets.json",
        "run": {"dt": DT, "tstop": TSTOP, "random_seed": RANDOM_SEED},
        "output": {"output_dir": "output", "spikes_file": "spikes.h5"},
        "inputs": inputs,
    }
    (out_dir / "simulation_config.json").write_text(json.dumps(simulation_config, indent=2))
    return simulation_config, number_neurons


def register_simulation(
    db_client: entitysdk.Client, circuit: models.Circuit, output_dir: Path, summary: dict
) -> models.Simulation:
    config_dir = output_dir / "simulation_config"
    staged_circuit = stage_circuit(
        db_client, model=circuit, output_dir=output_dir / "staged_circuit"
    )
    config_dir.mkdir(parents=True, exist_ok=True)
    _, number_neurons = write_simulation_inputs(Path(staged_circuit), config_dir)

    campaign = db_client.register_entity(
        models.SimulationCampaign(
            name="NEST e2e simulation campaign",
            description=f"Poisson replay ({INPUT_RATE_HZ} Hz) into the virtual inputs of {circuit.name}",
            entity_id=circuit.id,
            scan_parameters={},
        )
    )
    simulation = db_client.register_entity(
        models.Simulation(
            name="NEST e2e simulation",
            description=f"{TSTOP} ms NEST simulation of {circuit.name}",
            simulation_campaign_id=campaign.id,
            entity_id=circuit.id,
            scan_parameters={},
            number_neurons=number_neurons,
        )
    )
    for file_name, content_type, label in (
        ("simulation_config.json", ContentType.application_json, AssetLabel.sonata_simulation_config),
        ("node_sets.json", ContentType.application_json, AssetLabel.custom_node_sets),
        (INPUT_SPIKES_FILENAME, ContentType.application_x_hdf5, AssetLabel.replay_spikes),
    ):
        db_client.upload_file(
            entity_id=simulation.id,
            entity_type=models.Simulation,
            file_path=config_dir / file_name,
            file_content_type=content_type,
            asset_label=label,
        )
    generation = db_client.register_entity(
        models.SimulationGeneration(
            start_time=datetime.now(UTC),
            used=[campaign],
            generated=[simulation],
        )
    )
    summary["simulation_campaign"] = _entity_row(campaign)
    summary["simulation"] = _entity_row(simulation)
    summary["simulation_generation"] = _activity_row(generation)
    return simulation


def simulate(db_client: entitysdk.Client, circuit_id: UUID, output_dir: Path, summary: dict):
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)
    summary["simplified_circuit"] = _entity_row(circuit)
    if circuit.target_simulator != "NEST":
        msg = f"Circuit {circuit.id} targets {circuit.target_simulator}, expected NEST"
        raise RuntimeError(msg)

    simulation = register_simulation(db_client, circuit, output_dir, summary)
    activity = db_sdk.create_activity(
        client=db_client,
        activity_type=models.SimulationExecution,
        activity_status=ActivityStatus.pending,
        used=[simulation],
    )
    run_dir = output_dir / "simulation_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    # The NEST task stages into ./data and writes into ./outputs of the working directory.
    with contextlib.chdir(run_dir):
        activity = run_tracked_task(
            db_client,
            task_type=TaskType.circuit_simulation_nest_machine,
            config_entity=simulation,
            activity=activity,
            scan_output_root=run_dir,
        )
    summary["simulation_execution"] = _activity_row(activity)

    results = [
        db_client.get_entity(entity_id=g.id, entity_type=models.SimulationResult)
        for g in activity.generated
    ]
    summary["simulation_results"] = [_entity_row(r) for r in results]

    spikes = sorted((output_dir / "simulation_run").rglob("spikes.h5"))
    if spikes:
        summary["spike_report"] = _spike_stats(spikes[0])


def _entity_row(entity) -> dict:
    row = {"type": type(entity).__name__, "id": str(entity.id), "name": getattr(entity, "name", None)}
    for attr in ("target_simulator", "number_neurons", "number_synapses", "lifecycle_status"):
        if (value := getattr(entity, attr, None)) is not None:
            row[attr] = str(value)
    if assets := getattr(entity, "assets", None):
        row["assets"] = sorted(f"{a.label}:{a.path}" for a in assets)
    return row


def _activity_row(activity) -> dict:
    return {
        "type": type(activity).__name__,
        "id": str(activity.id),
        "status": str(getattr(activity, "status", None)),
        "used": [f"{type(u).__name__}:{u.id}" for u in activity.used or []],
        "generated": [f"{type(g).__name__}:{g.id}" for g in activity.generated or []],
    }


def _spike_stats(path: Path) -> dict:
    stats = {"file": str(path)}
    with h5py.File(path, "r") as h5:
        for name, group in h5["spikes"].items():
            stats[name] = {
                "n_spikes": int(group["timestamps"].size),
                "n_active_nodes": int(np.unique(group["node_ids"][:]).size),
            }
    return stats


def print_summary(summary: dict) -> None:
    print("\n" + "=" * 80 + "\nSUMMARY\n" + "=" * 80)
    for key, value in summary.items():
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            print(f"\n[{key}]")
            for k, v in row.items():
                print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--simplified-circuit-id",
        help="Skip simplification and simulate this already registered NEST circuit.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    db_client = get_db_client()
    summary: dict = {}
    try:
        if args.simplified_circuit_id:
            circuit_id = UUID(args.simplified_circuit_id)
        else:
            circuit_id = simplify(db_client, OUTPUT_DIR, summary)
        simulate(db_client, circuit_id, OUTPUT_DIR, summary)
    finally:
        (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        print_summary(summary)


if __name__ == "__main__":
    main()
