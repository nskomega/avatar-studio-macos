from pathlib import Path
import argparse
import gzip
import hashlib
import json
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'local-avatar/models/russian-stress'
OVERRIDES = Path(__file__).with_name('pronunciation-overrides.json')
REVISION = 'b78ae5ea1e62beaf138bed1865cd8c3b0b5ca855'
FILES = {
    'accents.json.gz': 'aa460ebba90de00fbbf3d41d121961f605b98667e45efb7920f127473b15515e',
    'omographs.json.gz': '04a9e81c68d65f65ba493fe0110f99e79087548c2beeec3032e2b66e28706f36',
}
TOKEN = re.compile(r'[А-Яа-яЁё]+(?:\u0301[А-Яа-яЁё]*)*')
VOWELS = 'аеёиоуыэюя'


def install():
    import urllib.request
    DATA.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        path = DATA / name
        if not path.exists():
            url = f'https://huggingface.co/ruaccent/accentuator/resolve/{REVISION}/dictionary/{name}'
            temporary = path.with_suffix('.download')
            urllib.request.urlretrieve(url, temporary)
            temporary.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Dictionary checksum mismatch: ' + name)
    target = DATA / 'stress.sqlite3'
    temporary = DATA / 'stress-building.sqlite3'
    with sqlite3.connect(temporary) as connection:
        connection.execute('DROP TABLE IF EXISTS words')
        connection.execute('CREATE TABLE words (word TEXT PRIMARY KEY, variants TEXT NOT NULL) WITHOUT ROWID')
        with gzip.open(DATA / 'accents.json.gz', 'rt', encoding='utf-8') as handle:
            entries = json.load(handle)
        count = len(entries)
        connection.executemany('INSERT INTO words VALUES (?, ?)',
                               ((key, json.dumps([value], ensure_ascii=False)) for key, value in entries.items()))
        del entries
        with gzip.open(DATA / 'omographs.json.gz', 'rt', encoding='utf-8') as handle:
            homographs = json.load(handle)
        connection.executemany('INSERT OR REPLACE INTO words VALUES (?, ?)',
                               ((key, json.dumps(value, ensure_ascii=False)) for key, value in homographs.items()))
        actual = connection.execute('SELECT COUNT(*) FROM words').fetchone()[0]
    temporary.replace(target)
    manifest = dict(source='https://huggingface.co/ruaccent/accentuator', revision=REVISION,
                    upstream_license='MIT (repository metadata)', sha256=FILES,
                    base_entries=count, homographs=len(homographs), indexed_forms=actual)
    (DATA / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def acute(value):
    return re.sub(r'\+([аеёиоуыэюя])', lambda match: match[1] + '\u0301', value)


def copy_case(value, original):
    if original.isupper():
        return value.upper()
    if original[0].isupper():
        return value[0].upper() + value[1:]
    return value


class Lexicon:
    def __init__(self, database=None, overrides=None):
        self.database = Path(database) if database is not None else DATA / 'stress.sqlite3'
        self.connection = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True) if self.database.exists() else None
        self.overrides = json.loads(OVERRIDES.read_text())['words'] if overrides is None else overrides

    def close(self):
        if self.connection is not None:
            self.connection.close()

    def lookup(self, word):
        key = word.lower().replace('\u0301', '')
        if key in self.overrides:
            return [copy_case(self.overrides[key], word)], 'project'
        if self.connection is None:
            return [], 'dictionary_missing'
        row = self.connection.execute('SELECT variants FROM words WHERE word = ?', (key,)).fetchone()
        if row is None:
            return [], 'unknown'
        return [copy_case(acute(value), word) for value in json.loads(row[0])], 'dictionary'

    def annotate(self, text):
        issues = []
        def replace(match):
            word = match[0]
            if '\u0301' in word or sum(letter.lower() in VOWELS for letter in word) <= 1:
                return word
            candidates, source = self.lookup(word)
            if len(candidates) == 1:
                return candidates[0]
            issues.append(dict(word=word, start=match.start(), end=match.end(),
                               status='ambiguous' if candidates else source, candidates=candidates))
            return word
        marked = TOKEN.sub(replace, text)
        return dict(original=text, marked=marked, issues=issues,
                    dictionary_available=self.connection is not None)


def for_tts(marked, mode):
    if mode == 'acute':
        return marked
    if mode == 'capital':
        return re.sub(r'([А-Яа-яЁё])\u0301', lambda match: match[1].upper(), marked)
    raise ValueError('Unsupported pronunciation mode: ' + mode)


def targeted_tts(text):
    overrides = json.loads(OVERRIDES.read_text())['words']
    def replace(match):
        word = match[0]
        value = overrides.get(word.lower())
        return for_tts(copy_case(value, word), 'capital') if value else word
    return TOKEN.sub(replace, text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--text')
    arguments = parser.parse_args()
    if arguments.install:
        install()
    if arguments.text:
        lexicon = Lexicon()
        try:
            print(json.dumps(lexicon.annotate(arguments.text), ensure_ascii=False, indent=2))
        finally:
            lexicon.close()
