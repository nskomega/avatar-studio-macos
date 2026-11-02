"""Model input spelling hints; canonical script/subtitles remain unchanged."""
import re

WORDS = re.compile(r'[А-Яа-яЁё]+(?:\u0301[А-Яа-яЁё]*)*')


def expand_spoken_terms(text, terms):
    """Expand product names for TTS only, before dictionary stress annotation."""
    if not terms:return text
    lookup={key.casefold():value for key,value in terms.items()}
    pattern=re.compile(r'(?<!\w)(?:'+'|'.join(re.escape(key) for key in sorted(terms,key=len,reverse=True))+r')(?!\w)',re.IGNORECASE)
    return pattern.sub(lambda match:lookup[match[0].casefold()],text)


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
