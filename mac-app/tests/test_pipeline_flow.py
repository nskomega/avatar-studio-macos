"""Orchestration tests with explicitly mocked ML workers; no claim of generated voice/face quality."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import pipeline
import scenario
import history
import drive_upload
ROOT=pipeline.ROOT
sys.path.insert(0,str(ROOT/'local-avatar/reels'))


class PipelineFlowTests(unittest.TestCase):
    def test_audio_delivery_and_upload_failure_keeps_result(self):
        plan=scenario.prepare('СЦЕНА 1 Озвучка: «Проверка сценария.»')
        real_check=pipeline.subprocess.check_output
        real_run=pipeline.run
        def check(args,**kwargs):
            if args[0]=='git':return 'TEST_FIXTURE_NOT_A_MODEL_RUN\n'
            return real_check(args,**kwargs)
        for fail_upload in [False,True]:
            with self.subTest(fail_upload=fail_upload),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);job=root/'mac-app/jobs/test';job.mkdir(parents=True)
                from PIL import Image
                Image.new('RGB',(64,64),'orange').save(root/'test-portrait.png')
                sf.write(root/'test-reference.wav',.1*np.sin(2*np.pi*220*np.arange(72000)/24000),24000)
                config=dict(photo=str(root/'test-portrait.png'),
                            reference_audio=str(root/'test-reference.wav'),
                            reference_text='Тестовая запись',script=plan['speech'],scenario_plan=plan,
                            title='TEST ONLY',voice_only=True)
                if fail_upload:config['upload_destination']='gdrive:AvatarStudio'
                (job/'project.json').write_text(json.dumps(config))
                def run(args,**kwargs):
                    if len(args)>1 and str(args[1]).endswith('/voice.py'):
                        # Test-only synthetic signal; this is NOT model inference or the user's cloned voice.
                        sr=24000;t=np.arange(sr//2)/sr
                        sf.write(job/'voice-000.wav',.1*np.sin(2*np.pi*220*t),sr)
                    else:real_run(args,**kwargs)
                with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'dependencies'),patch.object(pipeline,'run',side_effect=run),patch.object(pipeline.subprocess,'check_output',side_effect=check),patch.object(history,'record_job'),patch.object(drive_upload,'preflight',return_value='rclone'),patch.object(drive_upload,'upload',side_effect=RuntimeError('TEST network failure')):
                    if fail_upload:
                        with self.assertRaises(pipeline.UploadFailure):pipeline.main(job/'project.json')
                    else:pipeline.main(job/'project.json')
                state=json.loads((job/'status.json').read_text())
                self.assertEqual(state['stage'],'upload_error' if fail_upload else 'done')
                output=Path(state['output']);self.assertTrue(output.exists())
                self.assertTrue((output.parent/'report.json').exists())
                self.assertTrue((output.parent/'scenario.json').exists())
                self.assertFalse((output.parent/'reference.wav').exists())
                self.assertFalse((output.parent/'portrait.png').exists())
                timing=json.loads((job/'timing-check.json').read_text())
                self.assertLess(timing['duration'],1)  # not padded to a fixed requested scene slot
                self.assertEqual(timing['pauses'],[])


if __name__=='__main__':unittest.main()
