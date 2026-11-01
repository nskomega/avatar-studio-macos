"""Model input spelling hints; canonical script/subtitles remain unchanged."""
import re

WORDS = re.compile(r'[А-Яа-яЁё]+(?:\u0301[А-Яа-яЁё]*)*')


def apply_spelling_hints(text, hints):
    def replace(match):
        original=match[0]
        plain=original.replace('\u0301','').lower()
        replacement=hints.get(plain)
        if replacement is None:
            return original
        if len(replacement)!=len(plain):
            raise ValueError('Spelling hint must preserve letter count to retain explicit stress')
        letters=iter(replacement)
        return ''.join(ch if ch=='\u0301' else (next(letters).upper() if ch.isupper() else next(letters)) for ch in original)
    return WORDS.sub(replace,text)
