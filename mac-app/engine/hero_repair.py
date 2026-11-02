"""Bounded, cause-directed retries. Passing heuristics still requires human review."""
MAX_ATTEMPTS = 4


def failure_reasons(check):
    if check.get('passed'):
        return []
    reasons = []
    if check.get('face_coverage', 0) < .8:
        reasons.append('face_missing')
    if not check.get('mouth_passed', False):
        reasons.append('mouth_motion')
    head = check.get('head_motion', {})
    limits = head.get('thresholds', {})
    if head.get('face_width_ratio', 1) > limits.get('face_width_ratio', 1.18):
        reasons.append('face_scale')
    if (head.get('max_yaw_proxy_step', 0) > limits.get('step', .12)
            or head.get('max_yaw_proxy_excursion', 0) > limits.get('excursion', .18)):
        reasons.append('head_turn')
    if not reasons:
        reasons.append('incomplete_or_unmeasurable_clip')
    return reasons


LABELS = {
    'face_missing': 'лицо пропадает из кадра',
    'mouth_motion': 'недостаточная артикуляция',
    'face_scale': 'меняется масштаб лица',
    'head_turn': 'резкое движение или поворот головы',
    'incomplete_or_unmeasurable_clip': 'неполный клип или недостаточно данных проверки',
}


def repair_prompt(base, reasons):
    instructions = {
        'face_missing': 'Keep the entire face visible and unobstructed throughout every frame.',
        'mouth_motion': 'From the first frame, clearly articulate the supplied speech with visible lip opening and jaw motion. Keep hands away from the lips.',
        'face_scale': 'Locked tripod camera, fixed focal length and fixed subject distance. Maintain the exact initial medium framing throughout. Keep torso upright without leaning toward the lens. Table, mug and laptop remain visible.',
        'head_turn': 'Keep the head facing forward in a steady neutral pose throughout. Only lips and jaw move for speech; no head turns or sudden gestures.',
        'incomplete_or_unmeasurable_clip': 'Maintain a continuous unobstructed frontal shot for the entire supplied audio.',
    }
    return base + ' ' + ' '.join(instructions[key] for key in sorted(set(reasons)))
