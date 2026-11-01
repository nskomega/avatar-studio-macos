"""Unattended uploads through an already authorized rclone Google Drive remote."""
from pathlib import Path
import json
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
SETTINGS=ROOT/'mac-app/data/integrations.json'
DEFAULT='gdrive:AvatarStudio'


def destination(value=None):
    if value: return value
    if SETTINGS.exists(): return json.loads(SETTINGS.read_text()).get('drive_destination',DEFAULT)
    return DEFAULT


def preflight(target):
    binary=shutil.which('rclone')
    if not binary: raise ValueError('Не установлен rclone. Выполните brew install rclone, затем rclone config и studio drive-setup.')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_-]*:[^\x00-\x1f]*',target) or '..' in target.split(':',1)[1].split('/'):
        raise ValueError('Назначение должно быть вида gdrive:AvatarStudio, без переходов ..')
    names=subprocess.check_output([binary,'listremotes'],text=True,timeout=20).splitlines()
    if target.split(':',1)[0]+':' not in names:
        raise ValueError('Подключение rclone не настроено. Запустите rclone config и создайте remote gdrive (Google Drive).')
    return binary


def setup(target=DEFAULT):
    preflight(target)
    SETTINGS.parent.mkdir(parents=True,exist_ok=True)
    settings=json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    settings['drive_destination']=target
    SETTINGS.write_text(json.dumps(settings,ensure_ascii=False,indent=2))
    SETTINGS.chmod(0o600)
    return dict(destination=target, message='Назначение сохранено. OAuth хранится в конфигурации rclone, не в базе студии.')


def upload(folder,target,run):
    binary=preflight(target)
    remote=target.rstrip('/')+'/'+folder.name
    # Copy only the dedicated delivery folder. Never copy jobs, portrait, reference voice or database.
    run([binary,'copy',str(folder),remote,'--immutable','--retries','3',
         '--low-level-retries','5','--stats','0','--log-level','ERROR'],start_new_session=True)
    return dict(destination=remote, files=sorted(p.name for p in folder.iterdir() if p.is_file()))
