"""Launch NEST circuit simplification via local obi-one + staging launch-system.

Uses a NEST point-neuron algorithm (default ``adex_nest``). The worker registers a
simplified ``Circuit`` with ``target_simulator=NEST`` in the SONATA-extension format
(see ``run_simplification_local.ipynb`` and AGENTS.md).

For the NEURON single-compartment path, use ``run_circuit_simplification.py``.
"""

import json
import logging
import os
from pathlib import Path

from entitysdk import models
from entitysdk.token_manager import TokenFromFunction
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

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/circuit_simplification_nest/cloud"

L = logging.getLogger(__name__)

# Same paired-neuron staging circuit as run_circuit_simplification.py
CIRCUIT_ID = "ed096991-4171-4cfc-b54e-756323fc62e7"
# NEST algorithms: adex_nest, lif_nest, izhikevich_nest, glif_nest, gif_nest
ALGORITHM = os.environ.get("SIMPLIFICATION_ALGORITHM", "adex_nest")

# Set to relaunch without create_config()
CONFIG_ID: str | None = None

NEST_ALGORITHMS = {
    name for name in ALGORITHM_BLOCK_CLASSES if name.endswith("_nest")
}

DOMAINS = {
    "cell_a": {
        "virtual_lab_id": LAB_ID_STAGING_TEST,
        "project_id": PROJECT_ID_STAGING_TEST,
    }
}


def _entity_row(entity) -> dict:
    row = {
        "type": type(entity).__name__,
        "id": str(entity.id),
        "name": getattr(entity, "name", None),
        "description": getattr(entity, "description", None),
    }
    for attr in (
        "target_simulator",
        "number_neurons",
        "number_synapses",
        "lifecycle_status",
        "atlas_release",
    ):
        if (value := getattr(entity, attr, None)) is not None:
            row[attr] = str(value)
    if parent := getattr(entity, "parent", None):
        row["parent_id"] = str(getattr(parent, "id", parent))
    if assets := getattr(entity, "assets", None):
        row["assets"] = sorted(f"{a.label}:{a.path}" for a in assets)
    return row


def create_config(manager):
    db_client = manager.db_client

    if ALGORITHM not in NEST_ALGORITHMS:
        raise ValueError(
            f"Algorithm {ALGORITHM!r} is not a NEST algorithm; choose from "
            f"{sorted(NEST_ALGORITHMS)}"
        )

    input_circuit = db_client.get_entity(
        entity_id=CIRCUIT_ID, entity_type=models.Circuit
    )
    L.info("Input circuit: %s", json.dumps(_entity_row(input_circuit), indent=2))

    scan_config = CircuitSimplificationScanConfig(
        info=Info(
            campaign_name="Circuit Simplification NEST Test",
            campaign_description=(
                f"NEST SONATA-extension simplification ({ALGORITHM}) via local obi-one"
            ),
        ),
        initialize=CircuitSimplificationScanConfig.Initialize(
            circuit=CircuitFromID(id_str=CIRCUIT_ID),
        ),
        algorithm=ALGORITHM_BLOCK_CLASSES[ALGORITHM](),
    )

    grid_scan = GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.execute(db_client=db_client)

    campaign_entity = grid_scan.form.campaign
    L.info(
        "Campaign '%s' (ID %s): %s",
        campaign_entity.name,
        campaign_entity.id,
        campaign_entity.description,
    )

    for cfg in grid_scan.single_configs:
        L.info(
            "  Coordinate %s: '%s' (ID %s)",
            cfg.idx,
            cfg.single_entity.name,
            cfg.single_entity.id,
        )

    summary = {
        "input_circuit": _entity_row(input_circuit),
        "campaign": _entity_row(campaign_entity),
        "config": _entity_row(grid_scan.single_configs[0].single_entity),
        "algorithm": ALGORITHM,
        "expected_format": "SONATA-extension",
        "expected_target_simulator": "NEST",
    }
    (manager.output_dir / "pre_launch_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )
    return grid_scan.single_configs[0].single_entity, summary


def report_results(manager, config_id, summary: dict) -> dict:
    """Fetch execution activity + generated NEST circuit after the job finishes."""
    db_client = manager.db_client
    activities = list(
        db_client.search_entity(
            entity_type=models.TaskActivity,
            query={"used__id": str(config_id)},
        )
    )
    if not activities:
        L.warning("No TaskActivity found for config %s", config_id)
        summary["activities"] = []
        return summary

    activities = sorted(activities, key=lambda a: a.start_time or "", reverse=True)
    activity_rows = []
    generated_circuits = []
    for activity in activities:
        row = {
            "type": type(activity).__name__,
            "id": str(activity.id),
            "status": str(getattr(activity, "status", None)),
            "used": [f"{type(u).__name__}:{u.id}" for u in activity.used or []],
            "generated": [
                f"{type(g).__name__}:{g.id}" for g in activity.generated or []
            ],
        }
        activity_rows.append(row)
        for gen in activity.generated or []:
            try:
                circuit = db_client.get_entity(
                    entity_id=gen.id, entity_type=models.Circuit
                )
                generated_circuits.append(_entity_row(circuit))
            except Exception as exc:  # noqa: BLE001 - best-effort reporting
                generated_circuits.append(
                    {"id": str(gen.id), "error": f"{type(exc).__name__}: {exc}"}
                )

    summary["activities"] = activity_rows
    summary["simplified_circuits"] = generated_circuits

    nest_ok = any(c.get("target_simulator") == "NEST" for c in generated_circuits)
    summary["nest_sonata_extension_ok"] = nest_ok
    (manager.output_dir / "post_launch_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    print("\n" + "=" * 80 + "\nNEST SIMPLIFICATION SUMMARY\n" + "=" * 80)
    print(f"\n[algorithm]\n  {ALGORITHM}")
    print("\n[expected]\n  format: SONATA-extension\n  target_simulator: NEST")
    print("\n[before / input_circuit]")
    for k, v in summary.get("input_circuit", {}).items():
        print(f"  {k}: {v}")
    print("\n[after / simplified_circuits]")
    if generated_circuits:
        for circuit in generated_circuits:
            for k, v in circuit.items():
                print(f"  {k}: {v}")
            print()
    else:
        print("  (none found on TaskActivity.generated)")
    print(f"[nest_sonata_extension_ok]\n  {nest_ok}")
    print("[activities]")
    for row in activity_rows:
        for k, v in row.items():
            print(f"  {k}: {v}")
        print()

    if generated_circuits and not nest_ok:
        raise SystemExit(
            "Simplification finished but no Circuit with target_simulator=NEST was "
            "registered (expected SONATA-extension NEST output)."
        )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if "ACCESS_TOKEN" not in os.environ:
        raise SystemExit("ACCESS_TOKEN must be set in the environment")

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.circuit_simplification,
        subdomain="cell_a",
        obi_one_deployment="local",
        launch_system_deployment="staging",
        db_deployment="staging",
        domains=DOMAINS,
    )
    manager._token_manager = TokenFromFunction(lambda: os.environ["ACCESS_TOKEN"])

    summary: dict = {
        "algorithm": ALGORITHM,
        "expected_format": "SONATA-extension",
        "expected_target_simulator": "NEST",
    }
    if CONFIG_ID is None:
        config, summary = create_config(manager)
        config_id = config.id
        L.info("Config: %s", config)
    else:
        config_id = CONFIG_ID
        input_circuit = manager.db_client.get_entity(
            entity_id=CIRCUIT_ID, entity_type=models.Circuit
        )
        summary["input_circuit"] = _entity_row(input_circuit)
        L.info("Using existing config_id: %s", config_id)

    manager.run_task(
        config_id=config_id,
        activity_type=models.TaskActivity,
        check_mode="obi-one",
    )
    report_results(manager, config_id, summary)
