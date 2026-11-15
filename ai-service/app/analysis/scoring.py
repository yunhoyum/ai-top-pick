"""답변 점수 합산 (ai-service 6장, 루브릭 설계서 6장, SYS-007)."""

from decimal import ROUND_HALF_UP, Decimal


def calc_answer_score(
    content: Decimal, expression: Decimal | None, speech: Decimal, ratios: dict[str, int]
) -> Decimal:
    """비율은 공고의 면접 평가 비율 {"내용", "언어", "비언어"}. 내용 비율은 내용, 언어는 발화, 비언어는 표정에 곱한다.
    표정이 없으면 내용·언어 비율을 합 100이 되게 늘린다. 예: 50·30 → 62.5·37.5."""
    c, s, e = (Decimal(ratios.get(k, 0)) for k in ("내용", "언어", "비언어"))
    if expression is None:
        score = (content * c + speech * s) / (c + s)
    else:
        score = (content * c + speech * s + expression * e) / 100
    return score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
