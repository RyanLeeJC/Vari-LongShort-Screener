"""FastAPI app: serves the Vite dashboard and refreshes screener data on demand."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "longshort-screener" / "dist"
DATA = ROOT / "longshort-screener" / "public" / "screener.data.json"

_rebuild_lock = threading.Lock()


def rebuild() -> None:
    subprocess.run([sys.executable, "scripts/build_screener_data.py"], check=True, cwd=ROOT)
    if not DATA.is_file():
        raise RuntimeError("build_screener_data.py did not write screener.data.json")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with _rebuild_lock:
        try:
            rebuild()
        except Exception as exc:
            if DATA.is_file():
                print(f"Startup refresh failed, using committed screener.data.json: {exc}", flush=True)
            else:
                raise
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/api/refresh")
def refresh():
    try:
        with _rebuild_lock:
            rebuild()
            return json.loads(DATA.read_text(encoding="utf-8"))
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=502, detail=f"Data refresh failed (exit {e.returncode})") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/screener.data.json")
def screener_data():
    if not DATA.is_file():
        raise HTTPException(status_code=503, detail="Screener data not ready")
    return FileResponse(DATA, media_type="application/json")


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="static")
else:

    @app.get("/")
    def not_built():
        raise HTTPException(status_code=503, detail="Dashboard not built — run ./scripts/render_build.sh")
