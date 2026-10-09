"""Local scan-health recording and Telegram daily summary (stdlib only)."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

HEALTH = Path(__file__).resolve().parent / "data" / "health.json"
DAYS = 14

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def load_health(path=HEALTH):
    if not path.exists():
        return {"scans": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"scans": data.get("scans", [])}

def save_scan(scan, path=HEALTH, now=None):
    now = now or datetime.now(timezone.utc)
    data = load_health(path)
    cutoff = now - timedelta(days=DAYS)
    data["scans"] = [s for s in data["scans"] if datetime.fromisoformat(s["at"].replace("Z","+00:00")) >= cutoff]
    data["scans"].append(scan)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def summarize(data, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    scans = [s for s in data.get("scans", []) if datetime.fromisoformat(s["at"].replace("Z","+00:00")) >= cutoff]
    if not scans:
        return "Bangalore Job Alerts - daily health report\nNo scan history in the past 24 hours. Check GitHub Actions."
    failures = Counter()
    latest = {}
    for scan in scans:
        for b in scan.get("boards", []):
            latest[b["source"]] = b
            if b["status"] == "failed":
                failures[b["source"]] += 1
    total = sum(s.get("postings", 0) for s in scans)
    matches = sum(s.get("new_matches", 0) for s in scans)
    sent = sum(s.get("alerts_sent", 0) for s in scans)
    ok = sum(b["status"] == "ok" for b in latest.values())
    zero = sum(b["status"] == "empty" for b in latest.values())
    bad = sum(b["status"] == "failed" for b in latest.values())
    failed = ", ".join(f"{name} ({count})" for name,count in failures.most_common(8)) or "None"
    return ("Bangalore Job Alerts - last 24h\n"
            f"Scans: {len(scans)} | Listings scanned: {total}\n"
            f"New role matches: {matches} | Alerts sent: {sent}\n"
            f"Latest board states: {ok} OK, {zero} empty, {bad} failed\n"
            f"Failed boards (failure counts): {failed}\n"
            "Note: listing scans count repeated checks, not unique jobs.")

def failure_reason(exc):
    from urllib.error import HTTPError
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, TimeoutError):
        return "timeout"
    return type(exc).__name__
