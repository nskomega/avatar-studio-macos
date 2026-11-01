"""Speech-first timing: refuse to fill a requested runtime with empty scene slots."""
import numpy as np

def build_timeline(chunks, sample_rate, target_seconds=None, max_gap=.12, max_tail=.85):
    if not chunks or any(len(y)==0 for y in chunks):raise ValueError('Нужны непустые реплики')
    total=sum(len(y) for y in chunks);count=len(chunks)
    target=round(target_seconds*sample_rate) if target_seconds is not None else total+round((max_gap*(count-1)+.15)*sample_rate)
    spare=target-total
    if spare<0:raise ValueError('Речь длиннее целевого ролика. Сократи сценарий; не ускоряй голос автоматически.')
    gap=min(round(max_gap*sample_rate),max(0,(spare-round(.02*sample_rate))//max(1,count-1)))
    tail=spare-gap*(count-1)
    if tail/sample_rate>max_tail:raise ValueError('Слишком короткая речь для заданной длительности. Сократи ролик или добавь полезную озвучку; пустые интервалы запрещены.')
    audio=np.zeros(target);spans=[];cursor=0
    for y in chunks:
        audio[cursor:cursor+len(y)]=y;spans.append((cursor/sample_rate,(cursor+len(y))/sample_rate));cursor+=len(y)+gap
    return audio,spans,dict(gap_seconds=gap/sample_rate,tail_seconds=tail/sample_rate,duration=target/sample_rate)

def pauses(audio,sample_rate,threshold_db=-35,min_duration=.55):
    hop=round(.01*sample_rate)
    flags=np.array([np.sqrt(np.mean(audio[i:i+hop]**2))<10**(threshold_db/20) for i in range(0,len(audio),hop)])
    edges=np.diff(np.r_[False,flags,False].astype(int));starts=np.flatnonzero(edges==1);ends=np.flatnonzero(edges==-1)
    return [dict(start=a*hop/sample_rate,end=min(b*hop,len(audio))/sample_rate,duration=(min(b*hop,len(audio))-a*hop)/sample_rate) for a,b in zip(starts,ends) if (min(b*hop,len(audio))-a*hop)/sample_rate>=min_duration]
