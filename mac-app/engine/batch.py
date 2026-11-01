# -*- coding: utf-8 -*-
"""Validated sequential queues. Inputs are data, never executable instructions."""
from pathlib import Path
import argparse
import csv
import json
import os
import random
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from scenario import prepare

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.bmp'}


def load_items(paths):
    rows = []
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.stat().st_size > 5_000_000:
            raise ValueError('Input file exceeds 5 MB')
        suffix = path.suffix.lower()
        if suffix == '.json':
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
            items = payload.get('items') if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                raise ValueError('JSON must contain a list or {"items": [...]}')
        elif suffix == '.csv':
            with path.open(encoding='utf-8-sig', newline='') as handle:
                sample = handle.read(4096); handle.seek(0)
                try: dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
                except csv.Error: dialect = csv.excel
                items = list(csv.DictReader(handle, dialect=dialect))
        elif suffix == '.txt':
            items = [dict(title=path.stem, source=path.read_text(encoding='utf-8-sig'))]
        else:
            raise ValueError('Supported scenario files: JSON, CSV, TXT')
        for row in items:
            if isinstance(row, str): row = dict(source=row)
            if not isinstance(row, dict): raise ValueError('Scenario must be text or an object')
            source = row.get('source') or row.get('script') or row.get('speech') or row.get('Сценарий')
            title = row.get('title') or row.get('Название') or ''
            if not isinstance(source, str) or not isinstance(title, str):
                raise ValueError('Scenario source and title must be strings')
            plan = prepare(source, title)
            rows.append(dict(title=plan['title'], source=source, plan=plan))
            if len(rows) > 100: raise ValueError('Maximum 100 scenarios per queue')
    if not rows: raise ValueError('No scenarios in selected files')
    return rows


def photo_pool(folder):
    from PIL import Image
    path = Path(folder).expanduser().resolve()
    if not path.is_dir(): raise ValueError('Photo folder does not exist')
    candidates = []
    for file in sorted(path.iterdir()):
        if file.name.startswith('.') or file.suffix.lower() not in EXTENSIONS or not file.is_file(): continue
        try:
            with Image.open(file) as im: im.verify()
        except Exception: continue
        candidates.append(file.resolve())
    if not candidates: raise ValueError('No readable photos in folder')
    return candidates


def create_queue(items, base, folder=None, directory=None):
    import pipeline
    pool = photo_pool(folder) if folder else None
    configs = []
    for row in items:
        config = dict(base, title=row['title'], source_prompt=row['source'], script=row['plan']['speech'], scenario_plan=row['plan'])
        config['design'] = dict(base.get('design', {}), headline=row['title'])
        if pool: config['photo'] = str(random.SystemRandom().choice(pool))
        if config.get('upload_destination'):
            from drive_upload import preflight
            preflight(config['upload_destination'])
        pipeline.validate(config)
        configs.append(config)
    pipeline.dependencies(voice_only=base.get('voice_only', False))
    identity = 'batch-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    batch = (Path(directory) if directory else ROOT/'mac-app/jobs'/identity).resolve()
    if batch.parent != (ROOT/'mac-app/jobs').resolve(): raise ValueError('Invalid queue location')
    identity = batch.name
    if (batch/'batch.json').exists(): raise ValueError('Queue already exists; use run to resume')
    batch.mkdir(parents=True, exist_ok=True)
    jobs = []
    for index, config in enumerate(configs):
        job = batch.parent/f'{identity}-{index+1:03}'
        job.mkdir()
        # Snapshot the randomly selected photo now; a restarted queue uses the same asset.
        from PIL import Image, ImageOps
        with Image.open(config['photo']) as image:
            ImageOps.exif_transpose(image).convert('RGB').save(job/'selected-photo.png')
        config['photo_original'] = config['photo']
        config['photo'] = str(job/'selected-photo.png')
        (job/'project.json').write_text(json.dumps(config, ensure_ascii=False, indent=2))
        (job/'status.json').write_text(json.dumps(dict(stage='queued', message='Queued'), ensure_ascii=False))
        import history
        history.record_job(job, dict(stage='queued', message='Queued'))
        jobs.append(str(job))
    manifest = dict(version=1, id=identity, jobs=jobs, photo_folder=str(Path(folder).resolve()) if folder else None)
    (batch/'batch.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return batch


def run_queue(directory):
    batch = Path(directory).resolve()
    if batch.parent != (ROOT/'mac-app/jobs').resolve(): raise ValueError('Invalid queue location')
    manifest = json.loads((batch/'batch.json').read_text())
    # Lock queue in addition to the per-generation GPU lock; never race two resumes.
    import fcntl
    lock = (batch/'queue.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise ValueError('Queue is already running')
    child = None
    def state(stage, message, **extra):
        target = batch/'status.tmp'
        target.write_text(json.dumps(dict(stage=stage, message=message, **extra), ensure_ascii=False, indent=2))
        target.replace(batch/'status.json')
    def stop(signum, frame):
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
        state('cancelled', 'Queue stopped; remaining jobs preserved')
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    last_output = None
    try:
        for index, raw in enumerate(manifest['jobs']):
            job = Path(raw).resolve()
            if job.parent != batch.parent or not job.name.startswith(batch.name+'-'):
                raise ValueError('Invalid job location')
            saved = json.loads((job/'status.json').read_text()) if (job/'status.json').exists() else {}
            if saved.get('stage') == 'done':
                last_output = saved.get('output', last_output); continue
            state('running', f'{index+1}/{len(manifest["jobs"])}: {job.name}', current_job=str(job))
            with (job/'run.log').open('ab') as handle:
                command = [sys.executable, '-u', str(Path(__file__).with_name('studio_cli.py')), 'retry-upload', str(job)] if saved.get('stage') == 'upload_error' else [sys.executable, '-u', str(Path(__file__).with_name('pipeline.py')), str(job/'project.json')]
                child = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                code = child.wait()
            saved = json.loads((job/'status.json').read_text()) if (job/'status.json').exists() else {}
            if code or saved.get('stage') != 'done':
                state('error', f'Queue paused at {index+1}: '+saved.get('message', f'exit {code}'), current_job=str(job))
                return code or 1
            last_output = saved.get('output', last_output)
        state('done', f'Queue complete: {len(manifest["jobs"])}', output=last_output or '')
        return 0
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    preview = commands.add_parser('inspect'); preview.add_argument('files', nargs='+')
    run = commands.add_parser('run'); run.add_argument('queue')
    start = commands.add_parser('start'); start.add_argument('--controller', required=True); start.add_argument('--base', required=True); start.add_argument('--items', required=True); start.add_argument('--photos')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            print(json.dumps(dict(items=load_items(args.files)), ensure_ascii=False)); return 0
        if args.command == 'start':
            rows = json.loads(Path(args.items).read_text())
            # Revalidate imported data immediately before queue creation.
            items = [dict(source=r['source'], title=r['title'], plan=prepare(r['source'], r['title'])) for r in rows]
            queue = create_queue(items, json.loads(Path(args.base).read_text()), args.photos, args.controller)
            return run_queue(queue)
        return run_queue(args.queue)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        if args.command == 'start':
            (Path(args.controller)/'status.json').write_text(json.dumps(dict(stage='error', message=str(exc)), ensure_ascii=False))
        print(str(exc), file=sys.stderr); return 2


if __name__ == '__main__': sys.exit(main())
