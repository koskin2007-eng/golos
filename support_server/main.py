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
from voice_input.version import APP_VERSION as DESKTOP_APP_VERSION
from voice_input.version import GITHUB_REPOSITORY


APP_VERSION = "0.1.0"
ADMIN_COOKIE_NAME = "golos_admin_token"
DOWNLOAD_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases/latest/download/Golos-win64.zip"
RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases/latest"


def create_app(settings: ServerSettings | None = None) -> FastAPI:
    server_settings = settings or load_settings()
    init_storage(server_settings)

    app = FastAPI(title="Golos Support Server", version=APP_VERSION)

    @app.get("/", response_class=HTMLResponse)
    def landing():
        return HTMLResponse(_landing_html())

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
    def admin_login_post(
        username: str = Form(""),
        password: str = Form(""),
        token: str = Form(""),
    ):
        _ensure_admin_enabled(server_settings)
        submitted_password = password or token
        if not _is_admin_login_valid(server_settings, username, submitted_password):
            return HTMLResponse(_admin_login_html(error="Неверный логин или пароль."), status_code=401)
        response = RedirectResponse("/admin/diagnostics", status_code=303)
        response.set_cookie(
            ADMIN_COOKIE_NAME,
            _admin_password(server_settings),
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
    if not _admin_password(settings):
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
    password = _admin_password(settings)
    if not password or not token:
        return False
    return compare_digest(token, password)


def _is_admin_login_valid(settings: ServerSettings, username: str, password: str) -> bool:
    expected_username = settings.admin_username or "admin"
    expected_password = _admin_password(settings)
    if not expected_password:
        return False
    return compare_digest(username.strip(), expected_username) and compare_digest(password, expected_password)


def _admin_password(settings: ServerSettings) -> str:
    return settings.admin_password or settings.admin_token


def _landing_html() -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Голос - Windows-программа для диктовки текста в любое активное окно.">
  <title>Голос - голосовой ввод для Windows</title>
  <style>
    :root {{
      color-scheme: light;
      --bg:#f7fbf2;
      --ink:#101b13;
      --muted:#51614b;
      --green:#14783d;
      --green-dark:#0e4f2d;
      --blue:#155fc7;
      --yellow:#f9d923;
      --panel:#ffffff;
      --line:#d8e6c8;
      --soft:#eef8e8;
      --shadow:0 18px 50px rgba(15, 79, 45, .15);
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); line-height:1.55; }}
    a {{ color:inherit; }}
    .topbar {{ position:sticky; top:0; z-index:10; background:rgba(247,251,242,.94); border-bottom:1px solid var(--line); backdrop-filter:blur(10px); }}
    .nav {{ max-width:1120px; margin:0 auto; padding:14px 22px; display:flex; align-items:center; justify-content:space-between; gap:20px; }}
    .brand {{ display:flex; align-items:center; gap:12px; font-weight:850; font-size:20px; }}
    .mark {{ width:36px; height:36px; border:2px solid var(--yellow); background:var(--green); display:grid; place-items:center; color:#fff; font-weight:900; }}
    .navlinks {{ display:flex; align-items:center; gap:18px; color:var(--muted); font-size:14px; }}
    .navlinks a {{ text-decoration:none; }}
    .hero {{ background:#0d3824; color:#fff; }}
    .hero-inner {{ max-width:1120px; min-height:640px; margin:0 auto; padding:70px 22px 42px; display:grid; grid-template-columns:minmax(0, 1.03fr) minmax(320px, .97fr); align-items:center; gap:42px; }}
    .eyebrow {{ color:#ffe86a; font-weight:750; margin:0 0 12px; }}
    h1 {{ margin:0; font-size:56px; line-height:1.03; letter-spacing:0; max-width:760px; }}
    .lead {{ margin:22px 0 0; font-size:20px; max-width:690px; color:#e7f5df; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:30px; }}
    .button {{ display:inline-flex; align-items:center; justify-content:center; min-height:46px; padding:12px 18px; border:1px solid transparent; font-weight:800; text-decoration:none; transition:transform .12s ease, box-shadow .12s ease, background .12s ease; }}
    .button:hover {{ transform:translateY(-1px); }}
    .button:active {{ transform:translateY(0); box-shadow:none; }}
    .button.primary {{ background:var(--yellow); color:#18210e; border-color:#ffe671; box-shadow:0 10px 25px rgba(249,217,35,.22); }}
    .button.secondary {{ background:#ffffff; color:var(--green-dark); border-color:#d8efd0; }}
    .button.outline {{ background:transparent; color:#fff; border-color:rgba(255,255,255,.45); }}
    .version {{ margin-top:14px; color:#cfe8c3; font-size:14px; }}
    .product-shot {{ background:#fbfff6; color:var(--ink); border:1px solid rgba(255,255,255,.18); box-shadow:var(--shadow); overflow:hidden; }}
    .shot-top {{ background:#155b35; color:#fff; padding:18px 20px; display:flex; justify-content:space-between; align-items:center; }}
    .shot-title {{ display:flex; align-items:center; gap:10px; font-weight:850; font-size:22px; }}
    .shot-status {{ background:#1d7d43; padding:8px 12px; font-weight:800; font-size:13px; }}
    .shot-body {{ padding:22px; }}
    .tabs {{ display:flex; flex-wrap:wrap; gap:6px; border-bottom:1px solid var(--line); margin-bottom:18px; }}
    .tab {{ padding:9px 12px; background:#e7eadf; border:1px solid #c7d0bc; border-bottom:0; font-weight:700; font-size:13px; }}
    .tab.active {{ background:#14b861; color:#fff; border-color:#0f984f; }}
    .field {{ display:grid; grid-template-columns:150px 1fr; gap:10px; align-items:center; margin:12px 0; font-size:14px; }}
    .select, .inputline {{ border:1px solid #b9c7ad; background:#fff; min-height:34px; padding:7px 10px; }}
    .check {{ display:flex; align-items:center; gap:9px; margin-top:16px; font-size:14px; }}
    .tick {{ width:18px; height:18px; border:2px solid var(--green); background:#e9ffe9; }}
    section {{ max-width:1120px; margin:0 auto; padding:64px 22px; }}
    .section-head {{ max-width:760px; margin-bottom:26px; }}
    h2 {{ margin:0 0 12px; font-size:34px; line-height:1.15; letter-spacing:0; }}
    .section-head p {{ margin:0; color:var(--muted); font-size:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:16px; }}
    .card {{ background:var(--panel); border:1px solid var(--line); padding:22px; box-shadow:0 8px 22px rgba(17, 47, 20, .06); }}
    .card h3 {{ margin:0 0 8px; font-size:20px; }}
    .card p {{ margin:0; color:var(--muted); }}
    .steps {{ counter-reset:step; display:grid; gap:12px; }}
    .step {{ counter-increment:step; background:var(--panel); border:1px solid var(--line); padding:18px 20px 18px 64px; position:relative; }}
    .step::before {{ content:counter(step); position:absolute; left:20px; top:18px; width:28px; height:28px; display:grid; place-items:center; background:var(--green); color:#fff; font-weight:900; }}
    code {{ background:#eaf5e3; padding:2px 6px; overflow-wrap:anywhere; }}
    .download-band {{ background:#103f29; color:#fff; }}
    .download-band section {{ padding-top:52px; padding-bottom:52px; display:flex; align-items:center; justify-content:space-between; gap:24px; }}
    .download-band p {{ color:#dff0d8; margin:8px 0 0; }}
    .admin-footer {{ background:#0b1f16; color:#d9ead4; }}
    .admin-footer section {{ padding-top:38px; padding-bottom:38px; display:flex; align-items:center; justify-content:space-between; gap:20px; }}
    .admin-footer h2 {{ font-size:24px; color:#fff; }}
    .admin-footer p {{ margin:6px 0 0; color:#a8bea2; }}
    @media (max-width:860px) {{
      .nav {{ align-items:flex-start; }}
      .navlinks {{ display:none; }}
      .hero-inner {{ min-height:auto; grid-template-columns:1fr; padding-top:44px; }}
      h1 {{ font-size:42px; }}
      .lead {{ font-size:18px; }}
      .grid {{ grid-template-columns:1fr; }}
      .download-band section, .admin-footer section {{ align-items:flex-start; flex-direction:column; }}
      .field {{ grid-template-columns:1fr; }}
    }}
    @media (max-width:520px) {{
      h1 {{ font-size:34px; }}
      h2 {{ font-size:28px; }}
      .actions, .button {{ width:100%; }}
      .product-shot {{ margin-left:-8px; margin-right:-8px; }}
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <nav class="nav" aria-label="Главная навигация">
      <div class="brand"><span class="mark">Г</span><span>Голос</span></div>
      <div class="navlinks">
        <a href="#features">Возможности</a>
        <a href="#install">Установка</a>
        <a href="#download">Скачать</a>
      </div>
    </nav>
  </header>

  <main>
    <div class="hero">
      <div class="hero-inner">
        <div>
          <p class="eyebrow">Голосовой ввод для Windows</p>
          <h1>Говорите, отпускаете клавишу, текст появляется в нужном окне.</h1>
          <p class="lead">Голос работает в фоне, записывает микрофон только пока удерживается горячая клавиша, распознаёт речь и вставляет готовый текст в браузер, Telegram, Word, CRM или Google Docs.</p>
          <div class="actions">
            <a class="button primary" href="{DOWNLOAD_URL}">Скачать для Windows</a>
            <a class="button secondary" href="#install">Как установить</a>
            <a class="button outline" href="{RELEASES_URL}">Страница релиза</a>
          </div>
          <div class="version">Актуальная версия проекта: {escape(DESKTOP_APP_VERSION)}. Пакет скачивается как ZIP, внутри находится приложение Golos.</div>
        </div>
        <div class="product-shot" aria-label="Вид окна настроек Голос">
          <div class="shot-top">
            <div class="shot-title"><span class="mark">Г</span><span>Голос</span></div>
            <div class="shot-status">F8 готова</div>
          </div>
          <div class="shot-body">
            <div class="tabs">
              <div class="tab">Главное</div>
              <div class="tab active">Распознавание</div>
              <div class="tab">Диагностика</div>
              <div class="tab">Обновления</div>
            </div>
            <div class="field"><strong>Профиль</strong><div class="select">База - локально, быстрые настройки</div></div>
            <div class="field"><strong>Режим</strong><div class="inputline">Локальное распознавание на компьютере</div></div>
            <div class="check"><span class="tick"></span><span>GPT может исправлять ошибки после распознавания</span></div>
          </div>
        </div>
      </div>
    </div>

    <section id="features">
      <div class="section-head">
        <h2>Что умеет программа</h2>
        <p>Минимум лишнего интерфейса: нажали клавишу, продиктовали, отпустили, получили текст.</p>
      </div>
      <div class="grid">
        <article class="card"><h3>Push-to-talk</h3><p>Запись идёт только пока удерживается горячая клавиша, по умолчанию F8.</p></article>
        <article class="card"><h3>Локальное распознавание</h3><p>Базовый режим работает на вашем компьютере и не отправляет аудио в интернет.</p></article>
        <article class="card"><h3>OpenAI-режим</h3><p>Для сложной диктовки можно включить распознавание через OpenAI или GPT-исправление текста.</p></article>
        <article class="card"><h3>Вставка в любое окно</h3><p>Текст вставляется через буфер обмена и Ctrl+V в активную программу Windows.</p></article>
        <article class="card"><h3>Автозапуск</h3><p>Приложение можно добавить в меню Пуск и запускать вместе с Windows.</p></article>
        <article class="card"><h3>Диагностика</h3><p>Если что-то пошло не так, программа собирает безопасный архив для поддержки.</p></article>
      </div>
    </section>

    <section id="install">
      <div class="section-head">
        <h2>Как установить и запустить</h2>
        <p>Для обычной установки скачайте ZIP с GitHub Release, распакуйте папку и запустите приложение.</p>
      </div>
      <div class="steps">
        <div class="step">Скачайте <code>Golos-win64.zip</code> по ссылке ниже.</div>
        <div class="step">Распакуйте архив в удобную папку, например <code>C:\\Golos</code>.</div>
        <div class="step">Запустите приложение Golos из распакованной папки.</div>
        <div class="step">Откройте настройки из значка в трее, выберите профиль распознавания и проверьте горячую клавишу.</div>
        <div class="step">Для OpenAI-режима добавьте свой API-ключ в локальный файл <code>.env</code>.</div>
      </div>
    </section>

    <section>
      <div class="section-head">
        <h2>Режимы распознавания</h2>
        <p>Можно начать с локального профиля, а затем включить более точный интернет-режим, если качество диктовки важнее автономности.</p>
      </div>
      <div class="grid">
        <article class="card"><h3>База</h3><p>Локально на компьютере, рабочий баланс скорости и качества.</p></article>
        <article class="card"><h3>Small</h3><p>Локально, обычно точнее, но заметно медленнее на слабом ПК.</p></article>
        <article class="card"><h3>Tiny</h3><p>Локально и быстро, но качество русского текста ниже.</p></article>
        <article class="card"><h3>OpenAI</h3><p>Распознавание через интернет с помощью модели OpenAI.</p></article>
        <article class="card"><h3>GPT-исправление</h3><p>Локальная модель распознаёт, а GPT приводит текст в более чистый вид.</p></article>
        <article class="card"><h3>Диагностика</h3><p>Архив с логами можно отправить на сервер поддержки для разбора ошибки.</p></article>
      </div>
    </section>

    <div class="download-band" id="download">
      <section>
        <div>
          <h2>Скачать Голос для Windows</h2>
          <p>Последний публичный релиз лежит на GitHub. Внутри архива находится готовая программа для запуска.</p>
        </div>
        <a class="button primary" href="{DOWNLOAD_URL}">Скачать Golos-win64.zip</a>
      </section>
    </div>
  </main>

  <footer class="admin-footer">
    <section>
      <div>
        <h2>Администрирование</h2>
        <p>Закрытая зона для просмотра диагностики и служебной информации.</p>
      </div>
      <a class="button outline" href="/admin/login">Вход в админку</a>
    </section>
  </footer>
</body>
</html>"""


def _admin_layout(title: str, body: str, show_logout: bool = True) -> str:
    logout_html = '<form method="post" action="/admin/logout"><button type="submit">Выйти</button></form>' if show_logout else ""
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
    {logout_html}
  </header>
  <main>{body}</main>
</body>
</html>"""


def _admin_login_html(error: str = "") -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    body = f"""
<section class="panel">
  <h2>Вход в админку</h2>
  <p class="muted">Введите служебный логин и пароль. Доступ к диагностике открыт только после входа.</p>
  {error_html}
  <form method="post" action="/admin/login">
    <p><input type="text" name="username" autocomplete="username" placeholder="Логин" autofocus></p>
    <p><input type="password" name="password" autocomplete="current-password" placeholder="Пароль"></p>
    <p><button type="submit">Открыть диагностику</button></p>
  </form>
</section>
"""
    return _admin_layout("Login", body, show_logout=False)


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
<p class="muted">Показаны последние {int(limit)} отчётов. Доступ к диагностике открыт только после входа.</p>
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
