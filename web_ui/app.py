from __future__ import annotations

from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web_ui.dashboard_service import build_dashboard_snapshot, refresh_dashboard_snapshot


def create_app(report_root: Path | str | None = None) -> FastAPI:
    static_dir = Path(__file__).resolve().parent / "static"
    app = FastAPI(title="Quant System Dashboard")
    app.state.report_root = Path(report_root) if report_root is not None else None
    app.state.refresh_lock = Lock()
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    no_cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}

    @app.get("/")
    def read_dashboard() -> FileResponse:
        return FileResponse(static_dir / "dashboard.html", headers=no_cache_headers)

    @app.get("/api/health")
    def read_health() -> dict[str, object]:
        return {"status": "ok", "dashboard": "ready"}

    @app.get("/api/dashboard")
    def read_dashboard_snapshot() -> JSONResponse:
        return JSONResponse(build_dashboard_snapshot(report_root=app.state.report_root), headers=no_cache_headers)

    @app.post("/api/dashboard/refresh")
    def refresh_dashboard() -> JSONResponse:
        lock: Lock = app.state.refresh_lock
        if not lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="dashboard refresh already running")
        try:
            return JSONResponse(refresh_dashboard_snapshot(report_root=app.state.report_root), headers=no_cache_headers)
        finally:
            lock.release()

    return app
