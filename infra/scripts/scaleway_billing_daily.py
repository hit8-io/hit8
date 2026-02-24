"""
Daily Scaleway cost monitoring: fetch consumptions, aggregate by category,
append one row to Google Sheet (Date, Billing period, Total MTD, Discount MTD, per-category).
Optional: if GMAIL_SERVICE_ACCOUNT is set, send a summary email to jan@hit8.io (from noreply@hit8.io).
Requires: SCW_SECRET_KEY, SCW_ORGANIZATION_ID, DRIVE_SERVICE_ACCOUNT (JSON).
Optional: SCALEWAY_BILLING_SHEET_ID (default: 1lilB-MmxHFmnmMYT_kvZZAK48_jTJkAHkYFKLANIGRY).
"""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
from typing import Any

import gspread  # type: ignore[import-untyped]
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Default sheet ID from plan
DEFAULT_SHEET_ID = "1lilB-MmxHFmnmMYT_kvZZAK48_jTJkAHkYFKLANIGRY"
SCW_BILLING_BASE = "https://api.scaleway.com/billing/v2beta1"
PAGE_SIZE = 100

# Sheet header: date, billing period, totals & discount, then all deltas, then category MTDs
HEADER_ROW = [
    "Date",
    "Billing period",
    "Total MTD",
    "Discount MTD",
    "Total Δ",
]

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _send_gmail(sa_json: str, to: str, subject: str, body: str, send_as: str) -> None:
    """Send one plain-text email via Gmail API (service account with domain-wide delegation)."""
    info = json.loads(sa_json)
    creds = Credentials.from_service_account_info(
        info,
        scopes=[GMAIL_SEND_SCOPE],
        subject=send_as,
    )
    service = build("gmail", "v1", credentials=creds)
    message = MIMEText(body)
    message["to"] = to
    message["from"] = send_as
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def log(event: str, **kwargs: Any) -> None:
    """Structured log to stderr (no print for business logic)."""
    parts = [f"[billing] {event}"]
    for k, v in kwargs.items():
        parts.append(f" {k}={v}")
    sys.stderr.write("".join(parts) + "\n")
    sys.stderr.flush()


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val or not val.strip():
        raise ValueError(f"{name} is required but not set")
    return val.strip()


def money_to_eur(obj: dict[str, Any]) -> float:
    """Convert Scaleway Money (units + nanos) to EUR float."""
    units = int(obj.get("units", 0) or 0)
    nanos = int(obj.get("nanos", 0) or 0)
    return units + nanos / 1e9


def fetch_all_consumptions(
    secret_key: str, organization_id: str, billing_period: str
) -> tuple[list[dict[str, Any]], float | None]:
    """Fetch all consumption pages; return (consumptions, total_discount_untaxed_value)."""
    consumptions: list[dict[str, Any]] = []
    total_discount: float | None = None
    page = 1

    while True:
        url = (
            f"{SCW_BILLING_BASE}/consumptions"
            f"?organization_id={organization_id}"
            f"&billing_period={billing_period}"
            f"&page={page}&page_size={PAGE_SIZE}"
        )
        resp = requests.get(
            url,
            headers={
                "X-Auth-Token": secret_key,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        consumptions.extend(data.get("consumptions") or [])
        if total_discount is None and "total_discount_untaxed_value" in data:
            total_discount = float(data["total_discount_untaxed_value"] or 0)

        total_count = int(data.get("total_count", 0))
        if len(consumptions) >= total_count:
            break
        page += 1

    return consumptions, total_discount


def aggregate_by_category(
    consumptions: list[dict[str, Any]],
) -> tuple[float, dict[str, float], set[str]]:
    """Sum total EUR and per category_name; collect project_ids. Return (total_eur, category_eur, project_ids)."""
    total_eur = 0.0
    by_category: dict[str, float] = {}
    project_ids: set[str] = set()

    for c in consumptions:
        value = c.get("value")
        if not value:
            continue
        eur = money_to_eur(value)
        total_eur += eur
        cat = (c.get("category_name") or "Other").strip()
        by_category[cat] = by_category.get(cat, 0.0) + eur
        pid = c.get("project_id")
        if pid:
            project_ids.add(pid)

    return total_eur, by_category, project_ids


def get_sheet_client(drive_sa_json: str) -> gspread.Client:
    """Build gspread client from service account JSON string."""
    info = json.loads(drive_sa_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def ensure_header(worksheet: gspread.Worksheet, category_columns: list[str]) -> None:
    """If sheet is empty, set row 1 to header: date, period, totals & discount, all deltas, rest (category MTDs)."""
    try:
        row1 = worksheet.row_values(1)
    except Exception:
        row1 = []
    # Header: Date, Billing period, Total MTD, Discount MTD, Total Δ, then Cat Δ for each, then Cat for each
    header = HEADER_ROW + [f"{cat} Δ" for cat in category_columns] + list(category_columns)
    if not row1 or row1[0] != "Date":
        worksheet.update("A1", [header], value_input_option="RAW")
        log("header_written", headers=header)


def read_last_data_row(worksheet: gspread.Worksheet) -> list[Any] | None:
    """Return last row (data row, not header) or None if no data yet."""
    try:
        all_rows = worksheet.get_all_values()
    except Exception:
        return None
    if len(all_rows) < 2:
        return None
    last = all_rows[-1]
    if not last or (last and str(last[0]).strip() == "Date"):
        return None
    return last


def _prev_total_mtd(last_row: list[Any]) -> float:
    """Previous row Total MTD (index 2)."""
    if len(last_row) <= 2:
        return 0.0
    try:
        return float(last_row[2] or 0)
    except (ValueError, TypeError):
        return 0.0


def _prev_category_mtds(
    last_row: list[Any], num_categories: int
) -> list[float]:
    """Parse previous row: category MTDs at indices 5+n .. 5+2n-1."""
    prev: list[float] = []
    n = num_categories
    for i in range(n):
        idx = 5 + n + i
        if idx >= len(last_row):
            prev.append(0.0)
            continue
        try:
            prev.append(float(last_row[idx] or 0))
        except (ValueError, TypeError):
            prev.append(0.0)
    return prev


def main() -> None:
    secret_key = require_env("SCW_SECRET_KEY")
    organization_id = require_env("SCW_ORGANIZATION_ID")
    drive_sa_json = require_env("DRIVE_SERVICE_ACCOUNT")
    sheet_id = os.environ.get("SCALEWAY_BILLING_SHEET_ID", "").strip() or DEFAULT_SHEET_ID

    today = datetime.now(timezone.utc).date()
    billing_period = today.strftime("%Y-%m")

    log("fetch_start", organization_id=organization_id, billing_period=billing_period)
    consumptions, total_discount = fetch_all_consumptions(
        secret_key, organization_id, billing_period
    )
    log("fetch_done", count=len(consumptions), total_discount=total_discount)

    total_mtd_eur, by_category, _ = aggregate_by_category(consumptions)
    category_names = sorted(by_category.keys())
    category_columns = category_names

    client = get_sheet_client(drive_sa_json)
    workbook = client.open_by_key(sheet_id)
    worksheet = workbook.worksheet("Daily")

    ensure_header(worksheet, category_columns)
    last_row = read_last_data_row(worksheet)

    # Per-category and total deltas (blank on 1st of month or when no previous row)
    is_first_of_month = today.day == 1
    if last_row is None or is_first_of_month:
        prev_mtds = [0.0] * len(category_names)
        prev_total = 0.0
        if last_row is None:
            log("first_run", category_diffs="(blank)")
        else:
            log("first_of_month", category_diffs="(blank)")
    else:
        prev_mtds = _prev_category_mtds(last_row, len(category_names))
        prev_total = _prev_total_mtd(last_row)

    total_delta: Any = ""
    if not (is_first_of_month or last_row is None):
        total_delta = round(total_mtd_eur - prev_total, 4)

    discount_val = total_discount if total_discount is not None else ""
    # Column order: date, billing period, totals & discount, all deltas, rest (category MTDs)
    row_values: list[Any] = [
        today.isoformat(),
        billing_period,
        round(total_mtd_eur, 4),
        discount_val,
        total_delta,
    ]
    for i, cat in enumerate(category_names):
        if is_first_of_month or last_row is None:
            row_values.append("")  # category Δ blank
        else:
            row_values.append(round(by_category[cat] - prev_mtds[i], 4))
    for cat in category_names:
        row_values.append(round(by_category[cat], 4))

    worksheet.append_row(row_values, value_input_option="USER_ENTERED")
    log("row_appended", date=today.isoformat(), total_mtd_eur=round(total_mtd_eur, 4))

    gmail_sa = os.environ.get("GMAIL_SERVICE_ACCOUNT", "").strip()
    if gmail_sa:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        total_delta_line = f"Total Δ (EUR): {total_delta}\n" if total_delta != "" else ""
        body = (
            f"Scaleway billing daily job finished successfully.\n"
            f"Date: {today.isoformat()}\n"
            f"Billing period: {billing_period}\n"
            f"Total MTD (EUR): {round(total_mtd_eur, 4)}\n"
            f"{total_delta_line}"
            f"\nSheet: {sheet_url}"
        )
        try:
            _send_gmail(
                gmail_sa,
                to="jan@hit8.io",
                subject="[hit8] Scaleway billing daily completed",
                body=body,
                send_as="noreply@hit8.io",
            )
            log("email_sent", to="jan@hit8.io")
        except Exception as e:
            log("email_failed", error=str(e), error_type=type(e).__name__)
            raise


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("error", error=str(e), error_type=type(e).__name__)
        raise
