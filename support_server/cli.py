from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from support_server.settings import load_settings
from support_server.storage import (
    create_premium_license,
    get_diagnostic_report,
    get_premium_license,
    grant_premium_minutes,
    init_storage,
    list_diagnostic_reports,
    list_premium_licenses,
    set_premium_license_active,
)


DEFAULT_ENV_FILES = (
    Path("/etc/golos-support/golos-support.env"),
    Path(".env"),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golos support server admin CLI.")
    parser.add_argument("--env-file", default="", help="Optional env file to load before reading settings.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnostics = subparsers.add_parser("diagnostics", help="List diagnostic reports.")
    diagnostics.add_argument("--limit", type=int, default=20)
    diagnostics.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    show = subparsers.add_parser("show", help="Show one diagnostic report.")
    show.add_argument("report_id")
    show.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    premium = subparsers.add_parser("premium", help="Manage premium license keys.")
    premium_subparsers = premium.add_subparsers(dest="premium_command", required=True)

    premium_list = premium_subparsers.add_parser("list", help="List premium licenses.")
    premium_list.add_argument("--limit", type=int, default=20)
    premium_list.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    premium_show = premium_subparsers.add_parser("show", help="Show one premium license.")
    premium_show.add_argument("identifier", help="License id or full license key.")
    premium_show.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    premium_create = premium_subparsers.add_parser("create", help="Create a premium license and print the key once.")
    premium_create.add_argument("--label", required=True)
    premium_create.add_argument("--minutes", type=int, default=180)
    premium_create.add_argument("--amount-rub", type=int, default=100)
    premium_create.add_argument("--notes", default="")
    premium_create.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    premium_grant = premium_subparsers.add_parser("grant", help="Add minutes to an existing premium license.")
    premium_grant.add_argument("identifier", help="License id or full license key.")
    premium_grant.add_argument("--minutes", type=int, required=True)
    premium_grant.add_argument("--amount-rub", type=int, default=0)
    premium_grant.add_argument("--notes", default="")
    premium_grant.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    premium_set_active = premium_subparsers.add_parser("set-active", help="Enable or disable a premium license.")
    premium_set_active.add_argument("identifier", help="License id or full license key.")
    premium_set_active.add_argument("--active", choices=("yes", "no"), required=True)
    premium_set_active.add_argument("--json", action="store_true", help="Print JSON instead of a table.")

    args = parser.parse_args(argv)
    _load_env(args.env_file)
    settings = load_settings()
    init_storage(settings)

    if args.command == "diagnostics":
        reports = list_diagnostic_reports(settings, limit=args.limit)
        if args.json:
            print(json.dumps([_report_to_dict(report) for report in reports], ensure_ascii=False, indent=2))
        else:
            _print_reports_table(reports)
        return 0

    if args.command == "show":
        report = get_diagnostic_report(settings, args.report_id)
        if report is None:
            print(f"Diagnostic report not found: {args.report_id}")
            return 1
        if args.json:
            print(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2))
        else:
            _print_report_details(_report_to_dict(report))
        return 0

    if args.command == "premium":
        if args.premium_command == "list":
            licenses = list_premium_licenses(settings, limit=args.limit)
            if args.json:
                print(json.dumps([_license_to_dict(license) for license in licenses], ensure_ascii=False, indent=2))
            else:
                _print_premium_table(licenses)
            return 0

        if args.premium_command == "show":
            license = get_premium_license(settings, args.identifier)
            if license is None:
                print(f"Premium license not found: {args.identifier}")
                return 1
            if args.json:
                print(json.dumps(_license_to_dict(license), ensure_ascii=False, indent=2))
            else:
                _print_report_details(_license_to_dict(license))
            return 0

        if args.premium_command == "create":
            key, license = create_premium_license(
                settings,
                label=args.label,
                minutes=args.minutes,
                amount_rub=args.amount_rub,
                notes=args.notes,
            )
            payload = {"license_key": key, **_license_to_dict(license)}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print("Premium license created. Show this key to the customer once:")
                print(key)
                print("")
                _print_report_details(_license_to_dict(license))
            return 0

        if args.premium_command == "grant":
            license = grant_premium_minutes(
                settings,
                args.identifier,
                minutes=args.minutes,
                amount_rub=args.amount_rub,
                notes=args.notes,
            )
            if args.json:
                print(json.dumps(_license_to_dict(license), ensure_ascii=False, indent=2))
            else:
                print("Premium license updated.")
                _print_report_details(_license_to_dict(license))
            return 0

        if args.premium_command == "set-active":
            license = set_premium_license_active(settings, args.identifier, args.active == "yes")
            if args.json:
                print(json.dumps(_license_to_dict(license), ensure_ascii=False, indent=2))
            else:
                print("Premium license status updated.")
                _print_report_details(_license_to_dict(license))
            return 0

    parser.error("Unknown command.")
    return 2


def _load_env(env_file: str) -> None:
    candidates = [Path(env_file)] if env_file else list(DEFAULT_ENV_FILES)
    for path in candidates:
        if path.exists():
            _load_env_file(path)
            return


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _report_to_dict(report: Any) -> dict[str, Any]:
    data = asdict(report)
    data["stored_path"] = str(data["stored_path"])
    return data


def _license_to_dict(license: Any) -> dict[str, Any]:
    data = asdict(license)
    data["balance_minutes"] = round(data["balance_seconds"] / 60, 2)
    data["total_granted_minutes"] = round(data["total_granted_seconds"] / 60, 2)
    data["total_used_minutes"] = round(data["total_used_seconds"] / 60, 2)
    return data


def _print_reports_table(reports: list[Any]) -> None:
    if not reports:
        print("No diagnostic reports.")
        return
    header = f"{'created_at':20} {'report_id':12} {'version':8} {'profile':12} {'backend':12} {'size':>10} file"
    print(header)
    print("-" * len(header))
    for report in reports:
        print(
            f"{report.created_at[:20]:20} "
            f"{report.report_id[:12]:12} "
            f"{report.app_version[:8]:8} "
            f"{report.profile[:12]:12} "
            f"{report.backend[:12]:12} "
            f"{report.size_bytes:10} "
            f"{report.original_filename}"
        )


def _print_report_details(report: dict[str, Any]) -> None:
    for key, value in report.items():
        print(f"{key}: {value}")


def _print_premium_table(licenses: list[Any]) -> None:
    if not licenses:
        print("No premium licenses.")
        return
    header = f"{'created_at':20} {'license_id':12} {'active':6} {'balance':>9} {'paid':>7} label"
    print(header)
    print("-" * len(header))
    for license in licenses:
        balance_minutes = license.balance_seconds / 60
        print(
            f"{license.created_at[:20]:20} "
            f"{license.license_id[:12]:12} "
            f"{str(license.active):6} "
            f"{balance_minutes:8.1f}m "
            f"{license.total_amount_rub:6} RUB "
            f"{license.label}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
