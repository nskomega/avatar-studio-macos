# -*- coding: utf-8 -*-
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import batch
import pipeline


class BatchTests(unittest.TestCase):
    def test_import_json_csv_txt_and_all_or_nothing_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'a.json').write_text(json.dumps([dict(title='First',script='Первая реплика.')]))
            (root/'b.csv').write_text('title,script\nSecond,Вторая реплика.\n')
            (root/'c.txt').write_text('Третья реплика.')
            items=batch.load_items([root/'a.json',root/'b.csv',root/'c.txt'])
            self.assertEqual(len(items),3)
            self.assertEqual(items[1]['plan']['speech'],'Вторая реплика.')
            (root/'bad.json').write_text('[{"title":"Empty"}]')
            with self.assertRaises(ValueError):batch.load_items([root/'a.json',root/'bad.json'])

    def test_reject_empty_and_oversized_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.json'
            for data in [[], ['Тест.']*101]:
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):batch.load_items([path])

    def test_photo_selection_snapshot_and_reject_corrupt(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); photos=root/'photos';photos.mkdir()
            (photos/'broken.png').write_bytes(b'invalid')
            with self.assertRaises(ValueError):batch.photo_pool(photos)
            Image.new('RGB',(64,64),'orange').save(photos/'good.png')
            items=[dict(title='One',source='Тест.',plan=batch.prepare('Тест.'))]
            with patch.object(batch,'ROOT',root),patch.object(pipeline,'validate'),patch.object(pipeline,'dependencies'),patch('history.record_job'):
                queue=batch.create_queue(items,dict(reference_audio='fixture.wav'),photos)
            manifest=json.loads((queue/'batch.json').read_text())
            job=Path(manifest['jobs'][0]); config=json.loads((job/'project.json').read_text())
            self.assertEqual(Path(config['photo_original']).name,'good.png')
            (photos/'good.png').unlink()
            self.assertTrue(Path(config['photo']).is_file())
            with patch.object(batch,'ROOT',root),self.assertRaises(ValueError):
                batch.create_queue(items,{},directory=queue)

    def test_resume_skips_completed_and_pauses_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); queue=root/'mac-app/jobs/batch-test';queue.mkdir(parents=True)
            jobs=[]
            for i in range(2):
                job=queue.parent/f'batch-test-{i:03}';job.mkdir();jobs.append(str(job))
                (job/'status.json').write_text(json.dumps(dict(stage='done' if i==0 else 'error',message='fixture error')))
            (queue/'batch.json').write_text(json.dumps(dict(jobs=jobs)))
            class Failed:
                pid=999999
                def wait(self):return 1
            with patch.object(batch,'ROOT',root),patch.object(batch.subprocess,'Popen',return_value=Failed()) as launch:
                self.assertEqual(batch.run_queue(queue),1)
                self.assertEqual(launch.call_count,1)
                self.assertIn(jobs[1],launch.call_args.args[0][-1])
            self.assertEqual(json.loads((queue/'status.json').read_text())['stage'],'error')


    def test_upload_error_resume_does_not_repeat_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); queue=(root/'mac-app/jobs/batch-upload').resolve();queue.mkdir(parents=True)
            job=queue.parent/'batch-upload-001';job.mkdir()
            (job/'status.json').write_text(json.dumps(dict(stage='upload_error',message='network')))
            (queue/'batch.json').write_text(json.dumps(dict(jobs=[str(job)])))
            class Uploaded:
                def wait(self):
                    (job/'status.json').write_text(json.dumps(dict(stage='done',output='fixture-output')))
                    return 0
            with patch.object(batch,'ROOT',root),patch.object(batch.subprocess,'Popen',return_value=Uploaded()) as launch:
                self.assertEqual(batch.run_queue(queue),0)
            command=launch.call_args.args[0]
            self.assertTrue(command[2].endswith('studio_cli.py'))
            self.assertEqual(command[3],'retry-upload')


if __name__=='__main__':unittest.main()
