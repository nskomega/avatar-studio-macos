import json
import argparse
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import scenario
import drive_upload
import studio_cli

ROOT=Path(__file__).resolve().parents[2]

class ScenarioTests(unittest.TestCase):
    def test_real_user_brief(self):
        source=(Path(__file__).parent/'fixtures/structured-scenario.txt').read_text()
        plan=scenario.prepare(source,'SMS 2FA')
        self.assertEqual(len(plan['scenes']),5)
        self.assertEqual([s['kind'] for s in plan['scenes']],['hero','graphic','graphic','graphic','hero'])
        self.assertEqual(plan['scenes'][2]['style'],'diagram')
        self.assertEqual(plan['scenes'][1]['style'],'comparison')
        self.assertEqual(plan['scenes'][0]['headline'],'SMS-КОД — НЕ БРОНЯ')
        self.assertNotIn('ВИЗУАЛ',plan['speech'])
        self.assertNotIn('Покажи',plan['speech'])
        self.assertEqual(plan['requested_duration'],[35,40])
        self.assertEqual(len(scenario.validate_plan(plan,plan['speech'])),6)
        captions=[dict(start=i*1.1,end=i*1.1+1,text=u['text']) for i,u in enumerate(plan['utterances'])]
        timeline=scenario.actual_timeline(plan,captions,6.6)
        self.assertEqual(timeline[-1]['end'],6.6)
        self.assertEqual(timeline[0]['end'],1.1)  # no fixed 3-second opening
        self.assertTrue(all(a['end']==b['start'] for a,b in zip(timeline,timeline[1:])))
        plan['utterances'][0]['text']='Подмена'
        with self.assertRaises(ValueError):scenario.validate_plan(plan,plan['speech'])

    def test_quotes_rejections_and_plain_speech(self):
        plan=scenario.prepare('СЦЕНА 1\nОзвучка: “Раз.”\nСЦЕНА 2\nОзвучка: "Два."')
        self.assertEqual(plan['speech'],'Раз.\nДва.')
        for source in ['', 'СЦЕНА 1\nБез реплик', 'СЦЕНА 2 Озвучка: «А»', 'я'*1501,
                       'Озвучка: «'+'я'*351+'»', 'Создай видео со схемами']:
            with self.subTest(source=source[:30]),self.assertRaises(ValueError):scenario.prepare(source)
        self.assertEqual(scenario.prepare('Привет. Вторая реплика!')['speech'],'Привет.\nВторая реплика!')

    def test_upload_allowlisted_delivery_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'delivery';folder.mkdir();(folder/'video.mp4').write_bytes(b'test')
            commands=[]
            with patch.object(drive_upload,'preflight',return_value='/bin/rclone'):
                receipt=drive_upload.upload(folder,'gdrive:AvatarStudio',lambda args,**kw:commands.append(args))
                self.assertEqual(receipt['destination'],'gdrive:AvatarStudio/delivery')
                self.assertEqual(commands[0][1],'copy')
                self.assertIn('--immutable',commands[0])
                self.assertNotIn('sync',commands[0])
                def fail(*a,**kw):raise RuntimeError('network down')
                with self.assertRaises(RuntimeError):drive_upload.upload(folder,'gdrive:AvatarStudio',fail)
            with patch.object(drive_upload.shutil,'which',return_value='/bin/rclone'),patch.object(drive_upload.subprocess,'check_output',return_value='gdrive:\n'):
                drive_upload.preflight('gdrive:AvatarStudio')
                with self.assertRaises(ValueError):drive_upload.preflight('missing:folder')
                with self.assertRaises(ValueError):drive_upload.preflight('gdrive:../bad')

    def test_detach_worker_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            args=argparse.Namespace(scenario='СЦЕНА 1 Озвучка: «Проверка.»',scenario_file=None,scenario_stdin=False,
                                    title='Тест',avatar='fixture',voice_only=True,logo=None,upload=None,detach=True)
            worker=Mock(pid=424242)
            with patch.object(studio_cli,'ROOT',Path(directory)),patch.object(studio_cli,'avatar_config',return_value={}),patch('pipeline.validate'),patch('pipeline.dependencies'),patch('history.record_job'),patch.object(studio_cli.subprocess,'Popen',return_value=worker) as launch,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(studio_cli.generate(args),0)
                kwargs=launch.call_args.kwargs
                self.assertTrue(kwargs['start_new_session'])
                self.assertEqual(kwargs['stdin'],studio_cli.subprocess.DEVNULL)
                worker.wait.assert_not_called()
                configs=list(Path(directory).glob('mac-app/jobs/*/project.json'))
                self.assertEqual(len(configs),1)
                config=json.loads(configs[0].read_text())
                self.assertEqual(config['source_prompt'],args.scenario)
                self.assertEqual(config['script'],'Проверка.')

    def test_avatar_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'photo.png').write_bytes(b'fixture');(folder/'voice.wav').write_bytes(b'fixture')
            (folder/'avatar.json').write_text(json.dumps(dict(version=1,name='Test',photo='photo.png',audio='voice.wav',text='Тест')))
            actual=studio_cli.avatar_config(folder)
            self.assertTrue(Path(actual['photo']).is_file())
            self.assertTrue(Path(actual['reference_audio']).is_file())
            self.assertTrue(actual['reference_text'])
        with self.assertRaises(ValueError):studio_cli.job_path('/tmp/somewhere')

if __name__=='__main__':unittest.main()
