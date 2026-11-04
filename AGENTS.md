# Agent guide: launching OBI tasks from this repo

This file tells coding agents (Cursor, Claude Code, Codex, etc.) how to run tasks the same way a human would: local **obi-one** service + **launch-system tunnel** + a `run_*.py` script.

Read this before creating, editing, or executing task launch scripts.

## Repository layout

| Path | Role |
|------|------|
| `run_*.py` | Task-specific scripts: build config, submit job, poll logs |
| `utils.py` | `RemoteTaskManager`, HTTP clients for obi-one / launch-system / entitycore |
| `tunnel.sh` | AWS SSM port-forward to staging launch-system on `localhost:4444` |
| `../obi-one/` | Sibling checkout of [obi-one](https://github.com/openbraininstitute/obi-one); run the local API here |
| `out/<task>/cloud/` | Per-script output root (created/cleaned by `RemoteTaskManager`) |

Human-oriented setup details also live in [README.md](README.md).

## Standard execution workflow (3 terminals)

When the user asks to **run**, **test**, or **launch** a task script, use this layout:

### Terminal 1 — local obi-one API

```bash
cd ../obi-one
make install-service   # once, if not already installed
make run-local         # serves http://127.0.0.1:8100
```

Wait until Uvicorn reports **Application startup complete**, then verify:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8100/docs   # expect 200
```

Keep this process running in the background.

### Terminal 2 — launch-system tunnel

```bash
cd /path/to/obi-one-scripts
./tunnel.sh
```

Requires AWS SSO profile `BastionUserAccess-staging` and the Session Manager plugin. The script forwards staging launch-system to **https://127.0.0.1:4444**.

Verify:

```bash
curl -sk https://127.0.0.1:4444/api/launch-system/version
```

Keep this process running in the background.

### Terminal 3 — run the task script

Use the **obi-one virtualenv** (not the system Python):

```bash
cd /path/to/obi-one-scripts
export ACCESS_TOKEN='<platform bearer token from staging UI>'
../obi-one/.venv/bin/pip install rich   # once, if utils.py import fails
../obi-one/.venv/bin/python run_<task>.py
```

**Important tokens**

- `ACCESS_TOKEN` — required in the environment. Used by `RemoteTaskManager` for obi-one and launch-system HTTP calls. The user must supply it; never commit it, write it to repo files, or echo it in summaries.
- entitycore calls inside scripts use `obi_auth.get_token(environment="staging")` via `TokenFromFunction` and do **not** need `ACCESS_TOKEN`.

If task launch returns **401 Unauthorized** on `POST /declared/task/launch`, the `ACCESS_TOKEN` is missing, expired, or corrupted (common when copy-pasting into shell — preserve the JWT exactly).

## Script pattern

Every cloud launch script follows the same shape:

```python
import logging
from pathlib import Path

import obi_one as obi
from entitysdk import models
from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST
from obi_one.types import TaskType

from utils import RemoteTaskManager

OUTPUT_DIR = Path(__file__).parent / "out/<task_name>/cloud"

# Always use the staging test lab/project from obi-one unless the user overrides.
DOMAINS = {
    "cell_a": {
        "virtual_lab_id": LAB_ID_STAGING_TEST,
        "project_id": PROJECT_ID_STAGING_TEST,
    }
}


def create_config(manager):
    db_client = manager.db_client
    # 1. Build a ScanConfig (see obi-one examples/notebooks)
    scan_config = obi.SomeScanConfig(...)
    # 2. Generate coordinate configs in entitycore
    grid_scan = obi.GridScanGenerationTask(
        form=scan_config,
        coordinate_directory_option="ZERO_INDEX",
        output_root=manager.output_dir,
    )
    grid_scan.execute(db_client=db_client)
    # 3. Return the single TaskConfig entity to launch
    return grid_scan.single_configs[0].single_entity


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    manager = RemoteTaskManager(
        output_dir=OUTPUT_DIR,
        task_type=TaskType.some_task,
        subdomain="cell_a",
        obi_one_deployment="local",          # local obi-one on :8100
        launch_system_deployment="staging",  # tunnel on :4444
        db_deployment="staging",
        domains=DOMAINS,
    )
    config = create_config(manager)
    manager.run_task(
        config_id=config.id,
        activity_type=models.TaskActivity,  # most task configs
        check_mode="obi-one",               # or "job" / "stream" / "activity"
    )
```

### Staging domain (`cell_a`)

Always pass `domains` using the staging test IDs from obi-one (do not hardcode UUIDs):

```python
from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST

DOMAINS = {
    "cell_a": {
        "virtual_lab_id": LAB_ID_STAGING_TEST,
        "project_id": PROJECT_ID_STAGING_TEST,
    }
}
```

Only override when the user explicitly provides different lab/project IDs.

### Deployment matrix

| Setting | Local dev (this repo) | Direct staging |
|---------|----------------------|----------------|
| `obi_one_deployment` | `"local"` | `"staging"` |
| `launch_system_deployment` | `"staging"` (via tunnel) | `"staging"` |
| `db_deployment` | `"staging"` | `"staging"` |

### Re-running without new config

To relaunch an existing config, comment out `create_config(manager)` and pass a known UUID:

```python
CONFIG_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
manager.run_task(config_id=CONFIG_ID, check_mode="obi-one", ...)
```

## Adding a new task script

1. Find the obi-one example notebook or scan config under `obi-one/examples/obi_one/scientific/tasks/<task>/`.
2. Mirror its `ScanConfig` + `GridScanGenerationTask` setup in `create_config()`.
3. Look up `TaskType.<name>` in `obi-one/obi_one/types.py` and task registration in `obi-one/app/mappings.py`.
4. Name the file `run_<task_snake_case>.py` and set `OUTPUT_DIR` under `out/`.
5. Pass `domains=DOMAINS` with `LAB_ID_STAGING_TEST` / `PROJECT_ID_STAGING_TEST` from `obi_one`.
6. Use `CircuitFromID` (or other `*FromID`) in cloud scripts — staging/download happens on the worker, not locally.
7. Run the 3-terminal workflow above and show the user job output.

Example reference: [run_circuit_simplification.py](run_circuit_simplification.py) (from `run_simplification_local.ipynb`).

## Fetching full job logs after failure

Poll obi-one (preferred when using local deployment):

```python
import httpx
from obi_auth import get_token
from obi_one import LAB_ID_STAGING_TEST, PROJECT_ID_STAGING_TEST

JOB_ID = "..."
TOKEN = get_token(environment="staging")
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "virtual-lab-id": LAB_ID_STAGING_TEST,
    "project-id": PROJECT_ID_STAGING_TEST,
}
job = httpx.get(f"http://127.0.0.1:8100/declared/task/{JOB_ID}", headers=headers).json()
print(job["status"])
for entry in job.get("logs", {}).get("stream", []):
    if entry.get("message_type") == "stderr":
        print(entry["stderr"])
```

Or launch-system directly: `GET https://127.0.0.1:4444/api/launch-system/job/{job_id}` (verify=False).

Use `obi_auth.get_token` for log retrieval if the user's `ACCESS_TOKEN` is unavailable or expired.

## Known pitfalls

| Symptom | Likely cause | What to do |
|---------|--------------|------------|
| `401` on `/declared/task/launch` | Bad/missing `ACCESS_TOKEN` | Ask user for fresh token; export exactly, no truncation |
| `ModuleNotFoundError: rich` | utils.py dependency | `../obi-one/.venv/bin/pip install rich` |
| `MarkupError` while polling | `rich.print` chokes on `[...]` in stderr | Fetch logs via httpx (plain print), not `print_messages` |
| obi-one curl fails during startup | Worker still loading | Wait for "Application startup complete" |
| Job `error` after staging circuit | Worker-side failure (e.g. MOD compile) | Fetch full stderr from job API; not a launch-script bug |
| Duplicate MOD symbols (`InhPoissonStim` / `netstim_inhpoisson`) | Circuit mod directory conflict | Task/worker issue in obi-one or circuit assets |

## Agent checklist

Before declaring success, confirm:

- [ ] obi-one responds on `:8100`
- [ ] launch-system tunnel responds on `:4444`
- [ ] `ACCESS_TOKEN` is set (user-provided)
- [ ] Script uses `../obi-one/.venv/bin/python`
- [ ] Config entity created (or existing `CONFIG_ID` used)
- [ ] Job submitted and final status checked
- [ ] Full error logs shown if status is `error`
- [ ] No secrets written to git

## What not to do

- Do not commit `ACCESS_TOKEN`, `.env` secrets, or AWS credentials.
- Do not force-push or amend commits unless the user asks.
- Do not skip starting obi-one and the tunnel when the user wants an end-to-end run.
- Do not give up after a single 401 — verify token handling first.
