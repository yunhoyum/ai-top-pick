"""STT 보정 체인 (ai-service 4장 correct_transcript, SYS-004, AI Agent 설계서 T-31).

인식 원문 구간 → 보정 구간. 구간 시점은 유지한다.
끝까지 실패하거나 구간 수가 다르면 원문을 보정 텍스트로 쓴다. 답변 평가를 멈추지 않기 위해서다.

보정은 잘못 받아 적은 낱말만 고쳐야 한다. EXAONE은 '내용을 바꾸지 않는다'는 지시를 어기고 답변을 다시 쓰거나
뜻을 뒤집었다 (2026-11-15 e2e 세션 241: '키워드 검색은 쓰지 않겠다' → '함께 쓰면 더 정확하다').
그래서 구간마다 원문과 보정문의 글자 유사도를 보고, STT_MIN_SIMILARITY보다 낮으면 그 구간은 원문을 쓴다.
잰 값: 바른 보정('AP'→'API', '새긴'→'색인') 0.95 이상, 다시 쓴 보정 0.35~0.75.
"""

import logging
from difflib import SequenceMatcher

from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.chains.structured import invoke_structured
from app.core.config import get_settings
from app.prompts import stt_correction as prompts

log = logging.getLogger(__name__)


class CorrectionOutput(BaseModel):
    corrected: list[str]


def correct_transcript(model: Runnable, question: str, segments: list[dict]) -> list[dict]:
    """segments: [{time_offset_sec, raw_text}] → [{time_offset_sec, raw_text, corrected_text}]."""
    if not segments:
        return []
    raws = [s["raw_text"] for s in segments]
    corrected = raws
    try:
        out = invoke_structured(model, prompts.correct_transcript(question, raws), CorrectionOutput).corrected
        if len(out) == len(raws) and all(c.strip() for c in out):
            corrected = [_keep_if_close(r, c.strip()) for r, c in zip(raws, out)]
        else:
            log.warning("STT 보정 구간 수가 다르거나 빈 구간이 있어 원문을 쓴다 (%d → %d)", len(raws), len(out))
    except Exception as e:
        log.warning("STT 보정 실패, 원문을 쓴다: %s", e)
    return [s | {"corrected_text": c} for s, c in zip(segments, corrected)]


def _keep_if_close(raw: str, corrected: str) -> str:
    """보정문이 원문과 많이 다르면(다시 쓴 것) 원문을 쓴다."""
    similarity = SequenceMatcher(None, raw, corrected).ratio()
    if similarity < get_settings().STT_MIN_SIMILARITY:
        log.warning("STT 보정이 원문과 많이 달라(유사도 %.2f) 원문을 쓴다: %r → %r", similarity, raw, corrected)
        return raw
    return corrected
