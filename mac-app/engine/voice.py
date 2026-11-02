# -*- coding: utf-8 -*-
"""Production ESpeech worker. Canonical scripts and captions are never rewritten."""
import json
import os
from pathlib import Path
import re
import sys


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    root, job = Path(config['project']), Path(config['job'])
    if config.get('voice_engine', 'espeech') != 'espeech':
        raise ValueError('Unsupported production voice engine')
    os.environ['HF_HOME'] = str(root/'local-avatar/models')
    os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    sys.path.insert(0, str(root/'local-avatar/ltx'))
    import numpy as np
    import soundfile as sf
    import torch
    from f5_tts.infer.utils_infer import load_model, load_vocoder, infer_batch_process
    from f5_tts.model import DiT
    from thermal_guard import ThermalGuard
    from pronunciation import Lexicon
    from phonetics import apply_spelling_hints, expand_spoken_terms
    settings = json.loads(Path(__file__).with_name('voice-settings.json').read_text())
    lexicon = Lexicon()
    try:
        plan = [lexicon.annotate(apply_spelling_hints(expand_spoken_terms(t, settings.get('spoken_terms', {})), settings['spelling_hints'])) for t in config['sentences']]
        for row, original in zip(plan, config['sentences']):
            row['canonical_text'] = original
        reference = lexicon.annotate(config['reference_text'])
    finally:
        lexicon.close()
    if not reference['dictionary_available']:
        raise ValueError('Install the stress dictionary: pronunciation.py --install')
    (job/'pronunciation-plan.json').write_text(json.dumps(dict(engine='espeech', utterances=plan, reference=reference), ensure_ascii=False, indent=2))
    plus = lambda s: re.sub(r'([А-Яа-яЁё])\u0301', r'+\1', s)
    guard = ThermalGuard()
    try:
        torch.set_num_threads(4)
        guard.checkpoint('before-espeech', minimum=1)
        model_path = root/'local-avatar/models/espeech-rl-v2'
        model = load_model(DiT, dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4), str(model_path/'espeech_tts_rlv2.pt'), vocab_file=str(model_path/'vocab.txt'), device='mps')
        vocoder = load_vocoder(device='mps', hf_cache_dir=str(root/'local-avatar/models/hub'))
        def cooling(module, inputs):
            torch.mps.synchronize()
            guard.check_if_hot('espeech-diffusion')
        model.transformer.register_forward_pre_hook(cooling)
        audio, rate = sf.read(job/'reference.wav', dtype='float32')
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        tensor = torch.from_numpy(audio.copy()).unsqueeze(0)
        for index, row in enumerate(plan):
            guard.checkpoint(f'espeech-{index}', minimum=1)
            torch.manual_seed(config.get('voice_seed', 42))
            samples, sr, _ = next(infer_batch_process((tensor, rate), plus(reference['marked']), [plus(row['marked'])], model, vocoder, progress=None, nfe_step=32, speed=1.0, device='mps'))
            torch.mps.synchronize()
            samples = np.asarray(samples).reshape(-1)
            if not len(samples) or not np.isfinite(samples).all() or np.max(np.abs(samples)) < .0001:
                raise ValueError('Empty or invalid ESpeech output')
            samples *= min(1, .95 / np.max(np.abs(samples)))
            sf.write(job/f'voice-{index:03}.wav', samples, sr, subtype='PCM_24')
            print(f'VOICE {index+1}/{len(plan)} ESpeech', flush=True)
        (job/'voice-production.json').write_text(json.dumps(dict(engine='ESpeech/ESpeech-TTS-1_RL-V2', synthesis_speed=1.0, atempo=1.0, stress='dictionary_plus', human_review='pending'), indent=2))
    finally:
        guard.close()


if __name__ == '__main__':
    main()
