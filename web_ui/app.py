from __future__ import annotations

from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web_ui.dashboard_service import build_dashboard_snapshot, refresh_dashboard_snapshot


def create_app(report_root: Path | str | None = None) -> FastAPI:
    static_dir = Path(__file__).resolve().parent / "static"
    app = FastAPI(title="Quant System Dashboard")
    app.state.report_root = Path(report_root) if report_root is not None else None
    app.state.refresh_lock = Lock()
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def read_dashboard() -> FileResponse:
        return FileResponse(static_dir / "dashboard.html")

    @app.get("/api/health")
    def read_health() -> dict[str, object]:
        return {"status": "ok", "dashboard": "ready"}

    @app.get("/api/dashboard")
    def read_dashboard_snapshot() -> dict[str, object]:
        return build_dashboard_snapshot(report_root=app.state.report_root)

    @app.post("/api/dashboard/refresh")
    def refresh_dashboard() -> dict[str, object]:
        lock: Lock = app.state.refresh_lock
        if not lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="dashboard refresh already running")
        try:
            return refresh_dashboard_snapshot(report_root=app.state.report_root)
        finally:
            lock.release()

    return app
