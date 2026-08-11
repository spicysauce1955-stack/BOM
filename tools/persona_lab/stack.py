"""Boot and tear down one fully isolated stack per persona.

Isolation is the point: a stray mutation or a crash in one persona's session
must not be visible to another, so each gets its own uvicorn, its own Chrome,
and its own throwaway SQLite file.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cdp import Cdp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

PERSONAS = [
    "kablan-gderot", "estimator", "sales-rep",
    "procurement", "measurer", "export-engineer-en",
]


def ports_for(index: int) -> tuple[int, int]:
    return 8800 + index, 9400 + index


def session_path(run_dir: Path) -> Path:
    return run_dir / "session.json"


def _port_free(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://localhost:{port}/api/health", timeout=1)
        return False
    except Exception:
        return True


def start(persona: str, index: int, run_dir: Path) -> dict:
    port, cdp_port = ports_for(index)
    if not _port_free(port):
        raise RuntimeError(f"port {port} is already in use — kill the stale stack first")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "shots").mkdir(exist_ok=True)
    db = tempfile.mktemp(suffix=f"-{persona}.db")

    server = subprocess.Popen(
        ["uv", "run", "uvicorn", "fenceai.api.app:app", "--port", str(port)],
        env={**os.environ, "FENCEAI_DB": db, "FENCEAI_AI": "stub"},
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    chrome = subprocess.Popen(
        ["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
         f"--remote-debugging-port={cdp_port}", "--remote-allow-origins=*",
         "--window-size=1400,950", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    time.sleep(4)

    c = Cdp(f"http://localhost:{port}/", cdp_port=cdp_port, out_dir=str(run_dir / "shots"))
    # a real user never sees a native confirm(); auto-accept so a modal cannot
    # wedge the tab in a state the persona has no verb to escape
    c.js("window.confirm = () => true; undefined")

    session = {
        "persona": persona,
        "port": port,
        "cdp_port": cdp_port,
        "ws_url": c.ws_url,
        "target_id": c.target_id,
        "db": db,
        "server_pid": server.pid,
        "chrome_pid": chrome.pid,
        "run_dir": str(run_dir),
    }
    session_path(run_dir).write_text(json.dumps(session, indent=2), encoding="utf-8")
    return session


def stop(run_dir: Path) -> None:
    path = session_path(run_dir)
    if not path.exists():
        return
    session = json.loads(path.read_text(encoding="utf-8"))
    for pid in (session["server_pid"], session["chrome_pid"]):
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            pass
    time.sleep(1.5)
    if os.path.exists(session["db"]):
        os.unlink(session["db"])
    if not _port_free(session["port"]):
        raise RuntimeError(f"port {session['port']} still held after stop()")
    path.unlink()
