"""Deterministic preparation of Russian scene briefs. Never invents spoken facts."""
import json
import re
import sys

QUOTE = r'(?:«([^»]+)»|“([^”]+)”|"([^"]+)")'
VOICE = re.compile(r'озвучка\s*:\s*'+QUOTE, re.I)
LABEL = re.compile(r'(?:финальная\s+надпись|текст\s+на\s+экране|надпись|текст)\s*:\s*'+QUOTE, re.I)
HEAD = re.compile(r'^\s*СЦЕНА\s+(\d+)\b[^\n]*', re.I | re.M)
SPLIT = re.compile(r'(?<=[.!?])\s+|\n+')


def quoted(match):
    return next(v for v in match.groups() if v is not None).strip()


def prepare(source, title=''):
    source = source.strip()
    if not source or len(source) > 50000:
        raise ValueError('Вставьте сценарий от 1 до 50 000 символов.')
    headings = list(HEAD.finditer(source))
    scenes = []
    warnings = []
    # Heading and content may occupy a single line. Split at heading START, not its end.
    if headings:
        numbers = [int(h.group(1)) for h in headings]
        if numbers != list(range(1, len(numbers)+1)):
            raise ValueError('Номера сцен должны идти подряд, начиная с 1.')
        for index, head in enumerate(headings):
            body = source[head.start():headings[index+1].start() if index+1 < len(headings) else len(source)]
            lines = [quoted(m) for m in VOICE.finditer(body)]
            if not lines:
                raise ValueError(f'Сцена {index+1}: нужна реплика Озвучка: «…».')
            labels = [quoted(m) for m in LABEL.finditer(body)]
            if any(len(label)>160 for label in labels):raise ValueError(f'Сцена {index+1}: сократите экранную надпись до 160 символов.')
            directions = VOICE.sub('', body)
            directions = LABEL.sub('', directions)
            hero = index in (0, len(headings)-1) or bool(re.search(r'геро[йя]|верни.+кадр', directions, re.I))
            style = ('comparison' if re.search(r'контраст|сравнен|ошибочн', directions, re.I)
                     else 'diagram' if re.search(r'схем', directions, re.I)
                     else 'checklist' if re.search(r'чек.?лист', directions, re.I) else 'statement')
            scenes.append(dict(id=index+1, kind='hero' if hero else 'graphic', style=style,
                               speech='\n'.join(lines), headline=labels[0] if labels else '',
                               labels=labels, directions=directions.strip()))
    elif VOICE.search(source):
        lines = [quoted(m) for m in VOICE.finditer(source)]
        scenes = [dict(id=i+1, kind='hero' if i in (0,len(lines)-1) else 'graphic',
                       style='statement', speech=line, headline='', labels=[], directions='') for i,line in enumerate(lines)]
        warnings.append('Сцены без номеров: порядок взят по репликам «Озвучка».')
    else:
        if re.search(r'сцена\s*\d|создай.+видео|главный\s+герой|визуал\s*:', source, re.I | re.S):
            raise ValueError('Не найдены реплики. Используйте строки СЦЕНА 1 … Озвучка: «…».')
        lines = [s.strip() for s in SPLIT.split(source) if s.strip()]
        scenes = [dict(id=i+1, kind='hero' if i in (0,len(lines)-1) else 'graphic',
                       style='statement', speech=line, headline='', labels=[], directions='') for i,line in enumerate(lines)]
        warnings.append('Вставлена только речь: созданы планы героя и текстовые графические сцены.')
    utterances = []
    for scene in scenes:
        scene['utterance_ids'] = []
        for line in SPLIT.split(scene['speech']):
            if not line.strip(): continue
            if len(line.strip()) > 350:
                raise ValueError(f'Сцена {scene["id"]}: реплика длиннее 350 символов. Разделите её предложениями.')
            scene['utterance_ids'].append(len(utterances))
            utterances.append(dict(scene_id=scene['id'], text=line.strip()))
    speech = '\n'.join(u['text'] for u in utterances)
    if not 1 <= len(speech) <= 1500:
        raise ValueError(f'После извлечения {len(speech)} символов речи; допустимо 1–1500.')
    if not title:
        title = next((s['headline'] for s in scenes if s['headline']), utterances[0]['text'])[:90]
    duration_match = re.search(r'(\d+(?:[.,]\d+)?)\s*[–—-]\s*(\d+(?:[.,]\d+)?)\s*секунд', source, re.I)
    requested = [float(v.replace(',','.')) for v in duration_match.groups()] if duration_match else None
    warnings.append('Таймкоды — ориентир. Финальная длина определяется речью, без ускорения и немых добивок.')
    warnings.append('Графика иллюстрирует текст сценария; реальные интерфейсы и команды не генерируются и не исполняются.')
    if re.search(r'музык', source, re.I): warnings.append('Музыка не добавляется: аудиофайл с разрешённым использованием не выбран.')
    if re.search(r'крупный\s+план', source, re.I): warnings.append('Герой снимается средним планом; автоматического увеличения лица нет.')
    warnings.append('Субтитры разбиты на короткие группы; время внутри реплики приблизительное, без ASR-выравнивания.')
    return dict(version=1, source=source, title=title[:90], speech=speech, utterances=utterances,
                scenes=scenes, requested_duration=requested, warnings=warnings)


def validate_plan(plan, script):
    if plan.get('version') != 1 or plan.get('speech') != script:
        raise ValueError('План устарел: подготовьте сценарий заново.')
    rebuilt = prepare(plan['source'], plan.get('title',''))
    for key in ('speech','utterances','scenes'):
        if rebuilt[key] != plan.get(key): raise ValueError('Некорректная структура плана: '+key)
    return [u['text'] for u in plan['utterances']]


def actual_timeline(plan, captions, duration):
    if len(captions) != len(plan['utterances']): raise ValueError('Число аудиореплик не совпало с планом.')
    scenes=[]
    for index, scene in enumerate(plan['scenes']):
        first=scene['utterance_ids'][0]
        next_first=plan['scenes'][index+1]['utterance_ids'][0] if index+1<len(plan['scenes']) else None
        scenes.append({**scene, 'start':captions[first]['start'],
                       'end':captions[next_first]['start'] if next_first is not None else duration})
    return scenes


if __name__ == '__main__':
    try:
        data=json.load(sys.stdin)
        print(json.dumps(prepare(data['source'],data.get('title','')),ensure_ascii=False))
    except (ValueError, KeyError) as exc:
        print(str(exc),file=sys.stderr); sys.exit(2)
