"""Local SQLite prompt library and job index. Media remain in job folders."""
from pathlib import Path
import argparse
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / 'mac-app/data/studio.sqlite3'


@contextmanager
def connect(path=DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS prompts (
        id TEXT PRIMARY KEY, created TEXT NOT NULL, title TEXT NOT NULL,
        source TEXT NOT NULL, speech TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS generations (
        job TEXT PRIMARY KEY, created TEXT NOT NULL, config TEXT NOT NULL,
        stage TEXT NOT NULL, message TEXT NOT NULL, output TEXT
    );
    PRAGMA user_version=1;
    ''')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def record_job(job, state=None, db_path=DB):
    job = Path(job).resolve()
    config = json.loads((job / 'project.json').read_text())
    if state is None:
        state = json.loads((job / 'status.json').read_text()) if (job / 'status.json').exists() else {}
    created = datetime.fromtimestamp((job/'project.json').stat().st_mtime, timezone.utc).isoformat()
    with connect(db_path) as db:
        db.execute('''INSERT INTO generations VALUES (?,?,?,?,?,?)
          ON CONFLICT(job) DO UPDATE SET config=excluded.config, stage=excluded.stage,
          message=excluded.message, output=excluded.output''',
          (str(job), created, json.dumps(config, ensure_ascii=False), state.get('stage', 'unknown'),
           state.get('message', 'Нет сохранённого статуса'), state.get('output')))


def sync(db_path=DB):
    warnings = []
    for path in sorted((ROOT/'mac-app/jobs').glob('*/project.json')):
        if path.parent.name in {'smoke', 'lock-check', 'ui-preview'}:
            continue
        try:
            record_job(path.parent, db_path=db_path)
        except (ValueError, OSError) as exc:
            warnings.append(f'{path.parent.name}: {exc}')
    import re
    for path in sorted((ROOT/'mac-app/jobs').glob('script-source-*.txt')):
        try:
            source = path.read_text()
            speech = '\n'.join(re.findall(r'(?i)озвучка\s*:\s*«([^»]+)»', source))
            save_prompt(dict(title=path.stem, source=source, speech=speech or source), db_path)
        except (ValueError, OSError) as exc:
            warnings.append(f'{path.name}: {exc}')
    return warnings


def save_prompt(data, db_path=DB):
    import hashlib
    source = str(data.get('source', ''))
    speech = str(data.get('speech', ''))
    if not source.strip() and not speech.strip():
        raise ValueError('Пустой промпт не сохраняется')
    title = str(data.get('title') or (speech or source).splitlines()[0])[:120]
    with connect(db_path) as db:
        db.execute('INSERT OR IGNORE INTO prompts VALUES (?,?,?,?,?)',
                   (hashlib.sha256(json.dumps([source, speech], ensure_ascii=False).encode()).hexdigest(), datetime.now(timezone.utc).isoformat(), title, source, speech))


def listing(query='', db_path=DB):
    with connect(db_path) as db:
        prompts = [dict(r) for r in db.execute('SELECT * FROM prompts ORDER BY created DESC')]
        jobs = [dict(r) for r in db.execute('SELECT * FROM generations ORDER BY created DESC')]
    items = []
    for p in prompts:
        items.append(dict(kind='prompt', title=p['title'], created=p['created'],
                          source=p['source'], speech=p['speech'], stage='Промпт', output='', job=''))
    for j in jobs:
        c = json.loads(j['config'])
        items.append(dict(kind='generation', title=c.get('script', '').split('\n')[0][:100],
                          created=j['created'], source=c.get('source_prompt', c.get('script', '')),
                          speech=c.get('script', ''), stage=j['stage'], message=j['message'],
                          output=j['output'] or '', job=j['job'], config=c))
    items.sort(key=lambda x: x['created'], reverse=True)
    return [item for item in items if query.casefold() in json.dumps(item, ensure_ascii=False).casefold()]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['list', 'save', 'sync', 'record'])
    parser.add_argument('--query', default='')
    parser.add_argument('--job')
    args = parser.parse_args()
    if args.action == 'save':
        import sys
        save_prompt(json.load(sys.stdin))
    elif args.action == 'record':
        record_job(args.job)
    elif args.action == 'sync':
        print(json.dumps(dict(warnings=sync()), ensure_ascii=False))
    else:
        warnings = sync()
        print(json.dumps(dict(items=listing(args.query), warnings=warnings), ensure_ascii=False))
