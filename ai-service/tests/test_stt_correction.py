"""STT 보정 체인 테스트. 예시는 2026-11-15 e2e(세션 241)와 통합테스트 IT-INTV-001(2026-11-17)에서 EXAONE이 실제로 낸 보정이다.

v2: LLM은 고칠 낱말 짝(fixes)만 내고 코드가 원문에 적용한다. 원문에 없는 낱말, 낱말을 다른 말로 바꿔 쓴 짝은 버린다.
"""

import json

from langchain_core.messages import AIMessage

from app.chains.stt_correction import correct_transcript


class FakeLlm:
    def __init__(self, fixes):
        self.fixes = fixes
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=json.dumps({"fixes": self.fixes}, ensure_ascii=False))


def _segments(*raws):
    return [{"time_offset_sec": i * 5, "raw_text": r} for i, r in enumerate(raws)]


def _fix(segment, wrong, right):
    return {"segment": segment, "wrong": wrong, "right": right}


def _corrected(fixes, *raws):
    return [s["corrected_text"] for s in correct_transcript(FakeLlm(fixes), "질문", _segments(*raws))]


def test_word_fixes_are_applied_to_their_segment():
    raws = ["음, AP 응답을 캐시로 줄였습니다.", "권한이 필요한 문서는 공개 문서만 새긴 하겠습니다."]
    out = _corrected([_fix(1, "AP 응답", "API 응답"), _fix(2, "새긴 하겠습니다", "색인하겠습니다")], *raws)
    assert out == ["음, API 응답을 캐시로 줄였습니다.", "권한이 필요한 문서는 공개 문서만 색인하겠습니다."]


def test_terms_and_numbers_are_fixed_and_time_offsets_stay():
    raws = ["알림 발송을 샐러리 작업으로 바꿔서 일 조 주셨습니다.", "N 플러스 일 문제."]
    fixes = [_fix(1, "샐러리", "Celery"), _fix(1, "일 조 주셨습니다", "1초로 줄였습니다"), _fix(2, "N 플러스 일", "N+1")]
    out = correct_transcript(FakeLlm(fixes), "질문", _segments(*raws))
    assert [s["corrected_text"] for s in out] == ["알림 발송을 Celery 작업으로 바꿔서 1초로 줄였습니다.", "N+1 문제."]
    assert [s["time_offset_sec"] for s in out] == [0, 5]


def test_rewriting_a_segment_into_an_answer_is_rejected():
    """통합테스트: '안녕하세요.'를 Redis 재시도 모범 답변으로, '몰라요.'를 '잘 모르겠습니다.'로 바꿔 썼다."""
    raws = ["안녕하세요.", "몰라요.", "한"]
    fixes = [_fix(1, "안녕하세요.", "Redis 캐시를 활용해 재시도 횟수를 저장하고 지수 백오프로 재시도합니다."),
             _fix(2, "몰라요.", "잘 모르겠습니다."),
             _fix(3, "한", "한 구간만 제공되었으나 답변을 이어 주세요.")]
    assert _corrected(fixes, *raws) == raws


def test_number_fix_must_keep_the_spoken_number():
    """실험 T1: '십 초'를 '1초'로 고쳤다. 바른 말의 숫자는 틀린 말의 한글 숫자와 같아야 한다."""
    raws = ["응답이 십 초 걸렸습니다.", "응답을 일 조 아래로 줄였습니다.", "삼백 밀리초였습니다."]
    fixes = [_fix(1, "십 초", "1초"), _fix(2, "일 조", "1초"), _fix(3, "삼백 밀리초", "300밀리초")]
    assert _corrected(fixes, *raws) == ["응답이 십 초 걸렸습니다.", "응답을 1초 아래로 줄였습니다.", "300밀리초였습니다."]
    assert _corrected([_fix(1, "십 초", "10초")], raws[0]) == ["응답이 10초 걸렸습니다."]


def test_fix_whose_wrong_text_is_not_in_the_segment_is_ignored():
    # 구간 번호가 틀렸거나 원문에 없는 낱말이다. 다른 바른 짝은 적용한다
    raws = ["음, AP 응답을 캐시로 줄였습니다.", "벡터 검색만으로 충분해서 키워드 검색은 쓰지 않겠습니다."]
    fixes = [_fix(2, "AP 응답", "API 응답"), _fix(9, "AP", "API"), _fix(2, "쓰지 않겠습니다", "함께 쓰겠습니다"),
             _fix(1, "AP 응답", "API 응답")]
    assert _corrected(fixes, *raws) == ["음, API 응답을 캐시로 줄였습니다.", raws[1]]


def test_llm_failure_keeps_raw_text():
    class Broken:
        def invoke(self, messages):
            return AIMessage(content="JSON이 아님")

    raws = ["음, AP 응답을 캐시로 줄였습니다."]
    out = correct_transcript(Broken(), "질문", _segments(*raws))
    assert [s["corrected_text"] for s in out] == raws


def test_no_segments_needs_no_call():
    llm = FakeLlm([])
    assert correct_transcript(llm, "질문", []) == [] and llm.calls == []
