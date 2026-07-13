"""Launch the ContentGenie Next.js studio and Python API."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
API_PORT = 31417
WEB_PORT = 31415


def _npm() -> str:
    executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not executable:
        raise RuntimeError("Node.js 20+ and npm are required to run the ContentGenie web studio.")
    return executable


def _frontend_needs_build() -> bool:
    marker = FRONTEND / ".next" / "BUILD_ID"
    if not marker.exists():
        return True
    newest_source = max(
        path.stat().st_mtime
        for path in [*(FRONTEND / "src").rglob("*"), FRONTEND / "package.json", FRONTEND / "next.config.ts"]
        if path.is_file()
    )
    return newest_source > marker.stat().st_mtime


def _prepare_frontend():
    npm = _npm()
    if not (FRONTEND / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
    if _frontend_needs_build():
        print("Building the ContentGenie web studio...")
        subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def _wait_for_api(timeout: float = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", API_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("ContentGenie API did not start in time.")


def _warm_local_image_model():
    try:
        from contentgenie.api_utils.image_api import preloadLocalZImage

        preloadLocalZImage()
        print("ContentGenie image engine is warm and ready.")
    except Exception as error:
        print(f"ContentGenie image warm-up deferred: {error}")


def main():
    os.chdir(ROOT)
    venv_scripts = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    if venv_scripts.exists():
        os.environ["PATH"] = str(venv_scripts) + os.pathsep + os.environ.get("PATH", "")
    _prepare_frontend()

    config = uvicorn.Config("contentgenie.web.api:app", host="127.0.0.1", port=API_PORT, log_level="info")
    api_server = uvicorn.Server(config)
    api_thread = threading.Thread(target=api_server.run, name="contentgenie-api", daemon=True)
    api_thread.start()
    _wait_for_api()
    threading.Thread(target=_warm_local_image_model, name="contentgenie-image-warmup", daemon=True).start()

    print(f"\nContentGenie is ready at http://127.0.0.1:{WEB_PORT}\n")
    npm = _npm()
    try:
        web = subprocess.Popen([npm, "run", "start", "--", "-p", str(WEB_PORT), "-H", "127.0.0.1"], cwd=FRONTEND)
        return web.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        api_server.should_exit = True
        api_thread.join(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
