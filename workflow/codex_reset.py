#!/usr/bin/env python3
"""Alfred Script Filter for checking Codex usage and reset credits."""

from __future__ import annotations

import json
import os
import sys
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

AUTH_FILE = os.path.expanduser("~/.codex/auth.json")
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
RESET_CREDITS_URL = "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits"
TIMEOUT = 20


def load_auth() -> tuple[str, str | None]:
    with open(AUTH_FILE, encoding="utf-8") as file:
        data = json.load(file)
    return data["tokens"]["access_token"], data["tokens"].get("account_id")


def decode_jwt_account_id(token: str) -> str | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = -len(payload_b64) % 4
        if padding:
            payload_b64 += "=" * padding
        payload = json.loads(urlsafe_b64decode(payload_b64.replace("-", "+").replace("_", "/")))
        auth = payload.get("https://api.openai.com/auth", {})
        return auth.get("chatgpt_account_id")
    except Exception:
        return None


def get_headers(token: str, account_id: str | None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "originator": "Codex Desktop",
        "OAI-Product-Sku": "CODEX",
        "Accept": "application/json",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


def fetch_json(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def is_available_credit(credit: dict[str, Any]) -> bool:
    return str(credit.get("status", "")).lower() == "available"


def format_duration(seconds: Any) -> str:
    if seconds is None:
        return "unknown"

    total_seconds = max(0, int(round(seconds)))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "<1m"


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_expiry(expires_at: str | None, now: datetime) -> str:
    expiry = parse_iso_datetime(expires_at)
    if not expiry:
        return "Expiry unavailable"

    local_expiry = expiry.astimezone()
    local_now = now.astimezone()
    delta_days = (local_expiry.date() - local_now.date()).days
    time_text = local_expiry.strftime("%H:%M")

    if expiry <= now:
        return f"Expired on {local_expiry.strftime('%b %-d, %H:%M')}"
    if delta_days == 0:
        return f"Expires today at {time_text}"
    if delta_days == 1:
        return f"Expires tomorrow at {time_text}"
    if delta_days <= 3:
        return f"Expires in {delta_days} days"
    if delta_days <= 7:
        return f"Expires this week ({local_expiry.strftime('%b %-d')})"
    return f"Expires on {local_expiry.strftime('%b %-d')}"


def summarize_expiry(credits: list[dict[str, Any]], now: datetime) -> str:
    if not credits:
        return "No reset credits available"

    expiries = [parse_iso_datetime(credit.get("expires_at")) for credit in credits]
    valid_expiries = [expiry for expiry in expiries if expiry is not None]
    if not valid_expiries:
        return "Expiry details unavailable"

    earliest = min(valid_expiries)
    if earliest <= now + timedelta(days=1):
        return f"Earliest: {format_expiry(earliest.isoformat(), now)}"
    return f"Earliest expiry: {earliest.astimezone().strftime('%b %-d')}"


def build_usage_items(usage: dict[str, Any] | None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    rate_limit = usage.get("rate_limit") if usage else None
    if not rate_limit:
        return items

    windows = [
        ("primary_window", "5-hour window"),
        ("secondary_window", "Weekly window"),
    ]
    for key, label in windows:
        window = rate_limit.get(key)
        if not window:
            continue
        used = int(window.get("used_percent", 0))
        remaining = max(0, 100 - used)
        reset_after = format_duration(window.get("reset_after_seconds"))
        items.append(
            {
                "title": label,
                "subtitle": f"Used {used}% · Remaining {remaining}% · Resets in about {reset_after}",
                "valid": False,
            }
        )
    return items


def build_reset_summary_item(
    available_count: int,
    available_credits: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    if available_count <= 0:
        detail = "No reset credits available right now"
    elif available_credits:
        detail = summarize_expiry(available_credits, now)
    else:
        detail = "Expiry details were not returned"
    return {
        "title": "Reset credits",
        "subtitle": f"Available: {available_count} · {detail}",
        "valid": False,
    }


def build_credit_items(credits: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, credit in enumerate(credits, start=1):
        title = credit.get("title") or f"Reset credit {index}"
        items.append(
            {
                "title": title,
                "subtitle": format_expiry(credit.get("expires_at"), now),
                "valid": False,
            }
        )
    return items


def build_updated_item(now: datetime) -> dict[str, Any]:
    local_now = now.astimezone()
    return {
        "title": "Last updated",
        "subtitle": local_now.strftime("%H:%M:%S"),
        "valid": False,
    }


def output(items: list[dict[str, Any]]) -> None:
    payload: dict[str, Any] = {"items": items, "skipknowledge": True}
    print(json.dumps(payload, ensure_ascii=False))


def output_message(title: str, subtitle: str) -> None:
    output([{"title": title, "subtitle": subtitle, "valid": False}])


def fetch_usage_and_credits(headers: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    usage = None
    reset_data = None

    try:
        usage = fetch_json(USAGE_URL, headers)
    except HTTPError as error:
        if error.code == 401:
            output_message("Session expired", "Sign in to Codex Desktop again and rerun the workflow.")
            raise SystemExit(0)
        if error.code == 429:
            output_message("Rate limited", "Try the workflow again in a moment.")
            raise SystemExit(0)
    except Exception as exc:
        print(f"[codex_reset] Warning: failed to fetch usage: {exc}", file=sys.stderr)

    try:
        reset_data = fetch_json(RESET_CREDITS_URL, headers)
    except Exception as exc:
        print(f"[codex_reset] Warning: failed to fetch reset credits: {exc}", file=sys.stderr)

    return usage, reset_data


def main() -> None:
    try:
        token, account_id = load_auth()
    except FileNotFoundError:
        output_message("Codex Desktop is not signed in", "Open Codex Desktop, sign in, and trigger the workflow again.")
        return
    except Exception as error:
        output_message("Failed to read local auth state", str(error))
        return

    effective_account_id = decode_jwt_account_id(token) or account_id
    headers = get_headers(token, effective_account_id)
    usage, reset_data = fetch_usage_and_credits(headers)

    now = datetime.now(timezone.utc)

    if not usage and not reset_data:
        output_message("Unable to fetch Codex data", "Check your network connection and try the workflow again.")
        return

    credits = reset_data.get("credits", []) if reset_data else []
    available_credits = [credit for credit in credits if is_available_credit(credit)]

    available_count = 0
    if reset_data is not None:
        available_count = int(reset_data.get("available_count", len(available_credits)) or 0)
    elif usage:
        available_count = int(usage.get("rate_limit_reset_credits", {}).get("available_count", 0) or 0)

    items = []
    items.extend(build_usage_items(usage))
    items.append(build_reset_summary_item(available_count, available_credits, now))
    items.extend(build_credit_items(available_credits, now))
    items.append(build_updated_item(now))

    output(items)


if __name__ == "__main__":
    main()
