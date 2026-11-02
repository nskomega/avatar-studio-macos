"""Synthetic timing checks; no voice quality claims."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'local-avatar/reels'))
from timing import pauses, shorten_long_pauses, build_timeline


class PauseRepairTests(unittest.TestCase):
    def test_preserves_speech_and_short_pauses(self):
        sr=24000
        speech=.1*np.sin(2*np.pi*220*np.arange(sr)/sr)
        short=np.zeros(round(.3*sr))
        source=np.concatenate([speech,short,speech,np.zeros(sr),speech])
        repaired,edits=shorten_long_pauses(source,sr)
        self.assertEqual(len(edits),1)
        self.assertEqual(len(source)-len(repaired),round(.65*sr))
        np.testing.assert_array_equal(repaired[:2*sr+len(short)],source[:2*sr+len(short)])
        np.testing.assert_array_equal(repaired[-sr:],speech)
        self.assertEqual(pauses(repaired,sr,min_duration=.85),[])
        waveform,_,_=build_timeline([repaired,speech],sr)
        self.assertEqual(pauses(waveform,sr,min_duration=.85),[])

    def test_no_change_when_audit_passes(self):
        source=np.ones(24000)*.1
        repaired,edits=shorten_long_pauses(source,24000)
        self.assertIs(repaired,source)
        self.assertEqual(edits,[])


if __name__=='__main__':unittest.main()
