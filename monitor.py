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
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "data" / "seen.json"
LOG = logging.getLogger("jobs")
TITLE = [
    r"\bdev\s*ops\b", r"\bcloud\s+(?:infrastructure\s+)?engineer\b",
    r"\bsite\s+reliability\b|\bsre\b", r"\blinux\s+(?:systems?\s+)?admin(?:istrator)?\b"
]
SENIOR = re.compile(r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|architect|head of)\b", re.I)
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
    content = (title + " " + job["description"]).casefold()
    skills = [s for s in cfg["skills"] if re.search(r"(?<!\w)" + re.escape(s.casefold()) + r"(?!\w)", content)]
    if len(skills) < cfg.get("minimum_skill_matches", 0):
        return None
    return {"score": min(100, 60 + 5 * len(skills) + (5 if exp else 0)), "skills": skills}

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
    for provider, boards in cfg["sources"].items():
        loader = {"greenhouse": greenhouse, "lever": lever}.get(provider)
        if not loader:
            LOG.warning("Unsupported provider: %s", provider)
            continue
        for board in boards:
            try:
                jobs = list(loader(board))
                successful_boards += 1
            except Exception as exc:
                LOG.warning("Failed %s/%s: %s", provider, board, exc)
                continue
            for job in jobs:
                total += 1
                if job["id"] in seen:
                    continue
                quality = matches(job, cfg)
                if quality:
                    candidates.append((job, quality))
                seen.add(job["id"])
    if not successful_boards:
        raise RuntimeError("No job boards were reachable; state preserved")
    candidates.sort(key=lambda item: item[1]["score"], reverse=True)
    LOG.info("Checked %d postings; %d newly matching", total, len(candidates))
    baseline = first_run and cfg.get("first_run") == "baseline"
    if not baseline:
        token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        if not dry_run and (not token or not chat_id):
            raise RuntimeError("Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Actions secrets")
        for job, match in candidates[:cfg.get("max_alerts_per_run", 20)]:
            message = (f"New Bengaluru Job Match ({match['score']}/100)\n"
                       f"{job['title']}\nLocation: {job['location']}\n"
                       f"Source: {job['source']}\nSkills: {', '.join(match['skills']) or 'Unspecified'}\n{job['url']}")
            if dry_run:
                print(message)
            else:
                send(token, chat_id, message)
    else:
        LOG.info("Initial scan baseline; suppressing alerts for existing postings")
    if not dry_run:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"ids": sorted(seen)}, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
