"""Read-only runtime audit; never loads models or starts GPU inference."""
from pathlib import Path
import importlib.metadata
import json
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]

def audit():
    checks=[]
    for name,relative,modules in [
        ('compositor','local-avatar/.venv-lipsync/bin/python',['PIL','numpy','soundfile']),
        ('espeech','local-avatar/.venv-tts-compare/bin/python',['torch','torchaudio','f5_tts','mlx.core','soundfile']),
        ('ltx','local-avatar/ltx-2-mlx/.venv/bin/python',['ltx_pipelines_mlx','ltx_core_mlx'])]:
        executable=ROOT/relative
        try:
            result=subprocess.run([str(executable),'-c',';'.join('import '+m for m in modules)],capture_output=True,text=True,timeout=40)
            checks.append(dict(name=name,ok=result.returncode==0,message=result.stderr[-2000:]))
        except (OSError,subprocess.TimeoutExpired) as exc:checks.append(dict(name=name,ok=False,message=str(exc)))
    for name in ['ffmpeg','ffprobe','macmon']:
        checks.append(dict(name=name,ok=shutil.which(name) is not None))
    try:
        import pipeline
        pipeline.dependencies()
        checks.append(dict(name='model_paths_and_stress_dictionary',ok=True))
    except ValueError as exc:checks.append(dict(name='model_paths_and_stress_dictionary',ok=False,message=str(exc)))
    return dict(version='0.5.0',voice_engine='espeech',voice_speed=1.0,checks=checks,ok=all(c['ok'] for c in checks),inference_tested=False)

if __name__=='__main__':
    result=audit(); print(json.dumps(result,ensure_ascii=False,indent=2));sys.exit(0 if result['ok'] else 1)
