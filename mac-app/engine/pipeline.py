"""Per-job local pipeline. Never mutates the reviewed v0.4.0 reel or its inputs."""
from pathlib import Path
import argparse, hashlib, json, math, os, re, shutil, subprocess, sys, time, signal, fcntl

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
children = set()
VERSION = (HERE.parent/"VERSION").read_text().strip()

def run(args, **kwargs):
    print('RUN', args[0], flush=True)
    p = subprocess.Popen([str(a) for a in args], **kwargs)
    children.add(p)
    try:
        code = p.wait()
        if code:
            raise RuntimeError(f'Этап завершился с кодом {code}: {args[0]}')
    finally:
        children.discard(p)

def stop(signum, frame):
    for p in list(children):
        try: os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError: pass
    for p in list(children):
        try: p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            p.wait()
    raise SystemExit(130)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

def duration(path):
    return float(probe(path)['format']['duration'])

def revision():
    try:
        return subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):
        return 'source-archive-'+VERSION


def sha(path):
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def status(job, stage, message, **extra):
    data = dict(stage=stage, message=message, **extra)
    temp = job/'status.tmp'
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    temp.replace(job/'status.json')
    try:
        from history import record_job
        record_job(job, data)
    except Exception as exc:
        print('История не обновлена: '+str(exc), flush=True)
    print(message, flush=True)

def dependencies(voice_only=False):
    required = [ROOT/'local-avatar/.venv-tts-compare/bin/python',
        ROOT/'local-avatar/models/espeech-rl-v2/espeech_tts_rlv2.pt',
        ROOT/'local-avatar/models/espeech-rl-v2/vocab.txt',
        ROOT/'local-avatar/models/russian-stress/stress.sqlite3',
        ROOT/'local-avatar/ltx/work/thermal-state']
    if not voice_only:
        required += [ROOT/'local-avatar/ltx-2-mlx/.venv/bin/python',
            ROOT/'local-avatar/models/ltx-2.3-mlx-q4', ROOT/'local-avatar/models/gemma-3-12b-it-4bit']
    missing = [str(p) for p in required if not p.exists()]
    missing += [name for name in ['ffmpeg','ffprobe','macmon'] if not shutil.which(name)]
    if missing: raise ValueError('Missing dependencies: '+', '.join(missing))


def validate(config):
    for key in ['photo','reference_audio']:
        if not Path(config.get(key,'')).is_file(): raise ValueError(f'Не выбран файл: {key}')
    from PIL import Image
    with Image.open(config['photo']) as im: im.verify()
    if not config.get('reference_text','').strip(): raise ValueError('Нужен точный текст записи голоса')
    seconds = duration(config['reference_audio'])
    if not 2 <= seconds <= 30: raise ValueError('Выбери чистый образец голоса длительностью 2–30 секунд. Длинную диктовку сначала нужно разметить.')
    script = config.get('script','').strip()
    if not 1 <= len(script) <= 1500: raise ValueError('Сценарий должен содержать от 1 до 1500 символов')
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', script) if s.strip()]
    if any(len(s)>350 for s in sentences): raise ValueError('Разбей длинные предложения: максимум 350 символов на реплику')
    if config.get('scenario_plan'):
        from scenario import validate_plan
        sentences=validate_plan(config['scenario_plan'], script)
    design = config.get('design', {})
    system = json.loads((HERE.parent/'design-system.json').read_text())
    if design.get('theme','dark-tech') not in system['themes']: raise ValueError('Неизвестная тема оформления')
    if design.get('accent') and not re.fullmatch(r'#[0-9a-fA-F]{6}',design['accent']): raise ValueError('Акцент должен быть цветом #RRGGBB')
    return sentences

def wrap_pixels(text, font, width):
    lines=[]; line=''
    for word in text.split():
        if line and font.getlength(line+' '+word)>width:
            lines.append(line); line=''
        while font.getlength(word)>width:
            count=1
            while count<len(word) and font.getlength(word[:count+1])<=width: count+=1
            lines.append(word[:count]); word=word[count:]
        line=(line+' '+word).strip()
    if line: lines.append(line)
    return lines

def export(source, audio, captions, output, job, design=None):
    """Stream frames through Pillow for portable caption rendering without libass."""
    from PIL import Image, ImageDraw, ImageFont, ImageColor
    design = design or {}
    system_path = job/'design-system.json'
    system = json.loads((system_path if system_path.exists() else HERE.parent/'design-system.json').read_text())
    theme = dict(system['themes'][design.get('theme', 'dark-tech')])
    if design.get('accent'): theme['accent'] = design['accent']
    tokens = system['tokens']
    w,h,fps = (system['canvas'][key] for key in ['width','height','fps'])
    safe_x = tokens['safe_x']; safe_top = tokens['safe_top']
    headline = design.get('headline','')[:90]
    panel_color = (*ImageColor.getrgb(theme['panel']), theme['panel_alpha'])
    length=duration(audio)
    decoder=subprocess.Popen(['ffmpeg','-v','error','-i',str(source),'-an','-vf',
        f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}',
        '-threads','2','-t',str(length),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE, start_new_session=True)
    encoder=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
        '-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-i',str(audio),'-map','0:v','-map','1:a',
        '-c:v','libx264','-preset','fast','-crf','19','-threads','2','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','192k','-movflags','+faststart','-t',str(length),str(output)],stdin=subprocess.PIPE, start_new_session=True)
    children.update([decoder,encoder])
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',tokens['caption_font_size'])
    headfont=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',tokens['headline_font_size'])
    logo=None
    logo_path=job/'logo.png'
    if logo_path.exists():
        logo=Image.open(logo_path).convert('RGBA'); logo.thumbnail((tokens['logo_max_width'],tokens['logo_max_height']))
    current=None; overlay=None
    try:
        for index in range(math.ceil(length*fps)):
            raw=bytearray()
            while len(raw)<w*h*3:
                piece=decoder.stdout.read(w*h*3-len(raw))
                if not piece: break
                raw.extend(piece)
            if len(raw)!=w*h*3: raise RuntimeError('Видеоряд короче аудио')
            t=index/fps
            text=next((c['text'] for c in captions if c['start']<=t<c['end']), '')
            key=(text, t<3)
            if current != key or overlay is None:
                current=key; overlay=Image.new('RGBA',(w,h)); draw=ImageDraw.Draw(overlay)
                if logo: overlay.alpha_composite(logo,(safe_x,safe_top))
                if headline and t<3:
                    head_lines=wrap_pixels(headline,headfont,w-2*safe_x-32)
                    hy=safe_top+tokens['logo_max_height']+28
                    draw.rounded_rectangle((safe_x,hy,w-safe_x,hy+len(head_lines)*50+32),18,fill=panel_color)
                    for n,line in enumerate(head_lines): draw.text((safe_x+16,hy+16+n*50),line,font=headfont,fill=theme['accent'])
                lines=wrap_pixels(text,font,w-2*safe_x-36)
                boxheight=len(lines)*tokens['caption_line_height']+2*tokens['caption_padding']
                if lines:
                    y=h-tokens['safe_bottom']-boxheight
                    draw.rounded_rectangle((safe_x,y,w-safe_x,y+boxheight),tokens['caption_radius'],fill=panel_color)
                    draw.rounded_rectangle((safe_x,y,safe_x+5,y+boxheight),2,fill=theme['accent'])
                    for n,line in enumerate(lines):
                        draw.text(((w-font.getlength(line))/2,y+tokens['caption_padding']+n*tokens['caption_line_height']),line,font=font,fill=theme['text'])
            im=Image.frombytes('RGB',(w,h),bytes(raw)).convert('RGBA')
            im.alpha_composite(overlay)
            progress=ImageDraw.Draw(im)
            progress.rectangle((safe_x,h-180,w-safe_x,h-177),fill=panel_color)
            progress.rectangle((safe_x,h-180,safe_x+(w-2*safe_x)*min(1,t/length),h-177),fill=theme['accent'])
            encoder.stdin.write(im.convert('RGB').tobytes())
            if index%120==0:
                metrics=json.loads(subprocess.check_output(['macmon','pipe','-s','1','-i','500'],text=True))
                print(f'EXPORT {index}/{math.ceil(length*fps)} CPU {metrics["temp"]["cpu_temp_avg"]}',flush=True)
                while max(metrics['temp']['cpu_temp_avg'],metrics['temp']['gpu_temp_avg'])>=65:
                    time.sleep(3)
                    metrics=json.loads(subprocess.check_output(['macmon','pipe','-s','1','-i','500'],text=True))
        encoder.stdin.close()
        decoder.stdout.close()
        if decoder.wait(): raise RuntimeError('Ошибка декодирования исходного видео')
        if encoder.wait(): raise RuntimeError('Ошибка экспорта FFmpeg')
    finally:
        for p in [decoder,encoder]:
            if p.poll() is None: p.terminate(); p.wait()
            children.discard(p)

class UploadFailure(RuntimeError): pass


def delivery(job, config, output, report):
    title=re.sub(r'[^\w -]+','',config.get('title') or config.get('design',{}).get('headline') or 'avatar',flags=re.UNICODE).strip()[:60] or 'avatar'
    folder=ROOT/'videos/exports'/f'{title}-{job.name}'
    folder.mkdir(parents=True,exist_ok=True)
    result=folder/output.name
    for source in [output,output.with_suffix('.srt')]:
        if source.exists():shutil.copy2(source,folder/source.name)
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if config.get('scenario_plan'):
        (folder/'scenario.json').write_text(json.dumps(config['scenario_plan'],ensure_ascii=False,indent=2))
    page=ROOT/'projects'/folder.name
    page.mkdir(parents=True,exist_ok=True)
    base='../../videos/exports/'+folder.name+'/'
    (page/'README.md').write_text('# '+title+'\n\n'
        +'[Результат](<'+base+output.name+'>) · [Проверки](<'+base+'report.json>)\n\n'
        +'[Сценарий и план](<'+base+'scenario.json>)\n\n'
        +'[Код](../../mac-app/engine/pipeline.py) · [Рабочие материалы](../../mac-app/jobs/'+job.name+'/)\n\n'
        +'Проверка лица, артикуляции и монтажа человеком: ожидается.\n')
    (job/'delivery.json').write_text(json.dumps(dict(folder=str(folder),output=str(result)),ensure_ascii=False,indent=2))
    receipt=None
    if config.get('upload_destination'):
        status(job,'upload','Загрузка результата в Google Drive',output=str(result))
        try:
            from drive_upload import upload
            receipt=upload(folder,config['upload_destination'],run)
        except Exception as exc:raise UploadFailure('Видео/голос сохранены локально, но загрузка не завершена: '+str(exc)) from exc
        (job/'upload.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    message='Голос готов' if config.get('voice_only') else 'Видео готово'
    if receipt:message+=' · Google Drive: '+receipt['destination']
    status(job,'done',message,output=str(result))


def main(config_path):
    config_path=Path(config_path).resolve()
    config=json.loads(config_path.read_text()); job=config_path.parent
    if job.parent != (ROOT/'mac-app/jobs').resolve():raise ValueError('Папка задания должна находиться в mac-app/jobs')
    lock = open(ROOT/'mac-app/jobs/engine.lock', 'a')
    awake = None
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Уже запущена другая генерация. Дождись её завершения.')
        awake = subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
        status(job,'validation','Проверка файлов и зависимостей')
        if config.get('upload_destination'):
            from drive_upload import preflight
            preflight(config['upload_destination'])
        from scenario import prepare
        if not config.get('scenario_plan'):
            config['scenario_plan']=prepare(config['script'],config.get('design',{}).get('headline',''))
            config['script']=config['scenario_plan']['speech']
        dependencies(voice_only=config.get('voice_only', False)); sentences=validate(config)
        config.update(project=str(ROOT),job=str(job),sentences=sentences,engine={
            'version':VERSION, 'voice_engine':'espeech', 'voice_speed':1.0,
            'git_commit':revision(),
            'source_sha256':{name:sha(HERE/name) for name in ['pipeline.py','voice.py','voice-settings.json','phonetics.py','hero_check.py','pronunciation.py','pronunciation-overrides.json','scenario.py','storyboard.py','drive_upload.py']}})
        # Snapshot source files so later edits cannot change an in-flight job.
        from PIL import Image, ImageOps
        photo=job/'portrait.png'
        with Image.open(config['photo']) as im:
            ImageOps.exif_transpose(im).convert('RGB').save(photo)
        if config.get('logo'):
            with Image.open(config['logo']) as im: im.convert('RGBA').save(job/'logo.png')
        run(['ffmpeg','-y','-v','error','-i',config['reference_audio'],'-ar','24000','-ac','1',job/'reference.wav'],start_new_session=True)
        shutil.copy2(HERE.parent/'design-system.json', job/'design-system.json')
        (job/'resolved.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
        status(job,'voice','Синтез голоса. Охлаждение может занимать время.')
        run([ROOT/'local-avatar/.venv-tts-compare/bin/python',HERE/'voice.py',job/'resolved.json'],start_new_session=True)
        import soundfile as sf
        import numpy as np
        sys.path.insert(0,str(ROOT/'local-avatar/reels'))
        from timing import build_timeline, pauses, shorten_long_pauses
        chunks=[]; sr=None; pause_edits=[]
        for i,text in enumerate(sentences):
            y,rate=sf.read(job/f'voice-{i:03}.wav')
            if y.ndim>1:y=y.mean(axis=1)
            if sr is not None and sr!=rate:raise ValueError('Разные частоты аудиореплик')
            sr=rate
            hop=max(1,round(sr*.01))
            active=[j for j in range(0,len(y),hop) if np.sqrt(np.mean(y[j:j+hop]**2))>10**(-35/20)]
            if not active:raise ValueError('Не обнаружена речь в реплике')
            y=y[max(0,active[0]-round(sr*.08)):min(len(y),active[-1]+hop+round(sr*.08))]
            y,edits=shorten_long_pauses(y,sr)
            pause_edits.extend(dict(utterance=i,**edit) for edit in edits)
            chunks.append(y)
        waveform,spans,timing=build_timeline(chunks,sr)
        captions=[dict(start=a,end=b,text=text) for (a,b),text in zip(spans,sentences)]
        cursor=len(waveform)/sr
        audit=pauses(waveform,sr,min_duration=.85)
        (job/'timing-check.json').write_text(json.dumps(dict(**timing,pauses=audit,pause_edits=pause_edits,
            pause_edit_coordinates='seconds within edge-trimmed source utterance',
            source_audio='voice-NNN.wav files preserved; speech speed unchanged'),ensure_ascii=False,indent=2))
        if audit:raise ValueError('В речи есть паузы от 0.85 с. Проверьте timing-check.json до генерации аватара.')
        if cursor>90:raise ValueError('Озвучка длиннее 90 секунд. Сократите текст; голос не ускоряется.')
        audio=job/'speech.wav'; sf.write(audio,waveform,sr)
        plan=config['scenario_plan']
        from scenario import actual_timeline
        scenes=actual_timeline(plan,captions,cursor)
        warnings=list(plan['warnings'])
        requested=plan.get('requested_duration')
        if requested and not requested[0]<=cursor<=requested[1]:warnings.append(f'Фактическая речь {cursor:.2f} с; запрос {requested[0]}–{requested[1]} с. Пустые интервалы не добавлены.')
        (job/'timeline.json').write_text(json.dumps(dict(scenes=scenes,captions=captions,duration=cursor,warnings=warnings),ensure_ascii=False,indent=2))
        report=dict(duration=cursor,timing=timing,pauses=audit,pause_edits=pause_edits,warnings=warnings,
                    human_review='pending: voice likeness, lips, face and final edit must be reviewed',
                    caption_alignment='approximate within each spoken sentence; not ASR word alignment',
                    engine=config['engine'],timing_module_sha256=sha(Path(sys.modules['timing'].__file__)))
        if config.get('voice_only'):
            report['audio_probe']=probe(audio);delivery(job,config,audio,report);return
        shots=[]
        for scene in scenes:
            start=scene['start']; number=0
            while start<scene['end']-1e-6:
                kind=scene['kind']
                if kind=='hero' and scene['style']=='checklist' and number>0:kind='graphic'
                end=min(scene['end'],start+(3 if kind=='hero' else 4))
                shot=dict(start=start,end=end,scene_id=scene['id'],kind=kind)
                if kind=='hero':
                    i=len(shots)
                    status(job,'video',f'Герой: сцена {scene["id"]}, план {number+1}. Дождитесь генерации/охлаждения.')
                    part=job/f'part-{i:03}.wav'
                    run(['ffmpeg','-y','-v','error','-ss',str(start),'-i',audio,'-af','apad','-t','3.3',part],start_new_session=True)
                    clip=job/f'clip-{i:03}.mp4'
                    spoken=' '.join(c['text'] for c in captions if c['start']<end and c['end']>start)
                    prompt=('A realistic continuous medium shot of the same person seated at a desk. '
                        'Preserve the reference identity, clothes, background, lighting and natural face. '
                        'Keep upper body, tabletop, coffee mug and part of laptop visible. No face zoom or tight crop. '
                        'Direct eye contact, subtle head movement and natural blinking. '
                        f'Actively speaking Russian with synchronized lip and jaw articulation: {spoken}. Stable camera.')
                    env=os.environ.copy();env.update(HF_HUB_OFFLINE='1',LTX2_VAE_DECODE_BUDGET_GB='4',PYTHONUNBUFFERED='1')
                    from hero_check import check_clip
                    attempts=[]
                    for attempt in range(2):
                        clip=job/f'clip-{i:03}-take-{attempt+1}.mp4'
                        seed=42+i+1000*attempt
                        run([ROOT/'local-avatar/ltx-2-mlx/.venv/bin/python',ROOT/'local-avatar/ltx/cooled_cli.py',
                            'a2v','--distilled','--model',ROOT/'local-avatar/models/ltx-2.3-mlx-q4',
                            '--gemma',ROOT/'local-avatar/models/gemma-3-12b-it-4bit','--prompt',prompt,
                            '--audio',part,'--image',photo,'--width','512','--height','896','--frames','73',
                            '--frame-rate','24','--seed',str(seed),'--low-ram','--output',clip],env=env,start_new_session=True)
                        check=check_clip(clip,end-start)
                        attempts.append(dict(clip=str(clip),seed=seed,**check))
                        (job/f'hero-check-{i:03}.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2))
                        if check['passed']:break
                        status(job,'video',f'План {i}: слабое движение губ или не найдено лицо; дубль {attempt+1} отклонён.')
                    else:
                        raise ValueError(f'План {i}: оба дубля героя не прошли проверку движения губ. См. hero-check-{i:03}.json. Нужен новый дубль; монтаж остановлен.')
                    shot['clip']=str(clip)
                    shot['mouth_motion_check']=check
                shots.append(shot);start=end;number+=1
        (job/'shots.json').write_text(json.dumps(shots,ensure_ascii=False,indent=2))
        status(job,'export','Монтаж сцен, анимированная графика и субтитры')
        output=job/'Готовое видео.mp4'
        import storyboard
        caps=storyboard.render(shots,scenes,audio,captions,output,job,sys.modules[__name__],config.get('design'))
        status(job,'verification','Полный декод и проверка MP4')
        run(['ffmpeg','-v','error','-xerror','-i',output,'-f','null','-'],start_new_session=True)
        details=probe(output)
        video=next(s for s in details['streams'] if s['codec_type']=='video')
        if (video['width'],video['height'])!=(720,1280) or not any(s['codec_type']=='audio' for s in details['streams']):raise ValueError('Ошибка геометрии или отсутствует звук')
        if abs(float(details['format']['duration'])-cursor)>.15:raise ValueError('Не совпала длительность экспорта')
        report.update(full_decode='passed',probe=details,sha256=sha(output),captions=caps)
        (job/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        delivery(job,config,output,report)
    except BaseException as exc:
        if isinstance(exc, SystemExit) and exc.code == 130:
            status(job,'cancelled','Генерация остановлена. Промежуточные файлы сохранены.')
        else:
            details={}
            if (job/'delivery.json').exists():details=json.loads((job/'delivery.json').read_text())
            status(job,'upload_error' if isinstance(exc,UploadFailure) else 'error',str(exc),**details)
        raise
    finally:
        if awake is not None:
            awake.terminate(); awake.wait()
        lock.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('config',type=Path); args=parser.parse_args()
    main(args.config)
