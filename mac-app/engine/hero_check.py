"""Reject obviously closed mouths; this heuristic does not certify lip sync."""
import numpy as np


def assess(ratios, frames):
    coverage=len(ratios)/max(1,frames)
    low,high=np.percentile(ratios,[10,90]) if ratios else (0,0)
    passed=coverage>=.8 and high>=.025 and high-low>=.015
    return dict(passed=bool(passed),face_coverage=coverage,frames=frames,
                mouth_open_p10=float(low),mouth_open_p90=float(high),
                method='inner lip gap / mouth width; project heuristic',
                limits='Motion only; human review required for synchronization and identity')


def assess_head(samples):
    """Project-specific framing guard, not a biomechanical naturalness score."""
    if not samples:return dict(passed=False,reason='no head landmarks')
    yaw=np.array([sample['yaw'] for sample in samples])
    widths=np.array([sample['width'] for sample in samples])
    steps=[abs(b['yaw']-a['yaw']) for a,b in zip(samples,samples[1:])
           if b['frame']==a['frame']+1]
    step=max(steps,default=0)
    excursion=float(np.max(np.abs(yaw-yaw[0])))
    scale=float(np.max(widths)/np.min(widths))
    return dict(passed=bool(step<=.12 and excursion<=.18 and scale<=1.18),
                max_yaw_proxy_step=float(step),max_yaw_proxy_excursion=excursion,
                face_width_ratio=scale,
                thresholds=dict(step=.12,excursion=.18,face_width_ratio=1.18),
                limits='2D landmark heuristic for frontal desk shots; not degrees or proof of natural motion')


def check_clip(path, seconds):
    import cv2
    import mediapipe as mp
    capture=cv2.VideoCapture(str(path));ratios=[];frames=0;head=[]
    fps=capture.get(cv2.CAP_PROP_FPS)
    if fps<=0:raise ValueError('Не прочитана частота кадров героя')
    try:
        with mp.solutions.face_mesh.FaceMesh(max_num_faces=1,refine_landmarks=True) as mesh:
            while frames/fps<seconds:
                ok,frame=capture.read()
                if not ok:break
                frames+=1
                result=mesh.process(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                if not result.multi_face_landmarks:continue
                landmarks=result.multi_face_landmarks[0].landmark
                h,w=frame.shape[:2]
                point=lambda i:np.array([landmarks[i].x*w,landmarks[i].y*h])
                width=np.linalg.norm(point(61)-point(291))
                if width>0:ratios.append(float(np.linalg.norm(point(13)-point(14))/width))
                face_width=landmarks[454].x-landmarks[234].x
                if face_width>0:
                    head.append(dict(frame=frames,width=face_width,
                        yaw=(landmarks[1].x-(landmarks[234].x+landmarks[454].x)/2)/face_width))
        report=assess(ratios,frames)
        report['mouth_passed']=report['passed']
        report['head_motion']=assess_head(head)
        report['passed']=report['passed'] and report['head_motion']['passed']
        if frames/fps+1/fps<seconds:report['passed']=False
        return report
    finally:capture.release()
