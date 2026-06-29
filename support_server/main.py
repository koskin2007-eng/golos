from __future__ import annotations

import math
import os
import tempfile
import time
import wave
from html import escape
from pathlib import Path
from secrets import compare_digest

from fastapi import Cookie, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from support_server.settings import ServerSettings, load_settings
from support_server.storage import (
    Account,
    AccountPayment,
    DiagnosticReport,
    PremiumLicense,
    account_payment_operation_exists,
    apply_paid_account_payment,
    authenticate_account,
    charge_premium_seconds,
    create_account,
    create_account_payment,
    create_client_action,
    create_premium_license,
    find_account_payment_by_order,
    get_account_by_token,
    get_diagnostic_report,
    get_account_payment,
    get_premium_license,
    grant_premium_minutes,
    init_storage,
    list_account_payments,
    list_pending_client_actions_for_license,
    list_diagnostic_reports,
    list_premium_licenses,
    load_update_payload,
    logout_account,
    mark_client_action_for_license,
    mark_account_payment_failed,
    record_event,
    resolve_premium_license,
    resolve_report_archive,
    save_diagnostic_report,
    set_premium_license_active,
    set_account_payment_url,
)
from support_server.yoomoney import (
    YOOMONEY_PROVIDER,
    build_yoomoney_payment_form,
    validate_yoomoney_payment_payload,
    verify_yoomoney_notification,
    yoomoney_is_configured,
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

    @app.post("/api/account/register")
    async def account_register(request: Request) -> dict[str, object]:
        payload = await _read_json_object(request)
        try:
            token, account = create_account(
                server_settings,
                str(payload.get("email") or ""),
                str(payload.get("password") or ""),
                str(payload.get("name") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        license = get_premium_license(server_settings, account.premium_license_id)
        return {
            "ok": True,
            "account_token": token,
            "account": _account_payload(account, license),
        }

    @app.post("/api/account/login")
    async def account_login(request: Request) -> dict[str, object]:
        payload = await _read_json_object(request)
        result = authenticate_account(
            server_settings,
            str(payload.get("email") or ""),
            str(payload.get("password") or ""),
        )
        if result is None:
            raise HTTPException(status_code=401, detail="Неверный email или пароль.")
        token, account = result
        license = get_premium_license(server_settings, account.premium_license_id)
        return {
            "ok": True,
            "account_token": token,
            "account": _account_payload(account, license),
        }

    @app.get("/api/account/me")
    def account_me(x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token")) -> dict[str, object]:
        account = _require_account(server_settings, x_golos_account_token)
        license = get_premium_license(server_settings, account.premium_license_id)
        payments = list_account_payments(server_settings, account.account_id, limit=10)
        return {
            "ok": True,
            "account": _account_payload(account, license),
            "payments": [_payment_payload(payment) for payment in payments],
        }

    @app.post("/api/account/logout")
    def account_logout(x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token")) -> dict[str, object]:
        if x_golos_account_token:
            logout_account(server_settings, x_golos_account_token)
        return {"ok": True}

    @app.post("/api/account/payments")
    async def account_create_payment(
        request: Request,
        x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token"),
    ) -> dict[str, object]:
        account = _require_account(server_settings, x_golos_account_token)
        payload = await _read_json_object(request)
        amount_rub = _safe_int(payload.get("amount_rub"), server_settings.payment_default_amount_rub)
        if amount_rub < server_settings.payment_min_amount_rub or amount_rub > server_settings.payment_max_amount_rub:
            raise HTTPException(
                status_code=400,
                detail=f"Введите сумму от {server_settings.payment_min_amount_rub} до {server_settings.payment_max_amount_rub} руб.",
            )
        provider = "mock" if server_settings.payments_mode == "mock" else server_settings.payments_provider
        payment = create_account_payment(
            server_settings,
            account,
            amount_rub=amount_rub,
            minutes=_payment_minutes_for_amount(server_settings, amount_rub),
            provider=provider,
            description=f"Голос Премиум: {amount_rub} руб.",
        )
        if server_settings.payments_mode == "mock":
            payment = set_account_payment_url(server_settings, payment.payment_id, f"/account/payments/{payment.payment_id}")
            return {"ok": True, "payment": _payment_payload(payment)}

        if provider == YOOMONEY_PROVIDER:
            if not yoomoney_is_configured(server_settings):
                payment = mark_account_payment_failed(
                    server_settings,
                    payment.payment_id,
                    "yoomoney_not_configured",
                    "Онлайн-оплата YooMoney ещё не включена. Попробуйте позже или напишите в поддержку.",
                )
                return {"ok": False, "payment": _payment_payload(payment)}
            payment = set_account_payment_url(
                server_settings,
                payment.payment_id,
                f"/account/payments/{payment.payment_id}/yoomoney",
            )
            return {"ok": True, "payment": _payment_payload(payment)}

        payment = mark_account_payment_failed(
            server_settings,
            payment.payment_id,
            "payment_provider_pending",
            "Онлайн-оплата временно настраивается.",
        )
        return {"ok": False, "payment": _payment_payload(payment)}

    @app.get("/account/payments/{payment_id}", response_class=HTMLResponse)
    def account_payment_detail(payment_id: str):
        payment = get_account_payment(server_settings, payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found.")
        return HTMLResponse(_account_payment_detail_html(server_settings, payment))

    @app.get("/account/payments/{payment_id}/yoomoney", response_class=HTMLResponse)
    def account_payment_yoomoney(payment_id: str):
        payment = get_account_payment(server_settings, payment_id)
        if payment is None:
            raise HTTPException(status_code=404, detail="Payment not found.")
        if payment.provider != YOOMONEY_PROVIDER or payment.status != "pending":
            return RedirectResponse(f"/account/payments/{payment.payment_id}", status_code=303)
        try:
            payment_form = build_yoomoney_payment_form(payment, server_settings)
        except ValueError:
            mark_account_payment_failed(
                server_settings,
                payment.payment_id,
                "yoomoney_not_configured",
                "Онлайн-оплата YooMoney ещё не включена.",
            )
            return RedirectResponse(f"/account/payments/{payment.payment_id}", status_code=303)
        return HTMLResponse(_yoomoney_payment_html(payment, payment_form.action_url, payment_form.fields))

    @app.post("/account/payments/{payment_id}/mock-success", response_class=HTMLResponse)
    def account_payment_mock_success(payment_id: str):
        if server_settings.payments_mode != "mock":
            raise HTTPException(status_code=404, detail="Not found.")
        try:
            apply_paid_account_payment(server_settings, payment_id, provider_payment_id=f"mock-{payment_id[:12]}")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RedirectResponse(f"/account/payments/{payment_id}", status_code=303)

    @app.post("/account/payments/{payment_id}/mock-fail", response_class=HTMLResponse)
    def account_payment_mock_fail(payment_id: str):
        if server_settings.payments_mode != "mock":
            raise HTTPException(status_code=404, detail="Not found.")
        mark_account_payment_failed(server_settings, payment_id, "mock_failed", "Тестовая ошибка оплаты.")
        return RedirectResponse(f"/account/payments/{payment_id}", status_code=303)

    @app.post("/payments/yoomoney/webhook")
    async def yoomoney_webhook(request: Request):
        if not yoomoney_is_configured(server_settings):
            return Response("yoomoney_not_configured", status_code=503)
        form = await request.form()
        payload = {key: str(value) for key, value in form.items()}
        if not verify_yoomoney_notification(payload, server_settings.yoomoney_notification_secret):
            return Response("invalid_sign", status_code=403)

        provider_order_id = payload.get("label") or ""
        operation_id = payload.get("operation_id") or ""
        if not provider_order_id or not operation_id:
            return Response("ignored_missing_required_fields", status_code=200)
        if account_payment_operation_exists(server_settings, YOOMONEY_PROVIDER, operation_id):
            return Response("duplicate_operation", status_code=200)

        payment = find_account_payment_by_order(server_settings, YOOMONEY_PROVIDER, provider_order_id)
        if payment is None:
            return Response("ignored_payment_not_found", status_code=200)
        validation_error = validate_yoomoney_payment_payload(
            payload,
            expected_label=payment.provider_order_id,
            expected_amount_rub=payment.amount_rub,
        )
        if validation_error:
            mark_account_payment_failed(
                server_settings,
                payment.payment_id,
                validation_error,
                "YooMoney вернул платёж с параметрами, которые не прошли проверку.",
            )
            return Response(validation_error, status_code=400)

        apply_paid_account_payment(server_settings, payment.payment_id, provider_payment_id=operation_id)
        return Response("OK", status_code=200)

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

    @app.get("/admin/premium", response_class=HTMLResponse)
    def admin_premium(
        limit: int = 50,
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        licenses = list_premium_licenses(server_settings, limit=limit)
        return HTMLResponse(_premium_admin_html(licenses, limit))

    @app.post("/admin/premium/create", response_class=HTMLResponse)
    def admin_premium_create(
        label: str = Form(""),
        minutes: int = Form(180),
        amount_rub: int = Form(100),
        notes: str = Form(""),
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        if not label.strip():
            licenses = list_premium_licenses(server_settings)
            return HTMLResponse(_premium_admin_html(licenses, error="Укажите имя клиента или комментарий."), status_code=400)
        if minutes <= 0:
            licenses = list_premium_licenses(server_settings)
            return HTMLResponse(_premium_admin_html(licenses, error="Количество минут должно быть больше нуля."), status_code=400)
        license_key, _license = create_premium_license(server_settings, label, minutes, amount_rub, notes)
        licenses = list_premium_licenses(server_settings)
        return HTMLResponse(
            _premium_admin_html(
                licenses,
                created_key=license_key,
                message="Премиум-ключ создан. Скопируйте его клиенту сейчас: повторно ключ не показывается.",
            )
        )

    @app.post("/admin/premium/grant", response_class=HTMLResponse)
    def admin_premium_grant(
        identifier: str = Form(""),
        minutes: int = Form(180),
        amount_rub: int = Form(100),
        notes: str = Form(""),
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        if minutes <= 0:
            licenses = list_premium_licenses(server_settings)
            return HTMLResponse(_premium_admin_html(licenses, error="Количество минут должно быть больше нуля."), status_code=400)
        try:
            grant_premium_minutes(server_settings, identifier, minutes, amount_rub, notes)
        except ValueError as exc:
            licenses = list_premium_licenses(server_settings)
            return HTMLResponse(_premium_admin_html(licenses, error=str(exc)), status_code=404)
        licenses = list_premium_licenses(server_settings)
        return HTMLResponse(_premium_admin_html(licenses, message="Баланс премиум-ключа пополнен."))

    @app.post("/admin/premium/status", response_class=HTMLResponse)
    def admin_premium_status(
        identifier: str = Form(""),
        active: str = Form("yes"),
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        try:
            set_premium_license_active(server_settings, identifier, active == "yes")
        except ValueError as exc:
            licenses = list_premium_licenses(server_settings)
            return HTMLResponse(_premium_admin_html(licenses, error=str(exc)), status_code=404)
        licenses = list_premium_licenses(server_settings)
        return HTMLResponse(_premium_admin_html(licenses, message="Статус премиум-ключа обновлён."))

    @app.post("/admin/premium/action", response_class=HTMLResponse)
    def admin_premium_action(
        identifier: str = Form(""),
        action_type: str = Form("diagnostics_request"),
        message: str = Form(""),
        golos_admin_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
    ):
        redirect = _redirect_to_login_if_admin_needed(server_settings, golos_admin_token)
        if redirect:
            return redirect
        try:
            create_client_action(server_settings, identifier, action_type, message)
        except ValueError as exc:
            licenses = list_premium_licenses(server_settings)
            return HTMLResponse(_premium_admin_html(licenses, error=str(exc)), status_code=400)
        licenses = list_premium_licenses(server_settings)
        return HTMLResponse(_premium_admin_html(licenses, message="Запрос для клиента поставлен в очередь."))

    @app.get("/api/premium/balance")
    def premium_balance(
        x_golos_premium_key: str | None = Header(default=None, alias="X-Golos-Premium-Key"),
        x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token"),
    ) -> dict[str, object]:
        license = resolve_premium_license(server_settings, x_golos_premium_key, x_golos_account_token)
        if license is None or not license.active:
            raise HTTPException(status_code=401, detail="Premium access is invalid.")
        return _premium_license_payload(license)

    @app.post("/api/premium/transcribe")
    async def premium_transcribe(
        file: UploadFile = File(...),
        language: str = Form("ru"),
        duration_seconds: str = Form("0"),
        x_golos_premium_key: str | None = Header(default=None, alias="X-Golos-Premium-Key"),
        x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token"),
    ) -> dict[str, object]:
        license = resolve_premium_license(server_settings, x_golos_premium_key, x_golos_account_token)
        if license is None or not license.active:
            raise HTTPException(status_code=401, detail="Premium access is invalid.")

        content = await file.read(server_settings.max_upload_bytes + 1)
        if len(content) > server_settings.max_upload_bytes:
            raise HTTPException(status_code=400, detail="Audio file is too large.")

        measured_seconds = _wav_duration_seconds(content)
        fallback_seconds = _safe_float(duration_seconds)
        charge_seconds = max(1, math.ceil(measured_seconds or fallback_seconds or 1.0))
        if license.balance_seconds < charge_seconds:
            raise HTTPException(status_code=402, detail="Premium balance is not enough.")

        started = time.perf_counter()
        text, model = _transcribe_with_openai(content, file.filename or "audio.wav", language)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        updated = charge_premium_seconds(
            server_settings,
            license.license_id,
            charge_seconds,
            f"premium_transcribe filename={file.filename or 'audio.wav'}",
        )
        return {
            "ok": True,
            "text": text,
            "model": model,
            "elapsed_ms": round(elapsed_ms, 1),
            "charged_seconds": charge_seconds,
            "balance_minutes": round(updated.balance_seconds / 60, 2),
        }

    @app.get("/api/client/actions")
    def client_actions(
        x_golos_premium_key: str | None = Header(default=None, alias="X-Golos-Premium-Key"),
        x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token"),
    ) -> dict[str, object]:
        license = resolve_premium_license(server_settings, x_golos_premium_key, x_golos_account_token)
        if license is None or not license.active:
            raise HTTPException(status_code=401, detail="Premium access is invalid.")
        actions = list_pending_client_actions_for_license(server_settings, license.license_id)
        return {
            "ok": True,
            "actions": [
                {
                    "action_id": action.action_id,
                    "action_type": action.action_type,
                    "message": action.message,
                    "created_at": action.created_at,
                }
                for action in actions
            ],
        }

    @app.post("/api/client/actions/{action_id}/complete")
    async def client_action_complete(
        action_id: str,
        request: Request,
        x_golos_premium_key: str | None = Header(default=None, alias="X-Golos-Premium-Key"),
        x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token"),
    ) -> dict[str, object]:
        license = resolve_premium_license(server_settings, x_golos_premium_key, x_golos_account_token)
        if license is None or not license.active:
            raise HTTPException(status_code=401, detail="Premium access is invalid.")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON object expected.")
        try:
            action = mark_client_action_for_license(
                server_settings,
                action_id,
                license.license_id,
                str(payload.get("status") or "done"),
                str(payload.get("message") or ""),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "action_id": action.action_id, "status": action.status}

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
        x_golos_premium_key: str | None = Header(default=None, alias="X-Golos-Premium-Key"),
        x_golos_account_token: str | None = Header(default=None, alias="X-Golos-Account-Token"),
    ) -> JSONResponse:
        _require_upload_auth(server_settings, authorization, x_golos_premium_key, x_golos_account_token)
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


async def _read_json_object(request: Request) -> dict[str, object]:
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="JSON object expected.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object expected.")
    return payload


def _require_account(settings: ServerSettings, account_token: str | None) -> Account:
    if not account_token:
        raise HTTPException(status_code=401, detail="Account token is required.")
    account = get_account_by_token(settings, account_token)
    if account is None:
        raise HTTPException(status_code=401, detail="Account session is invalid.")
    return account


def _account_payload(account: Account, license: PremiumLicense | None) -> dict[str, object]:
    balance_seconds = license.balance_seconds if license else 0
    total_granted_seconds = license.total_granted_seconds if license else 0
    total_used_seconds = license.total_used_seconds if license else 0
    return {
        "account_id": account.account_id,
        "email": account.email,
        "name": account.name,
        "active": account.active,
        "email_confirmed": account.email_confirmed,
        "premium_license_id": account.premium_license_id,
        "balance_seconds": balance_seconds,
        "balance_minutes": round(balance_seconds / 60, 2),
        "total_granted_minutes": round(total_granted_seconds / 60, 2),
        "total_used_minutes": round(total_used_seconds / 60, 2),
    }


def _payment_payload(payment: AccountPayment) -> dict[str, object]:
    return {
        "payment_id": payment.payment_id,
        "amount_rub": payment.amount_rub,
        "minutes": payment.minutes,
        "currency": payment.currency,
        "status": payment.status,
        "provider": payment.provider,
        "payment_url": payment.payment_url,
        "description": payment.description,
        "error_code": payment.error_code,
        "error_message": payment.error_message,
        "created_at": payment.created_at,
        "paid_at": payment.paid_at,
    }


def _payment_minutes_for_amount(settings: ServerSettings, amount_rub: int) -> int:
    return max(1, round(int(amount_rub) * settings.premium_minutes_per_100_rub / 100))


def _safe_int(value: object, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return int(default)


def _require_auth(settings: ServerSettings, authorization: str | None) -> None:
    if not settings.support_token:
        return
    expected = f"Bearer {settings.support_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _require_upload_auth(
    settings: ServerSettings,
    authorization: str | None,
    premium_key: str | None,
    account_token: str | None = None,
) -> None:
    if settings.support_token:
        expected = f"Bearer {settings.support_token}"
        if authorization == expected:
            return
        license = resolve_premium_license(settings, premium_key, account_token)
        if license is not None and license.active:
            return
        raise HTTPException(status_code=401, detail="Unauthorized.")


def _transcribe_with_openai(content: bytes, filename: str, language: str) -> tuple[str, str]:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="Server OpenAI API key is not configured.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="openai package is not installed on the server.") from exc

    model = os.getenv("GOLOS_PREMIUM_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
    suffix = Path(filename).suffix or ".wav"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        client = OpenAI()
        with Path(temp_path).open("rb") as audio_file:
            params = {
                "model": model,
                "file": audio_file,
                "response_format": "text",
            }
            if language and language != "auto":
                params["language"] = language
            response = client.audio.transcriptions.create(**params)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass

    if isinstance(response, str):
        return response, model
    return str(getattr(response, "text", str(response))), model


def _wav_duration_seconds(content: bytes) -> float:
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        with wave.open(temp_path, "rb") as audio:
            rate = audio.getframerate() or 1
            return audio.getnframes() / rate
    except Exception:  # noqa: BLE001
        return 0.0
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def _safe_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        <div class="step">Для OpenAI-режима откройте настройки, вкладку распознавания, вставьте API-ключ и нажмите <code>Сохранить</code>.</div>
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
    header nav {{ margin-top:8px; display:flex; gap:14px; flex-wrap:wrap; }}
    header nav a {{ color:#d9f99d; font-size:14px; }}
    main {{ padding:24px 28px; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:14px; }}
    th {{ background:#eef7e7; }}
    a {{ color:var(--green); font-weight:600; text-decoration:none; }}
    .muted {{ color:var(--muted); }}
    .panel {{ background:var(--panel); border:1px solid var(--line); padding:18px; max-width:760px; }}
    .button, button {{ background:var(--green); color:#fff; border:1px solid #0f6630; padding:9px 14px; font-weight:700; cursor:pointer; }}
    input {{ width:100%; max-width:520px; padding:10px; border:1px solid var(--line); font-size:15px; }}
    textarea {{ width:100%; max-width:520px; min-height:72px; padding:10px; border:1px solid var(--line); font-size:15px; font-family:inherit; }}
    code {{ background:#eef7e7; padding:2px 5px; }}
    dl {{ display:grid; grid-template-columns:180px 1fr; gap:8px 14px; }}
    dt {{ color:var(--muted); }}
    dd {{ margin:0; overflow-wrap:anywhere; }}
    .error {{ background:#fff2f2; border:1px solid #f3b7b7; padding:10px 12px; margin-bottom:14px; }}
    .success {{ background:#ecfff1; border:1px solid #a7dfb2; padding:10px 12px; margin-bottom:14px; }}
    .keybox {{ background:#0b1f16; color:#d9f99d; padding:12px; margin:10px 0 16px; overflow-wrap:anywhere; font-size:15px; }}
    .forms {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px; margin-bottom:18px; }}
    .forms .panel {{ max-width:none; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Golos Admin</h1>
      <nav><a href="/admin/diagnostics">Диагностика</a><a href="/admin/premium">Премиум</a><a href="/">Лендинг</a></nav>
    </div>
    {logout_html}
  </header>
  <main>{body}</main>
</body>
</html>"""


def _account_payment_detail_html(settings: ServerSettings, payment: AccountPayment) -> str:
    status_label = {
        "pending": "Ожидает оплаты",
        "paid": "Оплачен",
        "failed": "Ошибка оплаты",
        "canceled": "Отменён",
    }.get(payment.status, payment.status)
    error_html = f'<div class="error">{escape(payment.error_message)}</div>' if payment.error_message else ""
    if settings.payments_mode == "mock" and payment.status == "pending":
        action_html = f"""
        <div class="actions">
          <form method="post" action="/account/payments/{escape(payment.payment_id)}/mock-success">
            <button type="submit">Тест: оплатить успешно</button>
          </form>
          <form method="post" action="/account/payments/{escape(payment.payment_id)}/mock-fail">
            <button class="secondary" type="submit">Тест: ошибка оплаты</button>
          </form>
        </div>
"""
    elif payment.payment_url and payment.status == "pending":
        action_html = f'<p><a class="button" href="{escape(payment.payment_url)}">Перейти к оплате</a></p>'
    else:
        action_html = ""
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Платёж Голос</title>
  <style>
    :root {{ --bg:#f7faf4; --panel:#fff; --ink:#172112; --muted:#607052; --green:#167a3c; --line:#d8e6c8; --yellow:#facc15; }}
    body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); }}
    main {{ max-width:720px; margin:0 auto; padding:36px 18px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); padding:24px; }}
    h1 {{ margin:0 0 12px; font-size:30px; }}
    .muted {{ color:var(--muted); }}
    .detail-list {{ display:grid; gap:10px; margin:20px 0; }}
    .detail-list div {{ display:flex; justify-content:space-between; gap:18px; border-bottom:1px solid var(--line); padding-bottom:10px; }}
    .button, button {{ display:inline-block; background:var(--green); color:#fff; border:1px solid #0f6630; padding:11px 16px; font-weight:700; text-decoration:none; cursor:pointer; }}
    button.secondary {{ background:#fff7c2; color:var(--ink); border-color:#e2c94f; }}
    .actions {{ display:flex; gap:10px; flex-wrap:wrap; }}
    .error {{ background:#fff2f2; border:1px solid #f3b7b7; padding:10px 12px; margin:14px 0; }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <p class="muted">Платёж #{escape(payment.payment_id[:12])}</p>
      <h1>{escape(status_label)}</h1>
      <div class="detail-list">
        <div><span>Сумма</span><strong>{int(payment.amount_rub)} {escape(payment.currency)}</strong></div>
        <div><span>Минуты Голос Премиум</span><strong>{int(payment.minutes)} мин.</strong></div>
        <div><span>Провайдер</span><strong>{escape("Тестовый режим" if settings.payments_mode == "mock" else payment.provider)}</strong></div>
      </div>
      {error_html}
      {action_html}
      <p class="muted">После успешной оплаты вернитесь в программу Голос и нажмите «Обновить баланс».</p>
    </section>
  </main>
</body>
</html>"""


def _yoomoney_payment_html(payment: AccountPayment, action_url: str, fields: dict[str, str]) -> str:
    hidden_fields = "\n".join(
        f'<input type="hidden" name="{escape(name)}" value="{escape(value)}">'
        for name, value in fields.items()
    )
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Переход к оплате Голос</title>
  <style>
    body {{ margin:0; font-family:Segoe UI, Arial, sans-serif; background:#f7faf4; color:#172112; }}
    main {{ max-width:680px; margin:0 auto; padding:36px 18px; }}
    section {{ background:#fff; border:1px solid #d8e6c8; padding:24px; }}
    button {{ background:#167a3c; color:#fff; border:1px solid #0f6630; padding:11px 16px; font-weight:700; cursor:pointer; }}
    .muted {{ color:#607052; }}
  </style>
</head>
<body>
  <main>
    <section>
      <p class="muted">Платёж #{escape(payment.payment_id[:12])}</p>
      <h1>Переход к оплате</h1>
      <p>Сейчас откроется защищённая страница YooMoney. После оплаты баланс Голос пополнится автоматически.</p>
      <p><strong>{int(payment.amount_rub)} {escape(payment.currency)}</strong> за <strong>{int(payment.minutes)} мин.</strong></p>
      <form id="yoomoney-payment-form" method="post" action="{escape(action_url)}">
        {hidden_fields}
        <button type="submit">Перейти в YooMoney</button>
      </form>
      <p class="muted">Если переход не начался автоматически, нажмите кнопку выше.</p>
    </section>
  </main>
  <script>
    window.setTimeout(function () {{
      document.getElementById("yoomoney-payment-form").submit();
    }}, 400);
  </script>
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


def _premium_admin_html(
    licenses: list[PremiumLicense],
    limit: int = 50,
    created_key: str = "",
    message: str = "",
    error: str = "",
) -> str:
    rows = "\n".join(_premium_license_row(license) for license in licenses)
    if not rows:
        rows = '<tr><td colspan="8" class="muted">Премиум-ключей пока нет.</td></tr>'
    message_html = f'<div class="success">{escape(message)}</div>' if message else ""
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    key_html = f'<div class="keybox"><strong>{escape(created_key)}</strong></div>' if created_key else ""
    body = f"""
<h2>Премиум-ключи</h2>
<p class="muted">Ручной MVP монетизации: клиент оплатил 100 рублей, мы создаём ключ и начисляем пакет минут.</p>
{message_html}
{error_html}
{key_html}
<div class="forms">
  <section class="panel">
    <h3>Создать ключ</h3>
    <form method="post" action="/admin/premium/create">
      <p><input type="text" name="label" placeholder="Клиент или комментарий" required></p>
      <p><input type="number" name="minutes" value="180" min="1" step="1" placeholder="Минуты"></p>
      <p><input type="number" name="amount_rub" value="100" min="0" step="1" placeholder="Оплата, рублей"></p>
      <p><textarea name="notes" placeholder="Заметка: перевод, дата, контакт"></textarea></p>
      <p><button type="submit">Создать и начислить</button></p>
    </form>
  </section>
  <section class="panel">
    <h3>Пополнить ключ</h3>
    <form method="post" action="/admin/premium/grant">
      <p><input type="text" name="identifier" placeholder="License ID или полный ключ" required></p>
      <p><input type="number" name="minutes" value="180" min="1" step="1" placeholder="Минуты"></p>
      <p><input type="number" name="amount_rub" value="100" min="0" step="1" placeholder="Оплата, рублей"></p>
      <p><textarea name="notes" placeholder="Заметка о пополнении"></textarea></p>
      <p><button type="submit">Пополнить</button></p>
    </form>
  </section>
</div>
<table>
  <thead>
    <tr>
      <th>Создан</th><th>License ID</th><th>Клиент</th><th>Статус</th>
      <th>Баланс</th><th>Начислено</th><th>Оплата</th><th>Действие</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
<p class="muted">Показаны последние {int(limit)} ключей. Сам ключ хранится только у клиента; в базе виден префикс и хэш.</p>
"""
    return _admin_layout("Premium", body)


def _premium_license_row(license: PremiumLicense) -> str:
    active_text = "активен" if license.active else "выключен"
    next_active = "no" if license.active else "yes"
    button_text = "Выключить" if license.active else "Включить"
    return f"""
<tr>
  <td>{escape(license.created_at)}</td>
  <td><code>{escape(license.license_id)}</code><br><span class="muted">{escape(license.key_prefix)}...</span></td>
  <td>{escape(license.label)}<br><span class="muted">{escape(license.notes)}</span></td>
  <td>{active_text}</td>
  <td>{_format_minutes(license.balance_seconds)}</td>
  <td>{_format_minutes(license.total_granted_seconds)}</td>
  <td>{int(license.total_amount_rub)} руб.</td>
  <td>
    <form method="post" action="/admin/premium/status">
      <input type="hidden" name="identifier" value="{escape(license.license_id)}">
      <input type="hidden" name="active" value="{next_active}">
      <button type="submit">{button_text}</button>
    </form>
    <form method="post" action="/admin/premium/action" style="margin-top:8px">
      <input type="hidden" name="identifier" value="{escape(license.license_id)}">
      <input type="hidden" name="action_type" value="diagnostics_request">
      <input type="hidden" name="message" value="Пожалуйста, отправьте диагностику Голос для разбора ошибки.">
      <button type="submit">Запросить диагностику</button>
    </form>
    <form method="post" action="/admin/premium/action" style="margin-top:8px">
      <input type="hidden" name="identifier" value="{escape(license.license_id)}">
      <input type="hidden" name="action_type" value="update_suggestion">
      <input type="hidden" name="message" value="Доступно служебное обновление Голос. Проверьте обновления в настройках.">
      <button type="submit">Предложить обновление</button>
    </form>
  </td>
</tr>"""


def _premium_license_payload(license: PremiumLicense) -> dict[str, object]:
    return {
        "ok": True,
        "active": license.active,
        "license_id": license.license_id,
        "key_prefix": license.key_prefix,
        "balance_seconds": license.balance_seconds,
        "balance_minutes": round(license.balance_seconds / 60, 2),
        "total_granted_minutes": round(license.total_granted_seconds / 60, 2),
        "total_used_minutes": round(license.total_used_seconds / 60, 2),
        "last_seen_at": license.last_seen_at,
    }


def _format_minutes(seconds: int) -> str:
    return f"{seconds / 60:.1f} мин."


def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


app = create_app()
