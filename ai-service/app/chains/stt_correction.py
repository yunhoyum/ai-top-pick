"""STT 보정 체인 (ai-service 4장 correct_transcript, SYS-004, AI Agent 설계서 T-31).

인식 원문 구간 → 보정 구간. 구간 시점은 유지한다.
끝까지 실패할 때의 처리는 설계서에 '미정'이다. 여기서는 원문을 보정 텍스트로 쓴다 (제안). 답변 평가를 멈추지 않기 위해서다.
"""

import logging

from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.chains.structured import invoke_structured
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
            corrected = [c.strip() for c in out]
        else:
            log.warning("STT 보정 구간 수가 다르거나 빈 구간이 있어 원문을 쓴다 (%d → %d)", len(raws), len(out))
    except Exception as e:
        log.warning("STT 보정 실패, 원문을 쓴다: %s", e)
    return [s | {"corrected_text": c} for s, c in zip(segments, corrected)]
