from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from support_server.settings import load_settings
from support_server.storage import get_diagnostic_report, list_diagnostic_reports


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

    args = parser.parse_args(argv)
    _load_env(args.env_file)
    settings = load_settings()

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


if __name__ == "__main__":
    raise SystemExit(main())
