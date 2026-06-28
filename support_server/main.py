from __future__ import annotations

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from support_server.settings import ServerSettings, load_settings
from support_server.storage import init_storage, load_update_payload, record_event, save_diagnostic_report


APP_VERSION = "0.1.0"


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    server_settings = settings or load_settings()
    init_storage(server_settings)

    app = FastAPI(title="Golos Support Server", version=APP_VERSION)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "golos-support", "version": APP_VERSION}

    @app.get("/api/update")
    def update() -> dict[str, object]:
        try:
            return load_update_payload(server_settings)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"Update metadata unavailable: {exc}") from exc

    @app.post("/api/events")
    async def events(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, object]:
        _require_auth(server_settings, authorization)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON object expected.")
        remote_addr = request.client.host if request.client else ""
        event_id = record_event(server_settings, payload, remote_addr)
        return {"ok": True, "event_id": event_id}

    @app.post("/api/diagnostics")
    async def diagnostics(
        request: Request,
        file: UploadFile = File(...),
        installation_id: str = Form(""),
        app_version: str = Form(""),
        profile: str = Form(""),
        backend: str = Form(""),
        platform: str = Form(""),
        python: str = Form(""),
        notes: str = Form(""),
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        _require_auth(server_settings, authorization)
        content = await file.read(server_settings.max_upload_bytes + 1)
        metadata = {
            "installation_id": installation_id,
            "app_version": app_version,
            "profile": profile,
            "backend": backend,
            "platform": platform,
            "python": python,
            "notes": notes,
        }
        try:
            record = save_diagnostic_report(server_settings, content, file.filename or "diagnostics.zip", metadata)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return JSONResponse(
            {
                "ok": True,
                "message": "Диагностика отправлена.",
                "report_id": record.report_id,
                "size_bytes": record.size_bytes,
                "sha256": record.sha256,
            }
        )

    return app


def _require_auth(settings: ServerSettings, authorization: str | None) -> None:
    if not settings.support_token:
        return
    expected = f"Bearer {settings.support_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


app = create_app()
