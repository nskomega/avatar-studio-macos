# Runtime setup

Apple Silicon macOS, Command Line Tools, Python 3.11 (voice/LTX), Python 3.10+
(compositor). Build works without models; inference requires separate environments.
Run commands from the repository root. No automatic download runs on app launch.

```sh
brew install ffmpeg macmon uv
uv venv --python 3.11 local-avatar/.venv-lipsync
uv pip install --python local-avatar/.venv-lipsync/bin/python -r mac-app/requirements-compositor.txt
uv venv --python 3.11 local-avatar/.venv-tts-compare
uv pip install --python local-avatar/.venv-tts-compare/bin/python -r mac-app/requirements-voice.txt
```

Voice dependencies use F5-TTS; verify PyTorch/torchaudio wheels compatible with your
macOS/architecture. Tested local versions are documented below, not a cross-machine
lockfile guarantee. Other versions may require testing.

## LTX runtime

External checkout, not vendored:

```sh
git clone https://github.com/dgrauet/ltx-2-mlx.git local-avatar/ltx-2-mlx
git -C local-avatar/ltx-2-mlx checkout 62b7651406f8ad4a0b7a3f36a93874a1015d59ca
(cd local-avatar/ltx-2-mlx && uv sync)
mkdir -p local-avatar/ltx/work
xcrun swiftc local-avatar/ltx/thermal_state.swift -o local-avatar/ltx/work/thermal-state
```

That checkout is expected to provide `.venv/bin/python` and ltx_core_mlx /
ltx_pipelines_mlx. See upstream installation instructions if uv changes.

## Models and dictionary

Read model terms before downloading. Obtain these separately:

| Local path | Source |
|---|---|
| local-avatar/models/espeech-rl-v2/ | ESpeech/ESpeech-TTS-1_RL-V2: espeech_tts_rlv2.pt, vocab.txt |
| local-avatar/models/ltx-2.3-mlx-q4/ | dgrauet/ltx-2.3-mlx-q4, revision 56a5866d638ecfe37c54d348e88938235185c2d4 |
| local-avatar/models/gemma-3-12b-it-4bit/ | mlx-community/gemma-3-12b-it-4bit, revision 86cc6a8dedbc456dd0e4af01a9d09f396f77e558 |

F5-TTS also needs the Vocos vocoder cache. First voice generation may retrieve it
from charactr/vocos-mel-24khz via Hugging Face; warm the cache if you need offline use.
The app does not upload your media to Hugging Face. Optional rclone upload is separate.

```sh
local-avatar/.venv-lipsync/bin/python mac-app/engine/pronunciation.py --install
local-avatar/.venv-lipsync/bin/python mac-app/engine/doctor.py
./mac-app/build.sh
```

Dictionary installer pins revision and verifies SHA256. Models are not downloaded
by this document or included in Git. Keep sufficient disk and memory headroom;
16 GB local operation was possible with cooling but is not a performance guarantee.

Locally tested imports/inference: f5-tts 1.1.22, torch 2.15.0, torchaudio 2.11.1,
mlx 0.32.4, soundfile 0.14.0 in the voice environment; Pillow 11.3.0,
NumPy 1.26.4, SoundFile 0.12.1 in the compositor environment.

These are observed environment versions; do not infer that arbitrary fresh wheel
combinations will be compatible. No clean-room full model installation was run
for this release. See THIRD_PARTY.md for source links and independent terms.
