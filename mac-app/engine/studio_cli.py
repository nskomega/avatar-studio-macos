"""SSH-friendly studio commands; no GUI or connector session required."""
from pathlib import Path
import argparse
import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
ENGINE=Path(__file__).resolve().parent
PYTHON=ROOT/'local-avatar/.venv-lipsync/bin/python'
# SSH and Finder frequently omit Homebrew from PATH.
os.environ['PATH']='/opt/homebrew/bin:/usr/local/bin:'+os.environ.get('PATH','/usr/bin:/bin')
from scenario import prepare
import drive_upload


def read_scenario(args):
    if args.scenario is not None:return args.scenario
    if args.scenario_file:return Path(args.scenario_file).expanduser().read_text()
    return sys.stdin.read()


def avatar_config(folder):
    folder=Path(folder).expanduser().resolve()
    p=json.loads((folder/'avatar.json').read_text())
    if p.get('version')!=1:raise ValueError('Поддерживается профиль аватара version=1')
    def media(key):
        result=(folder/p[key]).resolve()
        if not result.is_file():raise ValueError('Не найден файл аватара: '+str(result))
        return str(result)
    if not p.get('text','').strip():raise ValueError('В профиле нет расшифровки голоса')
    return dict(photo=media('photo'),reference_audio=media('audio'),reference_text=p['text'],avatar_name=p.get('name',''))


def job_path(path):
    path=Path(path).expanduser().resolve()
    if path.name=='project.json':path=path.parent
    if path.parent!=(ROOT/'mac-app/jobs').resolve():raise ValueError('Задание должно находиться в mac-app/jobs/<id>')
    return path


def generate(args):
    plan=prepare(read_scenario(args),args.title)
    config=avatar_config(args.avatar)
    config.update(script=plan['speech'],source_prompt=plan['source'],scenario_plan=plan,title=plan['title'],
                  voice_only=args.voice_only,logo=str(Path(args.logo).expanduser().resolve()) if args.logo else '',
                  design=dict(theme='dark-tech',accent='#FF5C1F',headline=plan['title']))
    if args.upload is not None:
        config['upload_destination']=drive_upload.destination(args.upload or None)
        drive_upload.preflight(config['upload_destination'])
    # Input and dependency errors happen before the long-running worker is launched.
    import pipeline
    pipeline.validate(config);pipeline.dependencies(voice_only=args.voice_only)
    identity=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')+'-'+uuid.uuid4().hex[:6]
    job=ROOT/'mac-app/jobs'/identity;job.mkdir(parents=True)
    (job/'project.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    (job/'prepared-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    import history
    history.record_job(job,dict(stage='queued',message='Задание подготовлено'))
    with (job/'run.log').open('wb') as logfile:
        worker=subprocess.Popen([str(PYTHON),str(__file__),'run-job',str(job)],stdin=subprocess.DEVNULL,
                                stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True,cwd=ROOT)
    (job/'worker.json').write_text(json.dumps(dict(pid=worker.pid,created=datetime.now(timezone.utc).isoformat())))
    print(json.dumps(dict(job=str(job),pid=worker.pid,log=str(job/'run.log'),status=str(job/'status.json')),
                     ensure_ascii=False),flush=True)
    if args.detach:return 0
    def interrupt(signum,frame):
        if worker.poll() is None:os.kill(worker.pid,signal.SIGTERM)
    signal.signal(signal.SIGINT,interrupt);signal.signal(signal.SIGTERM,interrupt)
    code=worker.wait()
    if (job/'status.json').exists():print((job/'status.json').read_text())
    return code


def run_job(path):
    import pipeline
    job=job_path(path)
    try:pipeline.main(job/'project.json');return 0
    except pipeline.UploadFailure as exc:print(str(exc),file=sys.stderr);return 3
    except Exception as exc:print(str(exc),file=sys.stderr);return 1


def main():
    parser=argparse.ArgumentParser(description='Аватар Студия: подготовка сценария, генерация и Google Drive')
    sub=parser.add_subparsers(dest='command',required=True)
    def scenario_args(p):
        group=p.add_mutually_exclusive_group(required=True)
        group.add_argument('--scenario',help='Полный сценарий одной строкой или с переводами строк')
        group.add_argument('--scenario-file',help='UTF-8 файл полного сценария')
        group.add_argument('--scenario-stdin',action='store_true',help='Читать сценарий из stdin')
        p.add_argument('--title',default='',help='Название проекта и заголовок ролика')
    prep=sub.add_parser('prepare');scenario_args(prep)
    gen=sub.add_parser('generate');scenario_args(gen)
    gen.add_argument('--avatar',required=True,help='Папка с avatar.json')
    gen.add_argument('--logo');gen.add_argument('--voice-only',action='store_true')
    gen.add_argument('--upload',nargs='?',const='',help='Назначение rclone; без значения — настроенная папка gdrive:AvatarStudio')
    gen.add_argument('--detach',action='store_true',help='Вернуться сразу; worker продолжает работу после отключения SSH')
    setup=sub.add_parser('drive-setup');setup.add_argument('--destination',default=drive_upload.DEFAULT)
    run=sub.add_parser('run-job');run.add_argument('job')
    stat=sub.add_parser('status');stat.add_argument('job')
    retry=sub.add_parser('retry-upload');retry.add_argument('job');retry.add_argument('--destination')
    args=parser.parse_args()
    try:
        if args.command=='prepare':print(json.dumps(prepare(read_scenario(args),args.title),ensure_ascii=False,indent=2));return 0
        if args.command=='drive-setup':print(json.dumps(drive_upload.setup(args.destination),ensure_ascii=False));return 0
        if args.command=='generate':return generate(args)
        if args.command=='run-job':return run_job(args.job)
        if args.command=='status':
            job=job_path(args.job)
            print((job/'status.json').read_text() if (job/'status.json').exists() else '{"stage":"unknown","message":"Статус ещё не записан"}');return 0
        if args.command=='retry-upload':
            import pipeline
            job=job_path(args.job);config=json.loads((job/'project.json').read_text())
            folder=Path(json.loads((job/'delivery.json').read_text())['folder']).resolve()
            if folder.parent!=(ROOT/'videos/exports').resolve():raise ValueError('Недопустимая папка экспорта')
            target=args.destination or config.get('upload_destination') or drive_upload.destination()
            receipt=drive_upload.upload(folder,target,pipeline.run)
            (job/'upload.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
            result=json.loads((job/'delivery.json').read_text())['output']
            pipeline.status(job,'done','Загрузка завершена',output=result)
            print(json.dumps(receipt,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,RuntimeError,subprocess.SubprocessError) as exc:
        print('Ошибка: '+str(exc),file=sys.stderr);return 2


if __name__=='__main__':sys.exit(main())
