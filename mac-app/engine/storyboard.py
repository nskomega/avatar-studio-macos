"""Speech-timed hero/animated graphic compositor; no fabricated terminal output."""
from pathlib import Path
import json
import math
import subprocess
import time
from PIL import Image, ImageDraw, ImageFont, ImageOps

W,H,FPS=720,1280,24
FONT='/System/Library/Fonts/Supplemental/Arial Bold.ttf'


def font(size): return ImageFont.truetype(FONT,size)


def wrap(text,size,width):
    f=font(size); lines=[]; line=''
    for word in text.split():
        trial=(line+' '+word).strip()
        if f.getlength(trial)>width and line: lines.append(line); line=''
        # Split exceptionally long display tokens without truncating spoken text.
        while f.getlength(word)>width:
            count=1
            while count<len(word) and f.getlength(word[:count+1])<=width: count+=1
            if line:lines.append(line);line=''
            lines.append(word[:count]);word=word[count:]
        line=(line+' '+word).strip()
    if line:lines.append(line)
    return lines


def text(im,xy,value,size=32,color='#F4F5F7',width=620,max_lines=None):
    lines=wrap(value,size,width)
    if max_lines is not None and len(lines)>max_lines:
        return text(im,xy,value,max(16,size-2),color,width,max_lines) if size>16 else lines
    draw=ImageDraw.Draw(im)
    for i,line in enumerate(lines):draw.text((xy[0],xy[1]+i*(size+10)),line,font=font(size),fill=color)
    return lines


def short_captions(captions):
    result=[]
    for caption in captions:
        words=caption['text'].split(); groups=[]; current=[]
        for word in words:
            candidate=' '.join(current+[word])
            if current and (len(wrap(candidate,32,612))>2 or len(current)>=6):
                groups.append(' '.join(current)); current=[]
            current.append(word)
        if current:groups.append(' '.join(current))
        total=sum(len(g) for g in groups); cursor=caption['start']
        for group in groups:
            end=cursor+(caption['end']-caption['start'])*len(group)/max(1,total)
            result.append(dict(start=cursor,end=end,text=group));cursor=end
    return result


def compose(scene,t,caption='',hero=None,logo=None,design=None):
    design=design or {}; accent=design.get('accent','#FF5C1F')
    light=design.get('theme')=='light-editorial'
    bg='#F6F3EA' if light else '#11151D'; fg='#142033' if light else '#F4F5F7'
    panel='#E5E7EB' if light else '#202733'
    im=Image.new('RGB',(W,H),bg); draw=ImageDraw.Draw(im)
    local=t-scene['start']
    is_hero=hero is not None
    if is_hero:
        # Entire source is contained in its own viewport: never crop/enlarge the face.
        fitted=ImageOps.contain(hero.convert('RGB'),(W,800),Image.Resampling.LANCZOS)
        im.paste(fitted,((W-fitted.width)//2,100+(800-fitted.height)//2))
    else:
        draw.rounded_rectangle((24,190,696,890),24,fill=panel)
        labels=scene.get('labels') or [scene.get('headline') or design.get('headline') or 'ПО ТЕКСТУ СЦЕНАРИЯ']
        heading=labels[min(len(labels)-1,int(local/4))]
        text(im,(48,224),heading,44,accent,624,3)
        # Each displayed phrase is verbatim from the supplied speech.
        words=scene['speech'].split(); phrases=[' '.join(words[i:i+7]) for i in range(0,len(words),7)] or ['']
        page=int(local/4)%max(1,math.ceil(len(phrases)/3)); shown=phrases[page*3:page*3+3]
        style=scene['style']
        if style=='comparison' and len(phrases)>1:
            shown=phrases[(int(local/4)*2)%len(phrases):][:2]
            for i,phrase in enumerate(shown):
                x=48+i*320
                draw.rounded_rectangle((x,450,x+304,870),18,fill=bg,outline=accent if int(local/1.3)%2==i else '#58616F',width=3)
                text(im,(x+20,498),f'0{i+1}',26,accent,260)
                text(im,(x+20,566),phrase,32,fg,264,5)
        else:
            for i,phrase in enumerate(shown):
                y=450+i*148
                shift=round(18*(1-min(1,max(0,local-i*.12)/.4)))
                active=int(local/1.2)%max(1,len(shown))==i
                draw.rounded_rectangle((48+shift,y,672,y+134),16,fill=bg,outline=accent if active else '#58616F',width=3 if active else 1)
                text(im,(66+shift,y+15),'→' if style=='diagram' else f'0{page*3+i+1}',24,accent,60)
                text(im,(122+shift,y+19),phrase,29,fg,520-shift,3)
                if style=='diagram' and i<len(shown)-1:
                    draw.line((360,y+136,360,y+161),fill=accent,width=4)
                    draw.polygon([(352,y+151),(368,y+151),(360,y+161)],fill=accent)
        # Meaningful reveal underline; not an alleged experiment/progress measurement.
        draw.rectangle((48,401,48+round(580*min(1,local/.45)),405),fill=accent)
        text(im,(36,906),'Иллюстрация по сценарию · не запись экрана',18,fg,648,1)
    # Global header lives outside both hero viewport and subtitles.
    if logo:im.paste(logo,(36,26),logo)
    header=design.get('headline') if t<3 else scene.get('headline','')
    if header:text(im,(190 if logo else 36,25),header,26,accent,494 if logo else 648,2)
    if caption:
        y=930 if is_hero else 948
        lines=wrap(caption,32,612)
        height=min(112,len(lines)*42+28)
        draw.rounded_rectangle((36,y,684,y+height),14,fill=panel)
        draw.rounded_rectangle((36,y,41,y+height),2,fill=accent)
        text(im,(54,y+12),caption,32,fg,612,2)
    return im


def srt(captions):
    def stamp(t):
        n=round(t*1000);return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'
    return '\n\n'.join(f'{i+1}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"]}' for i,c in enumerate(captions))+'\n'


def render(shots,scenes,audio,captions,output,job,pipeline,design=None):
    import cv2
    duration=pipeline.duration(audio); caps=short_captions(captions)
    (job/'captions.json').write_text(json.dumps(caps,ensure_ascii=False,indent=2))
    output.with_suffix('.srt').write_text(srt(caps))
    logo=None
    if (job/'logo.png').exists():
        logo=Image.open(job/'logo.png').convert('RGBA');logo.thumbnail((125,64))
    encoder=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}',
        '-r',str(FPS),'-i','pipe:0','-i',str(audio),'-map','0:v','-map','1:a','-c:v','libx264',
        '-preset','fast','-crf','19','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k',
        '-movflags','+faststart','-t',str(duration),str(output)],stdin=subprocess.PIPE,start_new_session=True)
    pipeline.children.add(encoder); capture=None; active=None; previews=[]; current_shot=0; current_scene=0; caption_index=0
    try:
        for index in range(math.ceil(duration*FPS)):
            t=index/FPS
            while current_shot+1<len(shots) and t>=shots[current_shot]['end']:current_shot+=1
            while current_scene+1<len(scenes) and t>=scenes[current_scene]['end']:current_scene+=1
            while caption_index+1<len(caps) and t>=caps[caption_index]['end']:caption_index+=1
            shot=shots[current_shot];scene=scenes[current_scene];hero=None
            if shot.get('clip'):
                if active!=shot['clip']:
                    if capture:capture.release()
                    capture=cv2.VideoCapture(shot['clip']);active=shot['clip']
                number=max(0,round((t-shot['start'])*24))
                capture.set(cv2.CAP_PROP_POS_FRAMES,number);ok,frame=capture.read()
                if not ok:raise RuntimeError('Не прочитан кадр героя: '+str(number))
                hero=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            caption=caps[caption_index]['text'] if caps and caps[caption_index]['start']<=t<caps[caption_index]['end'] else ''
            im=compose(scene,t,caption,hero,logo,design)
            encoder.stdin.write(im.tobytes())
            if index%max(1,round(duration*FPS/12))==0:
                preview=job/f'preview-{index:05}.jpg'; im.save(preview);previews.append(preview)
            if index%120==0:
                while True:
                    metrics=json.loads(subprocess.check_output(['macmon','pipe','-s','1','-i','500'],text=True))
                    with (job/'export-thermals.jsonl').open('a') as handle:handle.write(json.dumps(metrics)+'\n')
                    if max(metrics['temp']['cpu_temp_avg'],metrics['temp']['gpu_temp_avg'])<65:break
                    time.sleep(3)
        encoder.stdin.close()
        if encoder.wait():raise RuntimeError('Ошибка экспорта storyboard')
        sheet=Image.new('RGB',(720,math.ceil(len(previews)/4)*320),'#11151D')
        for i,path in enumerate(previews):
            with Image.open(path) as im:sheet.paste(im.resize((180,320)),((i%4)*180,(i//4)*320))
        sheet.save(job/'storyboard.jpg')
    finally:
        if capture:capture.release()
        if encoder.poll() is None:encoder.terminate();encoder.wait()
        pipeline.children.discard(encoder)
    return caps
