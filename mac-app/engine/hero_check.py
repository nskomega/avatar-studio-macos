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


def check_clip(path, seconds):
    import cv2
    import mediapipe as mp
    capture=cv2.VideoCapture(str(path));ratios=[];frames=0
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
        report=assess(ratios,frames)
        if frames/fps+1/fps<seconds:report['passed']=False
        return report
    finally:capture.release()
