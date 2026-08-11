#!/usr/bin/env python3
"""Stateful capability smoke for an owner account.

Creates and removes only its own short-lived reminder. No media generation is
called. Workflow mutation is opt-in because it changes active user state.
"""

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx


def check(client, base_url, headers, name, method, path, expected, **kwargs):
    started = time.perf_counter()
    try:
        response = client.request(method, f"{base_url.rstrip('/')}{path}", headers=headers, **kwargs)
        ok = response.status_code in expected
        error = None if ok else f"unexpected_http_{response.status_code}"
        try:
            body = response.json()
        except ValueError:
            body = None
    except httpx.HTTPError as exc:
        response, ok, error, body = None, False, exc.__class__.__name__, None
    return {"case_id": name, "method": method, "path": path,
            "status": response.status_code if response else None, "ok": ok,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": error, "body": body}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", default=os.getenv("ALTER_BASE_URL", "https://api.alterai.ru"))
    parser.add_argument("--check-workflow-mutation", action="store_true")
    args = parser.parse_args()
    token = os.getenv("AUTH_TOKEN", "").strip()
    if not token:
        raise SystemExit("AUTH_TOKEN is required")
    headers = {"Authorization": f"Bearer {token}"}
    records, reminder_id = [], None
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        records.append(check(client, args.base_url, headers, "reminders_before", "GET", "/api/v1/reminders", (200,)))
        created = check(client, args.base_url, headers, "reminder_create", "POST", "/api/v1/reminders", (201,),
                        json={"text": "ALTER capability smoke (auto-cleanup)",
                              "remind_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()})
        records.append(created)
        if created["ok"] and isinstance(created["body"], dict):
            reminder_id = created["body"].get("id")
        records.append(check(client, args.base_url, headers, "reminder_list_after_create", "GET", "/api/v1/reminders", (200,)))
        if reminder_id is not None:
            records.append(check(client, args.base_url, headers, "reminder_delete_cleanup", "DELETE",
                                 f"/api/v1/reminders/{int(reminder_id)}", (200,)))
        else:
            records.append({"case_id": "reminder_delete_cleanup", "ok": False, "status": None,
                            "error": "create_did_not_return_id"})
        records.append(check(client, args.base_url, headers, "workflow_read", "GET", "/api/v1/workflow", (200,)))
        if args.check_workflow_mutation:
            records.append(check(client, args.base_url, headers, "workflow_start", "POST", "/api/v1/workflow/start", (200,),
                                 json={"workflow_id": "finish_task", "goal": "Capability smoke", "steps": ["Проверить", "Завершить"]}))
            records.append(check(client, args.base_url, headers, "workflow_next", "POST", "/api/v1/workflow/next", (200,),
                                 json={"complete": False}))
        records.append(check(client, args.base_url, headers, "action_log_after_smoke", "GET", "/api/v1/action-log", (200,)))
        records.append(check(client, args.base_url, headers, "media_capabilities", "GET", "/api/v1/media/capabilities", (200,)))
        records.append(check(client, args.base_url, headers, "calendar_status", "GET", "/api/v1/calendar/status", (200, 503)))
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = sum(not item["ok"] for item in records)
    print(f"checked={len(records)} failed={failed} output={args.output}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
