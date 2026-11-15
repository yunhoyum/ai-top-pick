"""표정 요약과 표정 점수 (ai-service 6장, 루브릭 설계서 5장).

main-api worker의 workers/expression.py와 요약 규칙이 같아야 한다. 한쪽을 고치면 다른 쪽도 고친다.
"""

from decimal import ROUND_HALF_UP, Decimal

EMOTIONS = ("angry", "disgust", "fear", "happy", "sad", "surprise", "neutral")
POSITIVE = ("happy", "neutral")  # 긍정·중립 (P)
NEGATIVE = ("angry", "disgust", "fear", "sad")  # 부정 (N). surprise는 뺀다


def summarize_expression(frames: list[dict]) -> tuple[str | None, dict[str, float] | None]:
    """프레임별 감정 → (주요 표정, 감정별 프레임 비율). 얼굴을 찾은 프레임이 없으면 (None, None).
    비율은 그 감정으로 분류된 프레임 수 ÷ 전체 프레임 수다. 주요 표정은 비율이 가장 큰 감정이다 (제안)."""
    if not frames:
        return None, None
    counts = {e: 0 for e in EMOTIONS}
    for f in frames:
        counts[f["emotion"]] += 1
    ratio = {e: round(n / len(frames), 4) for e, n in counts.items()}
    return max(EMOTIONS, key=lambda e: counts[e]), ratio


def calc_expression_score(ratio: dict[str, float]) -> Decimal:
    """50 + (P − N) × 50 → 0~100 (루브릭 설계서 5.3)."""
    p = sum(ratio.get(e, 0.0) for e in POSITIVE)
    n = sum(ratio.get(e, 0.0) for e in NEGATIVE)
    return (Decimal(50) + (Decimal(str(p)) - Decimal(str(n))) * 50).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
