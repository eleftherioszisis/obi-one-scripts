   
subdomain = "cell_a"


js = {
        "project_id": project_id,
        "code": {
            "type": "builtin",
            "script": "circuit_simulation"
        },
        "resources": {
            "type": "cluster",
            "instance_type": "small",
            "instances": 1,
            "compute_cell": "cell_a",
        },
        "inputs": [
            "--simulation-id",
            SIMULATION_ID,
            "--simulation-execution-id",
            str(sim_exec.id)
        ]
    }
