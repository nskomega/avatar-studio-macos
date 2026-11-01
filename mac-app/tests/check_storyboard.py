"""Compositor smoke with synthetic color and tone fixtures, NOT avatar inference."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
import pipeline
import storyboard
from PIL import Image
root=pipeline.ROOT
job=root/'mac-app/jobs/storyboard-smoke';job.mkdir(parents=True,exist_ok=True)
audio=job/'fixture-audio.wav'
pipeline.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=220:sample_rate=24000','-t','4',audio],start_new_session=True)
fixture_clip=job/'synthetic-color.mp4'
pipeline.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','color=c=orange:s=512x896:r=24','-t','1.5','-threads','2',fixture_clip],start_new_session=True)
scenes=[dict(id=1,kind='hero',style='statement',speech='Проверка размещения субтитров.',headline='ПРОВЕРКА КОМПОНОВКИ',labels=[],start=0,end=1.5),
        dict(id=2,kind='graphic',style='diagram',speech='Один элемент связан с другим. Это иллюстрация текста сценария.',headline='СХЕМА ПО ТЕКСТУ',labels=['СХЕМА ПО ТЕКСТУ'],start=1.5,end=4)]
shots=[dict(start=0,end=1.5,scene_id=1,clip=str(fixture_clip)),
       dict(start=1.5,end=4,scene_id=2)]
captions=[dict(start=0,end=1.5,text='Проверка размещения субтитров без перекрытия лица.'),dict(start=1.5,end=4,text=scenes[1]['speech'])]
output=job/'test-compositor.mp4'
caps=storyboard.render(shots,scenes,audio,captions,output,job,pipeline,dict(accent='#FF5C1F',headline='ТЕСТ КОМПОНОВКИ'))
pipeline.run(['ffmpeg','-v','error','-xerror','-i',output,'-f','null','-'],start_new_session=True)
probe=pipeline.probe(output);video=next(s for s in probe['streams'] if s['codec_type']=='video')
assert (video['width'],video['height'])==(720,1280)
assert abs(pipeline.duration(output)-4)<.15
assert any(s['codec_type']=='audio' for s in probe['streams'])
assert caps[0]['start']==0 and abs(caps[-1]['end']-4)<.01
assert output.with_suffix('.srt').exists()
# Pure graphic frame difference proves scene elements change, not only a static card.
a=storyboard.compose(scenes[1],1.5);b=storyboard.compose(scenes[1],2.8)
assert a.tobytes()!=b.tobytes()
# Hero viewport is wholly ABOVE the independent subtitle band; header is above viewport.
fixture=Image.new('RGB',(512,896),'magenta')
im=storyboard.compose(scenes[0],.5,'Двухстрочные субтитры для проверки размещения',fixture)
assert im.getpixel((360,1035)) != (255,0,255)
report=dict(result='passed',checks=['real FFmpeg full decode','720x1280/audio/4 sec','SRT','animated graphics','separate hero/caption viewport'],
            fixture_only=True,lipsync='not tested; synthetic color and tone fixtures',output=str(output))
(job/'test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
