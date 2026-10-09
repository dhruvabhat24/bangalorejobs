"""Public Greenhouse/Lever career-board watcher with Telegram alerts."""
import argparse
import html
import json
import logging
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from health import save_scan, utc_now, failure_reason

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "seen.json"
LOG = logging.getLogger("jobs")
TITLE = [
    r"\bdev\s*ops\b", r"\bcloud\s+(?:infrastructure\s+)?engineer\b",
    r"\bsite\s+reliability\b|\bsre\b", r"\blinux\s+(?:systems?\s+)?admin(?:istrator)?\b", r"\b(?:platform|infrastructure|cloud\s+operations|systems?)\s+engineer\b", r"\b(?:junior|associate)\s+(?:devops|cloud|sre|linux)\b"
]
SENIOR = re.compile(r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|architect|head of|internship)\b", re.I)
EXPERIENCE = re.compile(
    r"(?<!\d)(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*(?:years?|yrs?)\b"
    r"|(?<!\d)(\d{1,2})\s*\+\s*(?:years?|yrs?)\b"
    r"|\b(?:minimum|at least)\s+(\d{1,2})\s*(?:years?|yrs?)\b"
    r"|(?<!\d)(\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b", re.I
)

def fetch_json(url, payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(url, data=body, headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "BangaloreJobMonitor/1.0"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=25) as response:
                return json.load(response)
        except (HTTPError, URLError, TimeoutError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def plain(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(value or "")))).strip()

def greenhouse(board):
    url = "https://boards-api.greenhouse.io/v1/boards/" + quote(board, safe="") + "/jobs?content=true"
    for j in fetch_json(url).get("jobs", []):
        yield {"id": "greenhouse:" + board + ":" + str(j["id"]), "source": "Greenhouse/" + board,
               "title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
               "description": plain(j.get("content")), "url": j.get("absolute_url", "")}

def lever(board):
    for offset in range(0, 2000, 100):
        url = "https://api.lever.co/v0/postings/" + quote(board, safe="") + f"?mode=json&skip={offset}&limit=100"
        jobs = fetch_json(url)
        if not isinstance(jobs, list):
            raise ValueError("Unexpected Lever API response")
        for j in jobs:
            yield {"id": "lever:" + board + ":" + str(j["id"]), "source": "Lever/" + board,
                   "title": j.get("text", ""), "location": (j.get("categories") or {}).get("location", ""),
                   "description": plain(" ".join([str(j.get("descriptionPlain") or ""), str(j.get("additionalPlain") or ""), str(j.get("description") or "")])),
                   "url": j.get("hostedUrl", "")}
        if len(jobs) < 100:
            return

def himalayas(query):
    """Free Himalayas remote-job search; location matching remains strict."""
    url = "https://himalayas.app/jobs/api/search?" + urlencode({"q": query, "country": "IN", "sort": "recent", "page": 1})
    response = fetch_json(url)
    jobs = response.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("Unexpected Himalayas response")
    for j in jobs:
        restrictions = j.get("locationRestrictions") or []
        if not isinstance(restrictions, list):
            restrictions = [str(restrictions)]
        location = " ".join([str(j.get("location") or ""), " ".join(map(str, restrictions))])
        yield {"id": "himalayas:" + str(j.get("guid") or j.get("applicationLink")),
               "source": "Himalayas/" + str(j.get("companyName") or "Unknown"),
               "title": j.get("title", ""),
               "location": location,
               "description": plain(j.get("description", "")),
               "url": j.get("applicationLink") or ""}

def ashby(board):
    """Ashby public postings API: listed jobs only, including secondary locations."""
    data = fetch_json("https://api.ashbyhq.com/posting-api/job-board/" + quote(board, safe=""))
    for job in data.get("jobs", []):
        if job.get("isListed") is False:
            continue
        extras = job.get("secondaryLocations") or []
        location = " | ".join([str(job.get("location") or "")] + [str(x.get("location") or "") for x in extras if isinstance(x, dict)])
        yield {"id": "ashby:" + board + ":" + str(job.get("id") or job.get("jobUrl")),
               "source": "Ashby/" + board,
               "title": job.get("title", ""), "location": location,
               "description": plain(job.get("descriptionPlain") or job.get("descriptionHtml") or ""),
               "url": job.get("jobUrl") or job.get("applyUrl") or ""}

def select_boards(provider, boards, cfg, now=None):
    """Cycle large Ashby lists across half-hour slots; scan the full set every ~2.5h."""
    if provider != "ashby":
        return boards
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    size = max(1, int(cfg.get("ashby_batch_size", 18)))
    batches = (len(boards) + size - 1) // size
    slot = (int(now.timestamp()) // 1800) % max(batches, 1)
    return boards[slot * size:(slot + 1) * size]

def years_required(description):
    result = []
    for m in EXPERIENCE.finditer(description[:20000]):
        lo, hi, plus, minimum, exact = m.groups()
        if lo is not None:
            result.append((int(lo), int(hi)))
        elif plus is not None:
            result.append((int(plus), 99))
        elif minimum is not None:
            result.append((int(minimum), 99))
        elif exact is not None:
            result.append((int(exact), int(exact)))
    return result

def filter_stage(job, cfg):
    """Return first failed filter, or eligible. Stage totals are cumulative."""
    title = job["title"]
    if SENIOR.search(title) or not any(re.search(pattern, title, re.I) for pattern in TITLE):
        return "title"
    if not any(city in job["location"].casefold() for city in cfg["locations"]):
        return "location"
    exp = years_required(job["description"])
    if exp and not any(low <= cfg["experience_max"] and high >= cfg["experience_min"] for low, high in exp):
        return "experience"
    if not exp and not cfg.get("allow_unspecified_experience", True):
        return "experience"
    return "eligible"

def matches(job, cfg):
    title = job["title"]
    if SENIOR.search(title) or not any(re.search(pattern, title, re.I) for pattern in TITLE):
        return None
    if not any(city in job["location"].casefold() for city in cfg["locations"]):
        return None
    exp = years_required(job["description"])
    if exp and not any(low <= cfg["experience_max"] and high >= cfg["experience_min"] for low, high in exp):
        return None
    if not exp and not cfg.get("allow_unspecified_experience", True):
        return None
    skills = []  # Match on title, location and experience only.
    junior = bool(re.search(r"\b(?:junior|associate|entry.level|graduate|early.career|fresher)\b", title, re.I))
    return {"score": min(100, 65 + (20 if exp else 0) + (15 if junior else 0)), "skills": skills, "experience": exp}

def send(token, chat_id, text):
    response = fetch_json("https://api.telegram.org/bot" + token + "/sendMessage",
                          {"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
    if not response.get("ok"):
        raise RuntimeError("Telegram rejected message")

def run(dry_run=False):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    first_run = not STATE.exists()
    state = json.loads(STATE.read_text(encoding="utf-8")) if not first_run else {"ids": []}
    seen = set(state.get("ids", []))
    candidates = []
    total = 0
    successful_boards = 0
    diagnostics = []
    stages = {"total": 0, "title": 0, "location": 0, "eligible": 0}
    near_matches = {"location": [], "experience": []}
    current_ids = set()
    current_examples = []
    for provider, all_boards in cfg["sources"].items():
        boards = select_boards(provider, all_boards, cfg)
        loader = {"greenhouse": greenhouse, "lever": lever, "himalayas": himalayas, "ashby": ashby}.get(provider)
        if not loader:
            for board in boards:
                diagnostics.append({"source": f"{provider}/{board}", "status": "failed", "postings": 0, "error": "unsupported provider"})
            LOG.warning("Unsupported provider: %s", provider)
            continue
        for board in boards:
            try:
                jobs = list(loader(board))
                successful_boards += 1
                diagnostics.append({"source": f"{provider}/{board}", "status": "ok" if jobs else "empty", "postings": len(jobs)})
            except Exception as exc:
                reason = failure_reason(exc)
                diagnostics.append({"source": f"{provider}/{board}", "status": "failed", "postings": 0, "error": reason})
                LOG.warning("Failed %s/%s: %s", provider, board, reason)
                continue
            for job in jobs:
                total += 1
                stages["total"] += 1
                rejection = filter_stage(job, cfg)
                if rejection != "title":
                    stages["title"] += 1
                    if rejection != "location":
                        stages["location"] += 1
                        if rejection == "eligible":
                            stages["eligible"] += 1
                if rejection in near_matches and len(near_matches[rejection]) < 2:
                    near_matches[rejection].append({
                        "title": job["title"], "location": job["location"], "url": job["url"]
                    })
                quality_current = matches(job, cfg)
                if quality_current:
                    current_ids.add(job["id"])
                    if len(current_examples) < 3:
                        current_examples.append({"title": job["title"], "url": job["url"]})
                if job["id"] in seen:
                    continue
                quality = quality_current
                if quality:
                    candidates.append((job, quality))
                seen.add(job["id"])
    if not successful_boards:
        if not dry_run:
            save_scan({"at": utc_now(), "boards": diagnostics, "postings": total, "new_matches": 0, "alerts_sent": 0})
        raise RuntimeError("No job boards were reachable; seen history preserved")
    candidates.sort(key=lambda item: item[1]["score"], reverse=True)
    LOG.info("Checked %d postings; %d newly matching", total, len(candidates))
    baseline = first_run and cfg.get("first_run") == "baseline"
    notified = set()
    if not baseline:
        token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if not dry_run and (not token or not chat_id):
            raise RuntimeError("Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Actions secrets")
        for job, match in candidates[:cfg.get("max_alerts_per_run", 20)]:
            message = (f"New Bengaluru Job Match ({match['score']}/100)\n"
                       f"{job['title']}\nLocation: {job['location']}\n"
                       f"Company/board: {job['source']}\nExperience: {match['experience'] or 'Not specified'}\nSkills: {', '.join(match['skills']) or 'Unspecified'}\n{job['url']}")
            if dry_run:
                print(message)
            else:
                send(token, chat_id, message)
                notified.add(job["id"])
    else:
        LOG.info("Initial scan baseline; suppressing alerts for existing postings")
    if not dry_run:
        # Unsent matching jobs beyond the alert cap remain eligible on a later scan.
        if not baseline:
            seen.difference_update(j["id"] for j, _ in candidates if j["id"] not in notified)
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"ids": sorted(seen)}, indent=2) + "\n", encoding="utf-8")
        save_scan({"at": utc_now(), "boards": diagnostics, "postings": total, "new_matches": len(candidates), "alerts_sent": len(notified), "current_matches": len(current_ids), "current_examples": current_examples, "filter_stages": stages, "near_matches": near_matches, "company_boards_configured": sum(len(v) for k,v in cfg["sources"].items() if k in ("greenhouse","lever","ashby")), "company_boards_scanned": sum(1 for b in diagnostics if b["source"].split("/")[0] in ("greenhouse","lever","ashby"))})
        LOG.info("Board health: %d OK, %d empty, %d failed", sum(b["status"] == "ok" for b in diagnostics), sum(b["status"] == "empty" for b in diagnostics), sum(b["status"] == "failed" for b in diagnostics))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
