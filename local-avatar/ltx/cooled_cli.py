"""LTX CLI with synchronized cooling callbacks; upstream files stay unchanged."""
import mlx.core as mx
from thermal_guard import ThermalGuard
from ltx_pipelines_mlx._base import BasePipeline
from ltx_pipelines_mlx.utils.blocks import PromptEncoder, VideoDecoder
from ltx_pipelines_mlx.cli import main

guard = ThermalGuard()
# Check between streamed blocks, which upstream already materializes separately.
from ltx_core_mlx.loader.block_streaming import BlockStreamer
original_bind = BlockStreamer.bind
def cooled_bind(self, block, idx, *args, **kwargs):
    guard.check_if_hot(f'transformer-block-{idx}')
    return original_bind(self, block, idx, *args, **kwargs)
BlockStreamer.bind = cooled_bind

# Gemma also needs internal cooling checkpoints on a fanless 16 GB laptop.
from mlx_lm.models.gemma3_text import TransformerBlock
original_gemma_block = TransformerBlock.__call__
gemma_count = 0
def cooled_gemma_block(self, *args, **kwargs):
    global gemma_count
    result = original_gemma_block(self, *args, **kwargs)
    gemma_count += 1
    if gemma_count % 4 == 0:
        mx.eval(result)
        guard.check_if_hot(f'gemma-block-{gemma_count}')
    return result
TransformerBlock.__call__ = cooled_gemma_block

original_hook = BasePipeline._stepwise_hook
def cooled_hook(self, *args, **kwargs):
    previous = original_hook(self, *args, **kwargs)
    stage = kwargs.get('stage')
    def step(index, total, prediction, sigma):
        mx.eval(prediction)
        mx.synchronize()
        if previous is not None:
            previous(index, total, prediction, sigma)
        guard.checkpoint(f'stage-{stage}-step-{index+1}/{total}')
    return step
BasePipeline._stepwise_hook = cooled_hook

original_prompt = PromptEncoder.encode
def cooled_prompt(self, *args, **kwargs):
    guard.checkpoint('before-text')
    value = original_prompt(self, *args, **kwargs)
    guard.checkpoint('after-text')
    return value
PromptEncoder.encode = cooled_prompt

original_decode = VideoDecoder.decode_and_stream
def cooled_decode(self, *args, **kwargs):
    guard.checkpoint('before-decode')
    value = original_decode(self, *args, **kwargs)
    guard.checkpoint('after-decode')
    return value
VideoDecoder.decode_and_stream = cooled_decode

from ltx_core_mlx.model.video_vae.video_vae import VideoDecoder as ConvVideoDecoder
from ltx_core_mlx.model.video_vae.resnet import ResBlockStage
original_res_stage = ResBlockStage.__call__
def cooled_res_stage(self, *args, **kwargs):
    value = original_res_stage(self, *args, **kwargs)
    mx.eval(value)
    guard.check_if_hot('vae-residual-stage')
    return value
ResBlockStage.__call__ = cooled_res_stage

original_tiles = ConvVideoDecoder.tiled_decode
def cooled_tiles(self, *args, **kwargs):
    for index, chunk in enumerate(original_tiles(self, *args, **kwargs)):
        mx.eval(chunk)
        guard.check_if_hot(f'decode-tile-{index}')
        yield chunk
ConvVideoDecoder.tiled_decode = cooled_tiles

try:
    guard.checkpoint('before-run')
    main()
finally:
    guard.close()
