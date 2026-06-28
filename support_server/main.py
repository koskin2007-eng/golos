from __future__ import annotations

from html import escape
from secrets import compare_digest

from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from support_server.settings import ServerSettings, load_settings
from support_server.storage import (
    DiagnosticReport,
    get_diagnostic_report,
    init_storage,
    list_diagnostic_reports,
    load_update_payload,
    record_event,
    resolve_report_archive,
    save_diagnostic_report,
)


APP_VERSION = "0.1.0"
ADMIN_COOKIE_NAME = "golos_admin_token"


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

    @app.get("/admin", response_class=HTMLResponse)
    def admin_root(golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME)):
        if _is_admin_authorized(server_settings, golos_admin_token):
            return RedirectResponse("/admin/diagnostics", status_code=303)
        return RedirectResponse("/admin/login", status_code=303)

    @app.get("/admin/login", response_class=HTMLResponse)
    def admin_login():
        _ensure_admin_enabled(server_settings)
        return HTMLResponse(_admin_login_html())

    @app.post("/admin/login")
    def admin_login_post(token: str = Form("")):
        _ensure_admin_enabled(server_settings)
        if not _is_admin_authorized(server_settings, token):
            return HTMLResponse(_admin_login_html(error="Invalid admin token."), status_code=401)
        response = RedirectResponse("/admin/diagnostics", status_code=303)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            token,
            max_age=8 * 60 * 60,
            httponly=True,
            samesite="strict",
        )
        return response

    @app.post("/admin/logout")
    def admin_logout():
        response = RedirectResponse("/admin/login", status_code=303)
        response.delete_cookie(ADMIN_COOKIE_NAME)
        return response

    @app.get("/admin/diagnostics", response_class=HTMLResponse)
    def admin_diagnostics(
        limit: int = 50,
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        reports = list_diagnostic_reports(server_settings, limit=limit)
        return HTMLResponse(_diagnostics_list_html(reports, limit))

    @app.get("/admin/diagnostics/{report_id}", response_class=HTMLResponse)
    def admin_diagnostic_detail(
        report_id: str,
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        report = get_diagnostic_report(server_settings, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Diagnostic report not found.")
        return HTMLResponse(_diagnostic_detail_html(report))

    @app.get("/admin/diagnostics/{report_id}/download")
    def admin_diagnostic_download(
        report_id: str,
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        report = get_diagnostic_report(server_settings, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Diagnostic report not found.")
        try:
            archive_path = resolve_report_archive(server_settings, report)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Diagnostic archive file not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=archive_path.name,
        )

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


def _ensure_admin_enabled(settings: ServerSettings) -> None:
    if not settings.admin_token:
        raise HTTPException(status_code=404, detail="Admin is disabled.")


def _require_admin(settings: ServerSettings, token: str | None) -> None:
    _ensure_admin_enabled(settings)
    if not _is_admin_authorized(settings, token):
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _redirect_to_login_if_admin_needed(settings: ServerSettings, token: str | None):
    _ensure_admin_enabled(settings)
    if _is_admin_authorized(settings, token):
        return None
    return RedirectResponse("/admin/login", status_code=303)


def _is_admin_authorized(settings: ServerSettings, token: str | None) -> bool:
    if not settings.admin_token or not token:
        return False
    return compare_digest(token, settings.admin_token)


def _admin_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - Golos Admin</title>
  <style>
    :root {{ color-scheme: light; --bg:#f7faf4; --panel:#ffffff; --ink:#172112; --muted:#607052; --green:#167a3c; --line:#d8e6c8; --yellow:#facc15; }}
    body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ background:#164e2e; color:#fff; padding:18px 28px; display:flex; align-items:center; justify-content:space-between; }}
    header h1 {{ font-size:22px; margin:0; }}
    main {{ padding:24px 28px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:14px; }}
    th {{ background:#eef7e7; }}
    a {{ color:var(--green); font-weight:600; text-decoration:none; }}
    .muted {{ color:var(--muted); }}
    .panel {{ background:var(--panel); border:1px solid var(--line); padding:18px; max-width:760px; }}
    .button, button {{ background:var(--green); color:#fff; border:1px solid #0f6630; padding:9px 14px; font-weight:700; cursor:pointer; }}
    input {{ width:100%; max-width:520px; padding:10px; border:1px solid var(--line); font-size:15px; }}
    code {{ background:#eef7e7; padding:2px 5px; }}
    dl {{ display:grid; grid-template-columns:180px 1fr; gap:8px 14px; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    .error {{ background:#fff2f2; border:1px solid #f3b7b7; padding:10px 12px; margin-bottom:14px; }}
  </style>
</head>
<body>
  <header>
    <h1>Golos Admin</h1>
    <form method="post" action="/admin/logout"><button type="submit">Logout</button></form>
  </header>
  <main>{body}</main>
</body>
</html>"""


def _admin_login_html(error: str = "") -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    body = f"""
<section class="panel">
  <h2>Admin login</h2>
  <p class="muted">Enter the private admin token. This page must be opened only through a private path such as an SSH tunnel.</p>
  {error_html}
  <form method="post" action="/admin/login">
    <p><input type="password" name="token" autocomplete="current-password" autofocus></p>
    <p><button type="submit">Open diagnostics</button></p>
  </form>
</section>
"""
    return _admin_layout("Login", body)


def _diagnostics_list_html(reports: list[DiagnosticReport], limit: int) -> str:
    rows = "\n".join(
        f"""
<tr>
  <td><a href="/admin/diagnostics/{escape(report.report_id)}">{escape(report.created_at)}</a></td>
  <td><code>{escape(report.report_id[:12])}</code></td>
  <td>{escape(report.app_version)}</td>
  <td>{escape(report.profile)}</td>
  <td>{escape(report.backend)}</td>
  <td>{_format_bytes(report.size_bytes)}</td>
  <td>{escape(report.original_filename)}</td>
</tr>"""
        for report in reports
    )
    if not rows:
        rows = '<tr><td colspan="7" class="muted">No diagnostic reports yet.</td></tr>'
    body = f"""
<h2>Diagnostic reports</h2>
<p class="muted">Showing latest {int(limit)} reports. Public nginx access to /admin should stay blocked.</p>
<table>
  <thead>
    <tr>
      <th>Created</th><th>Report</th><th>App</th><th>Profile</th><th>Backend</th><th>Size</th><th>File</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""
    return _admin_layout("Diagnostics", body)


def _diagnostic_detail_html(report: DiagnosticReport) -> str:
    body = f"""
<p><a href="/admin/diagnostics">Back to diagnostics</a></p>
<section class="panel">
  <h2>Diagnostic report</h2>
  <dl>
    <dt>Report id</dt><dd><code>{escape(report.report_id)}</code></dd>
    <dt>Created</dt><dd>{escape(report.created_at)}</dd>
    <dt>Installation id</dt><dd>{escape(report.installation_id)}</dd>
    <dt>App version</dt><dd>{escape(report.app_version)}</dd>
    <dt>Profile</dt><dd>{escape(report.profile)}</dd>
    <dt>Backend</dt><dd>{escape(report.backend)}</dd>
    <dt>Platform</dt><dd>{escape(report.platform)}</dd>
    <dt>Original file</dt><dd>{escape(report.original_filename)}</dd>
    <dt>Stored path</dt><dd><code>{escape(str(report.stored_path))}</code></dd>
    <dt>Size</dt><dd>{_format_bytes(report.size_bytes)}</dd>
    <dt>SHA256</dt><dd><code>{escape(report.sha256)}</code></dd>
    <dt>Notes</dt><dd>{escape(report.notes)}</dd>
  </dl>
  <p><a class="button" href="/admin/diagnostics/{escape(report.report_id)}/download">Download ZIP</a></p>
</section>
"""
    return _admin_layout("Diagnostic detail", body)


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


app = create_app()
