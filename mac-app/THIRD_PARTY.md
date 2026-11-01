# External components

The MIT license in this repository covers its own application code only. No model
weights, dictionaries, external source checkout, voices or portraits are distributed.
Install dependencies separately and consult their own licenses and model cards.

- [ESpeech RL-V2](https://huggingface.co/ESpeech/ESpeech-TTS-1_RL-V2): model card
  identifies Apache-2.0. ESpeech worker configuration follows the documented DiT
  configuration; no upstream model implementation is vendored.
- [F5-TTS](https://github.com/SWivid/F5-TTS): inference dependency; models and
  vocoder may have separate terms. No promise that all dependencies share MIT.
- [LTX MLX](https://github.com/dgrauet/ltx-2-mlx): separate MIT-licensed source
  checkout, tested commit `62b7651406f8ad4a0b7a3f36a93874a1015d59ca`.
- [LTX-2.3 MLX model](https://huggingface.co/dgrauet/ltx-2.3-mlx-q4) and
  [Gemma](https://huggingface.co/mlx-community/gemma-3-12b-it-4bit): obtain separately
  subject to the corresponding model terms. Application license does not relicense weights.
- [Russian stress dictionary](https://huggingface.co/ruaccent/accentuator): fetched
  separately at the revision/checksums in pronunciation.py; not vendored.
- PyTorch, MLX, Pillow, NumPy, SoundFile, FFmpeg, macmon and optional rclone retain
  their respective licenses. macOS system fonts/frameworks are not redistributed.

Use reference media only with the subject's permission. Do not describe synthetic
output or test fixtures as recordings of real events.
