import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from monitor import matches, years_required

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
    def test_years_parse(self):
        self.assertEqual(years_required("2-4 years experience"),[(2,4)])
if __name__=="__main__":
    unittest.main()
