"""Isolated Qwen worker; invoked by pipeline.py in the existing MLX environment."""
import json, sys, os
from pathlib import Path
config = json.loads(Path(sys.argv[1]).read_text())
root = Path(config['project'])
os.environ['HF_HOME'] = str(root/'local-avatar/models')
import mlx.core as mx
import numpy as np
import soundfile as sf
sys.path.insert(0, str(root/'local-avatar/ltx'))
from thermal_guard import ThermalGuard
from mlx_audio.tts.utils import load_model
job = Path(config['job'])
from pronunciation import Lexicon, for_tts, targeted_tts
pronunciation_mode = config.get('pronunciation_mode', 'review')
if pronunciation_mode not in ('review', 'acute', 'capital', 'targeted'):
    raise ValueError('Неизвестный режим произношения: ' + pronunciation_mode)
lexicon = Lexicon()
try:
    pronunciation = [lexicon.annotate(text) for text in config['sentences']]
finally:
    lexicon.close()
if pronunciation_mode != 'review' and any(not row['dictionary_available'] for row in pronunciation):
    raise ValueError('Сначала установите локальный словарь: pronunciation.py --install')
for row in pronunciation:
    if pronunciation_mode == 'review':
        row['tts_text'] = row['original']
    elif pronunciation_mode == 'targeted':
        row['tts_text'] = targeted_tts(row['original'])
    else:
        row['tts_text'] = for_tts(row['marked'], pronunciation_mode)
(job/'pronunciation-plan.json').write_text(json.dumps(dict(mode=pronunciation_mode, utterances=pronunciation), ensure_ascii=False, indent=2))
guard = ThermalGuard()
try:
    guard.checkpoint('before-voice', minimum=1)
    model = load_model(str(root/'local-avatar/models/qwen3-tts-0.6b-4bit'))
    for index, text in enumerate(config['sentences']):
        output = job/f'voice-{index:03}.wav'
        print(f'VOICE {index+1}/{len(config["sentences"])}: {text}', flush=True)
        guard.checkpoint(f'voice-{index}', minimum=1)
        mx.random.seed(config.get('voice_seed', 42))
        spoken = pronunciation[index]['tts_text']
        chunks = list(model.generate(text=spoken.replace('Kubernetes', 'Кубернетес'),
            lang_code='russian', ref_audio=str(job/'reference.wav'),
            ref_text=config['reference_text'], temperature=config.get('voice_temperature', .5), max_tokens=900, verbose=True))
        if not chunks:
            raise RuntimeError('Модель не вернула аудио')
        audio = np.concatenate([np.asarray(c.audio).reshape(-1) for c in chunks])
        if not len(audio) or not np.isfinite(audio).all() or np.max(np.abs(audio)) < .0001:
            raise RuntimeError('Пустой или повреждённый голос')
        audio *= min(1, .95/np.max(np.abs(audio)))
        sf.write(output, audio, chunks[0].sample_rate)
        mx.clear_cache()
finally:
    guard.close()
