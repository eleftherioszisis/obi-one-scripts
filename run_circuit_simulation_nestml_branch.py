"""Cloud end-to-end NESTML test against an obi-one service running a branch.

Same flow as run_circuit_simulation_nest_branch.py, but the simulated population runs a NESTML
custom model, which the NEST task generates and compiles on the launch-system executor:

1. Stage a simplified NEST circuit (``adex_nest``, ``nest:aeif_cond_alpha``) from staging.
2. Point its ``nest_point`` population at ``nestml:aeif_cond_alpha_obi``: an AdEx with alpha
   conductances (NESTML's own ``aeif_cond_alpha_neuron``) whose parameters are named as in NEST's
   ``aeif_cond_alpha``, so the template ``params`` and the per-node ``dynamics_params`` of the
   simplified circuit load unchanged. The model has no analytic solution, so NESTML integrates it
   with GSL.
3. Register it as a new NEST ``Circuit`` derived from the simplified one.
4. Register a NEST ``Simulation`` and launch it as the UI does (``circuit_simulation``), then check
   the registered ``SimulationResult``.

Usage::

    python run_circuit_simulation_nestml_branch.py --simplified-circuit-id <uuid>
    python run_circuit_simulation_nestml_branch.py --nestml-circuit-id <uuid>   # skip 1-3
"""

import argparse
import json
import logging
import shutil
from pathlib import Path
from uuid import UUID

import h5py
from entitysdk import models
from entitysdk.staging.circuit import stage_circuit
from entitysdk.types import DerivationType, TargetSimulator

import run_circuit_simulation_nest_branch as nest_e2e
from obi_one.db_sdk.registration.circuit.register import register_circuit
from obi_one.types import TaskType

L = logging.getLogger("nestml_e2e")

OUTPUT_DIR = Path(__file__).parent / "out/circuit_simulation_nestml_branch/cloud"
MODEL_NAME = "aeif_cond_alpha_obi"
SOURCE_TEMPLATE = "aeif_cond_alpha"

NESTML_SOURCE = f'''\
# AdEx with alpha-shaped conductances: NESTML's aeif_cond_alpha_neuron, with the parameter names
# of NEST's built-in aeif_cond_alpha (t_ref, E_ex, E_in, tau_syn_ex, tau_syn_in).
model {MODEL_NAME}:
    state:
        V_m mV = E_L
        w pA = 0 pA
        refr_t ms = 0 ms

    equations:
        kernel g_in = (e / tau_syn_in) * t * exp(-t / tau_syn_in)
        kernel g_ex = (e / tau_syn_ex) * t * exp(-t / tau_syn_ex)
        inline V_bounded mV = min(V_m, V_peak)
        inline exp_arg real = (V_bounded - V_th) / Delta_T
        inline I_spike pA = g_L * Delta_T * exp(exp_arg)
        inline I_syn_exc pA = unit_psg * convolve(g_ex, exc_spikes) * (V_bounded - E_ex)
        inline I_syn_inh pA = unit_psg * convolve(g_in, inh_spikes) * (V_bounded - E_in)
        V_m' = (-g_L * (V_bounded - E_L) + I_spike - I_syn_exc - I_syn_inh - w + I_e + I_stim) / C_m
        w' = (a * (V_bounded - E_L) - w) / tau_w
        refr_t' = -1

    parameters:
        C_m pF = 281.0 pF
        t_ref ms = 0 ms
        V_reset mV = -60.0 mV
        g_L nS = 30.0 nS
        E_L mV = -70.6 mV
        a nS = 4 nS
        b pA = 80.5 pA
        Delta_T mV = 2.0 mV
        tau_w ms = 144.0 ms
        V_th mV = -50.4 mV
        V_peak mV = 0 mV
        E_ex mV = 0 mV
        tau_syn_ex ms = 0.2 ms
        E_in mV = -85.0 mV
        tau_syn_in ms = 2.0 ms
        I_e pA = 0 pA

    internals:
        unit_psg nS = 1 nS

    input:
        exc_spikes <- excitatory spike
        inh_spikes <- inhibitory spike
        I_stim pA <- continuous

    output:
        spike

    update:
        if refr_t > 0 ms:
            integrate_odes(w, refr_t)
        else:
            integrate_odes(V_m, w)

    onCondition(refr_t <= 0 ms and V_m >= V_peak):
        refr_t = t_ref
        V_m = V_reset
        w += b
        emit_spike()
'''


def make_nestml_circuit(staged_config: Path, out_dir: Path) -> tuple[Path, dict]:
    """Copy the staged circuit to *out_dir* and switch its point populations to the NESTML model."""
    shutil.copytree(staged_config.parent, out_dir, ignore=shutil.ignore_patterns(".nestml_cache"))
    config = json.loads((out_dir / "circuit_config.json").read_text())
    changed = {}
    for network in config["networks"]["nodes"]:
        for name, population in network["populations"].items():
            if population["type"] != "nest_point":
                continue
            models_dir = out_dir / population["point_neuron_models_dir"].replace("$BASE_DIR/", "")
            template = json.loads((models_dir / f"{SOURCE_TEMPLATE}.json").read_text())
            if template["model"] != f"nest:{SOURCE_TEMPLATE}":
                raise RuntimeError(f"{name}: unexpected template model {template['model']!r}")
            template["model"] = f"nestml:{MODEL_NAME}"
            (models_dir / f"{MODEL_NAME}.json").write_text(json.dumps(template, indent=2))
            (models_dir / f"{MODEL_NAME}.nestml").write_text(NESTML_SOURCE)
            (models_dir / f"{SOURCE_TEMPLATE}.json").unlink()

            nodes_file = out_dir / network["nodes_file"].replace("$BASE_DIR/", "")
            with h5py.File(nodes_file, "r+") as h5:
                library = h5[f"nodes/{name}/0/@library"]
                names = [n.decode() for n in library["model_template"][:]]
                if names != [SOURCE_TEMPLATE]:
                    raise RuntimeError(f"{name}: unexpected model templates {names}")
                del library["model_template"]
                library.create_dataset(
                    "model_template", data=[MODEL_NAME], dtype=h5py.string_dtype()
                )
            changed[name] = {"template": f"{MODEL_NAME}.json", "model": template["model"]}
    if not changed:
        raise RuntimeError("No nest_point population to switch to NESTML")
    return out_dir / "circuit_config.json", changed


def register_nestml_circuit(db_client, parent: models.Circuit, summary: dict) -> models.Circuit:
    staged = stage_circuit(db_client, model=parent, output_dir=OUTPUT_DIR / "staged_parent")
    circuit_config, changed = make_nestml_circuit(Path(staged), OUTPUT_DIR / "nestml_circuit")
    summary["nestml_changes"] = changed
    circuit = register_circuit(
        client=db_client,
        circuit_path=circuit_config,
        name=f"{parent.name}__nestml_{MODEL_NAME}",
        description=f"{parent.name} with its point neurons as the NESTML model '{MODEL_NAME}'",
        build_category=parent.build_category,
        brain_region=parent.brain_region,
        subject=parent.subject,
        target_simulator=TargetSimulator.NEST,
        experiment_date=parent.experiment_date,
        license=parent.license,
        atlas=None,
        root=parent.root_circuit_id or parent.id,
        parent=parent,
        derivation_type=DerivationType.circuit_customization,
        # bluepysnap has no schema for the SONATA-extension NEST population types
        skip_validation=True,
    )
    return db_client.get_entity(entity_id=circuit.id, entity_type=models.Circuit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--simplified-circuit-id", help="Simplified NEST circuit to convert.")
    group.add_argument("--nestml-circuit-id", help="Already registered NESTML circuit.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    nest_e2e.OUTPUT_DIR = OUTPUT_DIR  # job logs, simulation inputs and results go here

    db_client = nest_e2e.get_db_client()
    summary: dict = {"obi_one_url": nest_e2e.OBI_ONE_URL, "nestml_model": MODEL_NAME}
    try:
        if args.nestml_circuit_id:
            circuit = db_client.get_entity(
                entity_id=args.nestml_circuit_id, entity_type=models.Circuit
            )
        else:
            parent = db_client.get_entity(
                entity_id=args.simplified_circuit_id, entity_type=models.Circuit
            )
            summary["parent_circuit"] = nest_e2e.entity_row(parent)
            circuit = register_nestml_circuit(db_client, parent, summary)
        summary["nestml_circuit"] = nest_e2e.entity_row(circuit)

        simulation = nest_e2e.register_simulation(db_client, circuit, summary)
        job = nest_e2e.launch_and_wait(
            TaskType.circuit_simulation,
            simulation.id,
            "simulation_job",
            expected_task_type=TaskType.circuit_simulation_nest_machine,
        )
        summary["simulation_job"] = job
        nest_e2e.check_results(db_client, UUID(job["activity_id"]), summary)
    finally:
        (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
