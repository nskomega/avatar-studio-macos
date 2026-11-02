# Avatar Studio for macOS

Native AppKit studio for local avatar Reels on Apple Silicon. Version **0.6.0**.
Russian GUI; ESpeech voice synthesis, speech-first timelines, LTX MLX avatar shots,
animated explanatory graphics, subtitle export and optional rclone delivery.

- Import a list of scripts: JSON/CSV or multiple TXT files.
- Pick a photo folder: one random image per video, snapshotted for reproducibility.
- Run sequentially; stop and resume a queue without repeating completed jobs.
- Preview voice before video; explicit thermal monitoring and cooperative cooling.
- Keep prompts and generation history locally in SQLite.

The source repository contains no personal portraits, voice recordings, profiles,
model weights, virtual environments, application binaries or previous private Git history.

## Build and run

```sh
./mac-app/build.sh
open 'mac-app/build/Аватар Студия.app'
```

Build requires macOS Command Line Tools. Generation requires **separate local runtime
setup**: [SETUP](mac-app/SETUP.md). The .app points at this checkout; rebuild if you
move it. This is not a self-contained model installer or notarized binary release.
First voice run may download the public vocoder to the local Hugging Face cache.

[Russian usage guide](mac-app/README.md) · [Examples](mac-app/examples/scenarios.json) ·
[Changelog](CHANGELOG.md) · [Validation](mac-app/VALIDATION.md) ·
[External components](mac-app/THIRD_PARTY.md) · [MIT license](LICENSE).

Model quality and lip sync require human review. Test success is not a guarantee
of facial fidelity, voice likeness or publishing quality. Use only authorized
reference media. No automatic social-media publication is provided.
