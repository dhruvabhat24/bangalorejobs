# Free Bangalore Job Alerts (Telegram)

A free Python + GitHub Actions monitor for **DevOps Engineer, Cloud Engineer, Site Reliability Engineer, and Linux Administrator** roles in **Bangalore/Bengaluru**. Preferred experience: **1–2 years**; skills: Docker, Git, Kubernetes, Linux, Python, Terraform, Azure, GCP, Prometheus.

## What it does
- Queries the configured companies' **public Greenhouse and Lever job boards**.
- Matches role, Bangalore location, experience requirements when specified, and skill keywords.
- Suppresses senior/lead/manager titles.
- Scores relevance, remembers seen job IDs and sends Telegram alerts for new matches.
- Runs every 30 minutes when GitHub Actions scheduling executes; GitHub may delay/skip scheduled runs.

**Coverage caveat:** This is NOT an internet-wide search. You must expand `config.json` with relevant company Greenhouse/Lever board identifiers. The included boards are starter examples, and might not contain matching jobs. Other platforms require separate authorized integrations.

## Set up Telegram
1. Message [@BotFather](https://t.me/BotFather), enter `/newbot`, follow instructions, and keep the bot token private.
2. Open your new bot and send `/start`.
3. In your own browser, visit `https://api.telegram.org/botYOUR_TOKEN/getUpdates` (replace YOUR_TOKEN), and find `message.chat.id`. Don't share the token.
4. In GitHub open **Settings → Secrets and variables → Actions → New repository secret**.
5. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as separate secrets.

## Run
1. In GitHub **Settings → Actions → General**, ensure workflows are enabled and set Workflow permissions to **Read and write permissions** (needed to save history).
2. Open **Actions → Bangalore Job Alerts → Run workflow**.
3. The FIRST run scans boards and saves an initial baseline. It **does not notify for already-existing jobs**; later newly discovered matches are sent to Telegram. To receive existing matches for a clean start, edit `first_run` in `config.json` to `"alert"` before running the first time.
4. Monitor Actions logs and `data/seen.json` commits.
5. Scheduled checks occur at 7 and 37 minutes after each UTC hour, best effort.

## Configure job discovery
Edit `config.json` to set experience, locations, skills, and provider board slugs:
```json
"sources": {
  "greenhouse": ["cloudflare", "datadog"],
  "lever": ["postman"]
}
```
A Greenhouse board's slug is usually the value after `boards.greenhouse.io/` (or its associated public board URL). Lever boards usually use the company slug after `jobs.lever.co/`. Verify these public endpoints before adding each board. More boards = more coverage, but also more requests.

## Local testing (optional)
Python 3.10+; no dependencies required:
```bash
python -m unittest discover -s tests -v
python monitor.py --dry-run
```
Dry run does not send Telegram alerts or save state.

## Limitations and safety
- Only uses company public job posting APIs. Do not scrape portals in violation of their terms.
- Experience extraction uses approximate regular expressions; descriptions may be ambiguous.
- The monitor treats listings with no explicit experience requirement as potentially eligible.
- Stored state is committed to the public repository; it contains only job IDs.
- GitHub Actions schedules are not guaranteed real-time. Public repository scheduled workflows may be disabled after inactivity.
- Multiple jobs in a scan beyond `max_alerts_per_run` are not notified in that run.
- Telegram secrets must NEVER be placed in the repository or chat.

## Expanded coverage (v2)
The configuration now includes over 35 candidate Greenhouse/Lever company boards. **These are candidate slugs, not a verified list of active APIs:** some will return 404 or no Bangalore jobs, and the workflow logs will report those failures. Remove invalid boards after reviewing the logs. Board scans may take longer and can hit API limits; reduce the list if workflow timeouts occur. Role matching includes platform/infrastructure/system engineering roles and junior/associate language. The seen-ID history was retained. Existing job alerts still require a new detection event; rerunning does not resend historic listings.

No paid sources, scraping of protected job boards, or AI service is required. Company-board APIs still cannot guarantee coverage of every job on the internet.

## Source health and daily Telegram digest
- Every scan writes `data/health.json` with timestamp, board-by-board status (`ok`, `empty`, `failed`), number of postings, new matches and successfully delivered Telegram alerts.
- Diagnostic errors are deliberately sanitized (e.g. HTTP 404) to avoid dumping full URLs or tokens into logs.
- Scan history is kept for 14 days; old data expires on subsequent scans.
- At **03:15 UTC every day (08:45 India time)**, `Daily Job Monitor Report` sends a 24-hour Telegram summary. It can also be run manually from Actions.
- The report summarizes scan counts, total fetched postings (not unique vacancies), new matching jobs, sent alerts, and the last observed state of each board. It also lists the most frequently failing boards.
- `python -m unittest discover -s tests -v` runs before each scheduled scan and daily digest.
- Both `data/seen.json` and `data/health.json` are committed by the scan workflow; enable Actions **Read and write permissions**.
- The daily report is best-effort on GitHub Actions scheduling; a missing report can indicate scheduling delay, an Actions outage, or workflow failure.

## 100+ companies: Ashby batch expansion
The monitor now has **105 distinct configured company boards** (15 Greenhouse/Lever + 90 Ashby slugs from the [public ATS directory](https://github.com/moonie0201/ats-directory)). These 90 slugs had `status: ok` in the third-party directory when selected; this is *not* independent live verification that they still work or are hiring in Bangalore. Any failed boards will be reported in scan-health diagnostics.

To keep each run under free GitHub Actions limits, the 90 Ashby boards are split into **five batches of 18**, with one batch scanned per half-hour interval. The original 15 boards and four Himalayas queries run each interval. Across five consecutive normally scheduled scans (~2.5 hours), all 105 configured company boards are checked. A manual run may repeat the same half-hour batch.

Only title, experience, and explicit Bangalore/Bengaluru location determine match eligibility. Skills do not filter or rank results. Listings with unspecified experience remain eligible (the setting can be tightened via `allow_unspecified_experience`). The daily snapshot is **per most recent batch**, not a simultaneous snapshot of all 105 companies. This setup does not guarantee alerts for postings that disappear before their batch is checked.
