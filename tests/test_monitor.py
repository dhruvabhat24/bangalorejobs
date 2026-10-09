import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from monitor import matches, years_required, himalayas, ashby, select_boards
from unittest.mock import patch

CFG={"experience_min":1,"experience_max":2,"locations":["bangalore","bengaluru"],"skills":["Docker","Git","Linux","Terraform"],"minimum_skill_matches":0,"allow_unspecified_experience":True}
def job(title="DevOps Engineer", location="Bengaluru", description="1-2 years experience in Docker and Linux"):
    return {"title":title,"location":location,"description":description}
class MatchingTests(unittest.TestCase):
    def test_good_match(self):
        self.assertIsNotNone(matches(job(),CFG))
    def test_not_bangalore(self):
        self.assertIsNone(matches(job(location="Pune"),CFG))
    def test_senior_role(self):
        self.assertIsNone(matches(job(title="Senior DevOps Engineer"),CFG))
    def test_wrong_role(self):
        self.assertIsNone(matches(job(title="Finance Analyst"),CFG))
    def test_experience_too_high(self):
        self.assertIsNone(matches(job(description="5+ years experience"),CFG))
    def test_overlapping_range(self):
        self.assertIsNotNone(matches(job(description="1-3 years experience"),CFG))
    def test_platform_engineer(self):
        self.assertIsNotNone(matches(job(title="Junior Platform Engineer"),CFG))
    def test_himalayas_parsing_and_strict_location(self):
        response={"jobs":[{"guid":"x1","title":"Cloud Engineer","companyName":"Demo","locationRestrictions":["India"],"description":"2 years","applicationLink":"https://himalayas.app/jobs/demo"}]}
        with patch("monitor.fetch_json", return_value=response):
            jobs=list(himalayas("cloud engineer"))
        self.assertEqual(len(jobs),1)
        self.assertIsNone(matches(jobs[0],CFG))
    def test_ashby_locations_and_listed(self):
        response={"jobs":[{"id":"abc","isListed":True,"title":"DevOps Engineer","location":"Remote","secondaryLocations":[{"location":"Bengaluru"}],"descriptionPlain":"1-2 years","jobUrl":"https://jobs.ashbyhq.com/demo/abc"},{"id":"hidden","isListed":False,"title":"Cloud Engineer"}]}
        with patch("monitor.fetch_json", return_value=response):
            found=list(ashby("demo"))
        self.assertEqual(len(found),1)
        self.assertIsNotNone(matches(found[0],CFG))
    def test_batches_cover_every_board(self):
        from datetime import datetime, timezone, timedelta
        boards=[str(x) for x in range(90)]
        cfg={"ashby_batch_size":18}
        base=datetime(2026,10,9,0,0,tzinfo=timezone.utc)
        batches=[select_boards("ashby",boards,cfg,base+timedelta(minutes=30*i)) for i in range(5)]
        self.assertEqual(set().union(*map(set,batches)),set(boards))
    def test_skills_not_required(self):
        cfg=dict(CFG,skills=["ImpossibleSkill"],minimum_skill_matches=999)
        self.assertIsNotNone(matches(job(),cfg))
    def test_years_parse(self):
        self.assertEqual(years_required("2-4 years experience"),[(2,4)])
if __name__=="__main__":
    unittest.main()
