"""SQLite history tests; no personal media and no model inference."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import history


class HistoryTests(unittest.TestCase):
    def test_roundtrip_and_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            db = base/'history.sqlite3'
            prompt = dict(source='Озвучка: «Тест»; SQL \' " ; DROP TABLE prompts;', speech='Тест 🚀')
            history.save_prompt(prompt, db)
            history.save_prompt(prompt, db)
            self.assertEqual(len(history.listing(db_path=db)), 1)
            self.assertEqual(history.listing('тЕсТ', db)[0]['speech'], 'Тест 🚀')
            job = base/'job'; job.mkdir()
            config = dict(script='Привет', voice_only=True, source_prompt='Исходное задание', design={'accent':'#FF5C1F'})
            (job/'project.json').write_text(json.dumps(config))
            history.record_job(job, dict(stage='voice', message='В работе'), db)
            history.record_job(job, dict(stage='done', message='Готово', output=str(job/'speech.wav')), db)
            history.record_job(job, dict(stage='done', message='Готово', output=str(job/'speech.wav')), db)
            rows=history.listing('Готово', db)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['config'],config)
            self.assertEqual(rows[0]['source'],'Исходное задание')
            self.assertEqual(rows[0]['output'],str(job/'speech.wav'))
            self.assertFalse((job/'speech.wav').exists())  # index never claims media were created
            self.assertEqual(len(history.listing(db_path=db)),2)
            self.assertEqual(history.listing('нет такой строки',db),[])
            with history.connect(db) as connection:
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_import_is_idempotent_and_reports_bad_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); jobs=root/'mac-app/jobs'; jobs.mkdir(parents=True)
            good=jobs/'old'; good.mkdir(); (good/'project.json').write_text('{"script":"Старое"}')
            bad=jobs/'bad'; bad.mkdir(); (bad/'project.json').write_text('broken')
            (jobs/'script-source-old.txt').write_text('Озвучка: «Привет»')
            original=history.ROOT
            try:
                history.ROOT=root
                db=root/'history.sqlite3'
                self.assertEqual(len(history.sync(db)),1)
                history.sync(db)
                self.assertEqual(len(history.listing(db_path=db)),2)
                self.assertEqual(history.listing('Старое',db)[0]['stage'],'unknown')
            finally:
                history.ROOT=original

    def test_empty_prompt_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): history.save_prompt({},Path(folder)/'test.sqlite3')


if __name__ == '__main__':
    unittest.main()
