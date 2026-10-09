import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from health import load_health, save_scan, summarize, failure_reason

NOW=datetime(2026,10,9,12,tzinfo=timezone.utc)
class HealthTests(unittest.TestCase):
    def test_record_and_preserve(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"health.json"
            old={"at":(NOW-timedelta(days=16)).isoformat(),"boards":[]}
            new={"at":NOW.isoformat(),"boards":[{"source":"greenhouse/x","status":"empty","postings":0}],"postings":0,"new_matches":0,"alerts_sent":0}
            save_scan(old,path,now=NOW-timedelta(days=16))
            save_scan(new,path,now=NOW)
            self.assertEqual(load_health(path)["scans"],[new])
    def test_daily_summary(self):
        scans=[{"at":NOW.isoformat(),"boards":[{"source":"lever/a","status":"failed","postings":0},{"source":"lever/b","status":"ok","postings":4}],"postings":4,"new_matches":2,"alerts_sent":1}]
        msg=summarize({"scans":scans},now=NOW)
        self.assertIn("Alerts sent: 1",msg)
        self.assertIn("lever/a (1)",msg)
    def test_no_recent_scans(self):
        self.assertIn("No scan history",summarize({"scans":[]},now=NOW))
    def test_http_error_redacted(self):
        from urllib.error import HTTPError
        err=HTTPError("https://example.invalid/secret",404,"Not Found",{},None)
        self.assertEqual(failure_reason(err),"HTTP 404")
