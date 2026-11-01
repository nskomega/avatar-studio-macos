"""Allowlist export: no parent Git history, personal data or generated binaries."""
from pathlib import Path
import argparse
import shutil

ROOT=Path(__file__).resolve().parents[2]
FILES=[
 'mac-app/VERSION','mac-app/README.md','mac-app/OPEN_SOURCE_README.md','mac-app/SETUP.md',
 'mac-app/CLI.md','mac-app/CHANGELOG.md','mac-app/LICENSE','mac-app/THIRD_PARTY.md',
 'mac-app/VALIDATION.md','mac-app/build.md','mac-app/build.sh','mac-app/studio',
 'mac-app/design-system.json','mac-app/DESIGN_SYSTEM.md','mac-app/.gitignore',
 'mac-app/requirements-compositor.txt','mac-app/requirements-voice.txt',
 'mac-app/Sources/main.swift','mac-app/tools/make-icon-vector-v1.swift','mac-app/tools/export_public.py',
 'mac-app/engine/README.md',
 'local-avatar/reels/timing.py','local-avatar/ltx/thermal_guard.py',
 'local-avatar/ltx/thermal_state.swift','local-avatar/ltx/cooled_cli.py',
]
FILES += ['mac-app/engine/'+name for name in ['pipeline.py','voice.py','voice_qwen.py','voice-settings.json','phonetics.py','pronunciation.py','pronunciation-overrides.json','scenario.py','storyboard.py','history.py','drive_upload.py','studio_cli.py','batch.py','doctor.py']]
FILES += ['mac-app/tests/'+name for name in ['test_scenario.py','test_history.py','test_pipeline_flow.py','test_pronunciation.py','test_batch.py','check_storyboard.py','profile-smoke.sh','profile-checks.swift','fixtures/structured-scenario.txt']]
FILES += ['mac-app/examples/'+name for name in ['scenarios.json','scenarios.csv']]
IGNORE='''# Private runtime/media; never commit these directories
.DS_Store
__pycache__/
*.py[cod]
.env
.env.*
!.env.example
*.log
*.jsonl
*.sqlite*
*.wav
*.m4a
*.mp3
*.mp4
*.mov
*.png
*.jpg
*.jpeg
*.webp
*.tiff
*.icns
*.pt
*.pth
*.safetensors
*.pem
*.key
mac-app/build/
mac-app/jobs/
mac-app/data/
local-avatar/avatar.json
local-avatar/audio/
local-avatar/models/
local-avatar/outputs/
local-avatar/logs/
local-avatar/ltx/work/
local-avatar/ltx-2-mlx/
local-avatar/.venv*/
assets/
videos/
projects/
'''

def export(destination):
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    for name in FILES:
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target)
    for source,target in [('OPEN_SOURCE_README.md','README.md'),('LICENSE','LICENSE'),('CHANGELOG.md','CHANGELOG.md')]:
        shutil.copy2(ROOT/'mac-app'/source,destination/target)
    (destination/'.gitignore').write_text(IGNORE)
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('destination');args=parser.parse_args()
    print(export(args.destination))
