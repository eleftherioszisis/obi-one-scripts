"""Run the local obi-one service so that launch jobs check out an obi-one commit.

The service normally submits ``ref=tag:<APP_VERSION>``. This wrapper replaces
``release_tag_ref`` before ``app.mappings`` imports it, so every obi-one task is submitted
with ``ref=commit:<OBI_ONE_LAUNCH_COMMIT>``. Run it from the obi-one checkout with its
``.env.run-local`` loaded, e.g.::

    cd ../obi-one
    set -a; source .env.run-local; set +a
    OBI_ONE_LAUNCH_COMMIT=<40-hex sha> .venv/bin/python ../obi-one-scripts/serve_obi_one_branch.py

The commit must be pushed. To use the branch's obi-one library code (not the last release
wheel), its ``launch_scripts/.../dependencies/*.txt`` obi-one line must point at a git ref,
see obi-one ``docs/internal/launch-script-dependencies.md``.
"""

import logging
import os
import re
import sys

import uvicorn

import obi_one.utils.versions

COMMIT = os.environ["OBI_ONE_LAUNCH_COMMIT"]
PORT = int(os.environ.get("OBI_ONE_PORT", "8101"))

if not re.fullmatch(r"[0-9a-f]{40}", COMMIT):
    sys.exit(f"OBI_ONE_LAUNCH_COMMIT must be a full 40-hex sha, got {COMMIT!r}")

obi_one.utils.versions.release_tag_ref = lambda _app_version: f"commit:{COMMIT}"

from app.mappings import TASK_DEFINITIONS  # noqa: E402

logging.basicConfig(level=logging.INFO, force=True)
logging.info("Launch jobs use obi-one ref commit:%s", COMMIT)
if "--check" in sys.argv:
    for task_type, definition in TASK_DEFINITIONS.items():
        print(task_type, getattr(getattr(definition, "code", None), "ref", None))
    sys.exit(0)

uvicorn.run("app.application:app", host="127.0.0.1", port=PORT)
