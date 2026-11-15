"""STT 보정 체인 테스트. 예시는 2026-11-15 e2e(세션 241)에서 EXAONE이 실제로 낸 보정문이다."""

import json

from langchain_core.messages import AIMessage

from app.chains.stt_correction import correct_transcript


class FakeLlm:
    def __init__(self, corrected):
        self.corrected = corrected

    def invoke(self, messages):
        return AIMessage(content=json.dumps({"corrected": self.corrected}, ensure_ascii=False))


def _segments(*raws):
    return [{"time_offset_sec": i * 5, "raw_text": r} for i, r in enumerate(raws)]


def test_word_fixes_are_kept():
    raws = ["음, AP 응답을 캐시로 줄였습니다.", "권한이 필요한 문서는 아예 챗봇에 넣지 않고 공개 문서만 새긴 하겠습니다."]
    fixed = ["음, API 응답을 캐시로 줄였습니다.", "권한이 필요한 문서는 아예 챗봇에 넣지 않고 공개 문서만 색인하겠습니다."]
    out = correct_transcript(FakeLlm(fixed), "질문", _segments(*raws))
    assert [s["corrected_text"] for s in out] == fixed


def test_rewritten_segment_falls_back_to_raw_text():
    """뜻을 뒤집은 보정은 버리고 원문을 쓴다. 다른 구간의 바른 보정은 남긴다."""
    raws = ["벡터 검색만으로 충분해서 키워드 검색은 쓰지 않겠습니다.", "음, AP 응답을 캐시로 줄였습니다."]
    llm = FakeLlm(["벡터 검색만으로 충분하다고 생각하지만, 키워드 검색을 함께 사용함으로써 더 정확하고 빠른 정보 검색이 가능해집니다.",
                   "음, API 응답을 캐시로 줄였습니다."])
    out = correct_transcript(llm, "질문", _segments(*raws))
    assert [s["corrected_text"] for s in out] == [raws[0], "음, API 응답을 캐시로 줄였습니다."]
    assert out[0]["time_offset_sec"] == 0 and out[1]["time_offset_sec"] == 5
