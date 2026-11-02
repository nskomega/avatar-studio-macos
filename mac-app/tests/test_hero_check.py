from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
from hero_check import assess
from phonetics import expand_spoken_terms


class HeroChecks(unittest.TestCase):
    def test_closed_mouth_is_rejected_despite_landmark_jitter(self):
        self.assertFalse(assess([.001,.002,.003]*24,72)['passed'])

    def test_motion_requires_face_coverage_and_variation(self):
        self.assertTrue(assess([.003,.06,.13]*24,72)['passed'])
        self.assertFalse(assess([.003,.06,.13],72)['passed'])
        self.assertFalse(assess([.1]*72,72)['passed'])
        self.assertFalse(assess([],72)['passed'])

    def test_product_reading_is_explicit_and_token_bounded(self):
        terms={'Битрикс24':'Би́трикс два́дцать четы́ре'}
        source='Сегодня Битрикс24, битрикс24! Битрикс240.'
        self.assertEqual(expand_spoken_terms(source,terms),
                         'Сегодня Би́трикс два́дцать четы́ре, Би́трикс два́дцать четы́ре! Битрикс240.')
        self.assertEqual(source,'Сегодня Битрикс24, битрикс24! Битрикс240.')


if __name__=='__main__':unittest.main()
