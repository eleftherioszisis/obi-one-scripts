#!/usr/bin/env python3
import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPTS = {
    "run_icm_cloud": ROOT / "run_icm_cloud.py",
    "run_circuit_simulation_cloud": ROOT / "run_circuit_simulation_cloud.py",
    "run_circuit_extraction_cloud": ROOT / "run_circuit_extraction_cloud.py",
    "run_skeletonization_cloud": ROOT / "run_skeletonization_cloud.py",
}


@dataclass
class TaskRun:
    run_id: str
    script_name: str
    script_path: str
    status: str
    created_at: float
    started_at: float | None = None
    ended_at: float | None = None
    return_code: int | None = None
    log: str = ""
    error: str = ""


class TaskStore:
    def __init__(self):
        self._runs: dict[str, TaskRun] = {}
        self._lock = threading.Lock()

    def list_runs(self) -> list[TaskRun]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    def create_run(self, script_name: str, script_path: Path) -> TaskRun:
        run = TaskRun(
            run_id=str(uuid.uuid4()),
            script_name=script_name,
            script_path=str(script_path),
            status="queued",
            created_at=time.time(),
        )
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def update_run(self, run_id: str, **kwargs):
        with self._lock:
            run = self._runs[run_id]
            for key, value in kwargs.items():
                setattr(run, key, value)

    def append_log(self, run_id: str, text: str):
        with self._lock:
            self._runs[run_id].log += text

    def get_run(self, run_id: str) -> TaskRun | None:
        with self._lock:
            return self._runs.get(run_id)


STORE = TaskStore()


def _run_script(run: TaskRun):
    env = os.environ.copy()
    access_token = env.get("ACCESS_TOKEN")
    if not access_token:
        STORE.update_run(
            run.run_id,
            status="failed",
            started_at=time.time(),
            ended_at=time.time(),
            return_code=1,
            error="Missing required environment variable: ACCESS_TOKEN",
            log="ERROR: Missing required environment variable: ACCESS_TOKEN\n",
        )
        return

    STORE.update_run(run.run_id, status="running", started_at=time.time())

    proc = subprocess.Popen(
        ["python", run.script_path],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    collected: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        collected.append(line)
        STORE.append_log(run.run_id, line)

    proc.wait()
    full_log = "".join(collected)
    error_text = full_log if proc.returncode != 0 else ""
    STORE.update_run(
        run.run_id,
        status="success" if proc.returncode == 0 else "failed",
        ended_at=time.time(),
        return_code=proc.returncode,
        error=error_text,
    )


def launch_script(script_name: str):
    script_path = SCRIPTS.get(script_name)
    if not script_path:
        raise ValueError(f"Unknown script: {script_name}")
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    run = STORE.create_run(script_name=script_name, script_path=script_path)
    worker = threading.Thread(target=_run_script, args=(run,), daemon=True)
    worker.start()
    return run


def launch_all():
    started = []
    for script_name in SCRIPTS:
        started.append(launch_script(script_name))
    return started


def as_json(run: TaskRun):
    return {
        "run_id": run.run_id,
        "script_name": run.script_name,
        "script_path": run.script_path,
        "status": run.status,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "return_code": run.return_code,
        "log": run.log,
        "error": run.error,
    }


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>OBI Cloud Script Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; background: #f7f7f8; color: #111; }
    h1 { margin-bottom: 4px; }
    .muted { color: #555; margin-bottom: 16px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
    button { border: 1px solid #bbb; background: #fff; border-radius: 8px; padding: 8px 12px; cursor: pointer; }
    button:hover { background: #f0f0f0; }
    .warn { color: #a10; font-weight: 600; margin-bottom: 16px; }
    .card { background: #fff; border: 1px solid #ddd; border-radius: 12px; padding: 12px; margin-bottom: 12px; }
    .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    .pill { border-radius: 999px; padding: 2px 8px; font-size: 12px; border: 1px solid #ddd; }
    .queued { background: #eef; }
    .running { background: #ffe9b0; }
    .success { background: #d6f5dd; }
    .failed { background: #ffd6d6; }
    pre { background: #0e1116; color: #d9e1ee; padding: 10px; border-radius: 8px; overflow: auto; max-height: 220px; }
    textarea { width: 100%; min-height: 120px; font-family: monospace; }
    .small { font-size: 12px; color: #444; }
  </style>
</head>
<body>
  <h1>OBI Cloud Script Dashboard</h1>
  <div class="muted">Run cloud scripts in parallel and inspect failures quickly.</div>
  <div id="tokenWarn" class="warn" style="display:none;"></div>
  <div class="row">
    <button onclick="runAll()">Run All Scripts</button>
    <button onclick="refreshRuns()">Refresh</button>
  </div>
  <div class="row" id="scriptButtons"></div>
  <div id="runs"></div>
<script>
const SCRIPT_ORDER = [
  "run_icm_cloud",
  "run_circuit_simulation_cloud",
  "run_circuit_extraction_cloud",
  "run_skeletonization_cloud"
];

function esc(text) {
  return (text || "").replace(/[&<>"]/g, (c) => (
    {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]
  ));
}

function fmt(ts) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

async function api(path, method="GET", body=null) {
  const res = await fetch(path, {
    method,
    headers: {"Content-Type":"application/json"},
    body: body ? JSON.stringify(body) : null
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || ("HTTP " + res.status));
  }
  return await res.json();
}

async function runScript(name) {
  await api("/api/run", "POST", {script_name: name});
  await refreshRuns();
}

async function runAll() {
  await api("/api/run_all", "POST", {});
  await refreshRuns();
}

function copyError(runId) {
  const el = document.getElementById("err-" + runId);
  if (!el) return;
  el.select();
  document.execCommand("copy");
}

async function loadMeta() {
  const meta = await api("/api/meta");
  const warn = document.getElementById("tokenWarn");
  if (!meta.access_token_present) {
    warn.style.display = "block";
    warn.textContent = "ACCESS_TOKEN is missing. Runs will fail until you export it before starting the dashboard.";
  } else {
    warn.style.display = "none";
  }
}

function renderScriptButtons() {
  const root = document.getElementById("scriptButtons");
  root.innerHTML = "";
  SCRIPT_ORDER.forEach((name) => {
    const btn = document.createElement("button");
    btn.textContent = "Run " + name;
    btn.onclick = () => runScript(name);
    root.appendChild(btn);
  });
}

async function refreshRuns() {
  const data = await api("/api/runs");
  const root = document.getElementById("runs");
  root.innerHTML = "";
  data.runs.forEach((run) => {
    const div = document.createElement("div");
    div.className = "card";
    const statusClass = run.status || "queued";
    const logPreview = run.log || "";
    const err = run.error || "";
    div.innerHTML = `
      <div class="head">
        <div><strong>${esc(run.script_name)}</strong></div>
        <div class="pill ${esc(statusClass)}">${esc(run.status)}</div>
      </div>
      <div class="small">Run ID: ${esc(run.run_id)} | Started: ${esc(fmt(run.started_at))} | Ended: ${esc(fmt(run.ended_at))} | Return code: ${run.return_code ?? "-"}</div>
      <pre>${esc(logPreview)}</pre>
      ${run.status === "failed" ? `
        <div><strong>Error output (copy/paste ready)</strong></div>
        <textarea id="err-${esc(run.run_id)}" readonly>${esc(err)}</textarea>
        <div class="row"><button onclick="copyError('${esc(run.run_id)}')">Copy Error</button></div>
      ` : ""}
    `;
    root.appendChild(div);
  });
}

async function boot() {
  renderScriptButtons();
  await loadMeta();
  await refreshRuns();
  setInterval(refreshRuns, 2000);
}
boot();
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/meta":
            self._send_json(
                {"access_token_present": bool(os.environ.get("ACCESS_TOKEN"))}
            )
            return
        if self.path == "/api/runs":
            runs = [as_json(r) for r in STORE.list_runs()]
            self._send_json({"runs": runs})
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/run":
            body = self._read_json()
            script_name = body.get("script_name")
            try:
                run = launch_script(script_name)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"run": as_json(run)}, status=HTTPStatus.CREATED)
            return
        if self.path == "/api/run_all":
            try:
                runs = [as_json(run) for run in launch_all()]
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"runs": runs}, status=HTTPStatus.CREATED)
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def main():
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("DASHBOARD_PORT", "8088"))
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard: http://{host}:{port}")
    print("Requires ACCESS_TOKEN in environment for successful task execution.")
    server.serve_forever()


if __name__ == "__main__":
    main()
