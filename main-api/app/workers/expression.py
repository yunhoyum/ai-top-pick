"""프레임별 감정 → 주요 표정·감정별 프레임 비율 (Celery 7장).

ai-service app/analysis/expression.py의 summarize_expression과 규칙이 같아야 한다. 한쪽을 고치면 다른 쪽도 고친다.
"""

EMOTIONS = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")


def summarize_expression(frames: list[dict]) -> tuple[str | None, dict[str, float] | None]:
    """얼굴을 찾은 프레임이 없으면 (None, None). 주요 표정은 비율이 가장 큰 감정이다 (제안)."""
    if not frames:
        return None, None
    counts = {e: 0 for e in EMOTIONS}
    for f in frames:
        counts[f["emotion"]] += 1
    ratio = {e: round(n / len(frames), 4) for e, n in counts.items()}
    return max(EMOTIONS, key=lambda e: counts[e]), ratio
