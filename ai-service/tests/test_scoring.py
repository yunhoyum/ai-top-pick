"""발화·표정·답변 점수 테스트. 기대값은 루브릭 설계서 4.2, 5.3, 6장의 예시다."""

from decimal import Decimal

import pytest

from app.analysis.expression import calc_expression_score, summarize_expression
from app.analysis.scoring import calc_answer_score
from app.analysis.speech import calc_speech_score


@pytest.mark.parametrize("filler, silence, delay, expected", [
    (2, 7.0, 3.0, "84.00"),  # 예시 A: −6, −10
    (6, 0.0, 12.0, "72.00"),  # 예시 B: −18, −10
    (40, 0.0, 0.0, "0.00"),  # 최저 0
    (0, 2.9, 9.9, "100.00"),  # 3초 미만 침묵, 10초 미만 지연은 감점 없음
])
def test_speech_score(filler, silence, delay, expected):
    assert calc_speech_score(filler, silence, delay, has_words=True) == Decimal(expected)


def test_speech_score_without_words_is_zero():
    assert calc_speech_score(0, 0.0, 0.0, has_words=False) == Decimal("0.00")


@pytest.mark.parametrize("ratio, expected", [
    ({"neutral": 0.8, "happy": 0.1, "fear": 0.1}, "90.00"),
    ({"neutral": 0.5, "sad": 0.3, "fear": 0.2}, "50.00"),
    ({"fear": 0.7, "neutral": 0.3}, "30.00"),
    ({"surprise": 0.5, "neutral": 0.5}, "75.00"),  # surprise는 빼고 센다
])
def test_expression_score(ratio, expected):
    assert calc_expression_score(ratio) == Decimal(expected)


def test_summarize_expression_counts_frames():
    main, ratio = summarize_expression([{"emotion": "neutral"}] * 3 + [{"emotion": "sad"}])
    assert main == "neutral" and ratio["neutral"] == 0.75 and ratio["sad"] == 0.25 and sum(ratio.values()) == 1
    assert summarize_expression([]) == (None, None)


RATIOS = {"내용": 50, "언어": 30, "비언어": 20}


def test_answer_score_with_and_without_expression():
    assert calc_answer_score(Decimal(90), Decimal(80), Decimal(70), RATIOS) == Decimal("82.00")
    # 표정이 없으면 50·30 → 62.5·37.5
    assert calc_answer_score(Decimal(90), None, Decimal(70), RATIOS) == Decimal("82.50")
