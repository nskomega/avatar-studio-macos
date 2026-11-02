"""Policy tests; no model inference or claims about generated quality."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from hero_repair import failure_reasons, repair_prompt


class RepairPolicyTests(unittest.TestCase):
    def test_observed_failed_takes_get_different_repairs(self):
        first=dict(passed=False,face_coverage=1,mouth_passed=False,
                   head_motion=dict(face_width_ratio=1.64,max_yaw_proxy_step=.012,max_yaw_proxy_excursion=.017))
        second=dict(passed=False,face_coverage=1,mouth_passed=True,
                    head_motion=dict(face_width_ratio=2.53,max_yaw_proxy_step=.308,max_yaw_proxy_excursion=.448))
        self.assertEqual(failure_reasons(first),['mouth_motion','face_scale'])
        self.assertEqual(failure_reasons(second),['face_scale','head_turn'])
        cumulative=set(failure_reasons(first)+failure_reasons(second))
        prompt=repair_prompt('Original identity and speech.',cumulative)
        for text in ['Original identity and speech.', 'clearly articulate', 'fixed subject distance', 'no head turns']:
            self.assertIn(text,prompt)

    def test_unknown_failure_cannot_be_treated_as_success(self):
        self.assertEqual(failure_reasons(dict(passed=False,face_coverage=1,mouth_passed=True)),
                         ['incomplete_or_unmeasurable_clip'])
        self.assertIn('face_missing',failure_reasons({}))
        self.assertEqual(failure_reasons(dict(passed=True)),[])


if __name__=='__main__':unittest.main()
