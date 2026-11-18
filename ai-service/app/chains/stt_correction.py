"""STT 보정 체인 (ai-service 4장 correct_transcript, SYS-004, AI Agent 설계서 T-31).

인식 원문 구간 → 보정 구간. 구간 시점은 유지한다. 끝까지 실패하면 원문을 보정 텍스트로 쓴다. 답변 평가를 멈추지 않기 위해서다.

보정은 잘못 받아 적은 낱말만 고쳐야 한다. EXAONE은 '내용을 바꾸지 않는다'는 지시를 어기고 답변을 다시 쓰거나
뜻을 뒤집었다 (2026-11-15 e2e 세션 241: '키워드 검색은 쓰지 않겠다' → '함께 쓰면 더 정확하다'). 통합테스트(2026-11-17)에서는
'안녕하세요.'를 모범 답변으로 바꿔 썼다. 그래서 LLM은 고칠 낱말 짝만 내고(프롬프트 v2), 코드가 아래를 지키는 짝만 적용한다.
- 틀린 말이 그 구간 원문에 그대로 있다. 길이는 MAX_WRONG_LEN 이하다
- 바른 말이 틀린 말보다 지나치게 길지 않다 (2배 + 4글자 이하). 답변을 덧붙이지 못하게 한다
- 바른 말에 영문·숫자가 없으면(한글끼리 고침) 자모 유사도가 MIN_JAMO_SIMILARITY 이상이다.
  소리가 비슷한 낱말을 고친 것만 남긴다. '몰라요' → '잘 모르겠습니다' 같은 바꿔 쓰기는 버린다
- 틀린 말의 부정어(않·안·못·없)를 바른 말에서 지우지 않는다. '쓰지 않겠습니다' → '함께 쓰겠습니다'는 자모 유사도가
  0.71이라 위 검사를 지난다
"""

import logging
from difflib import SequenceMatcher

from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.chains.structured import invoke_structured
from app.prompts import stt_correction as prompts

log = logging.getLogger(__name__)

MAX_WRONG_LEN = 20
MIN_JAMO_SIMILARITY = 0.5
NEGATIONS = ("않", "안 ", "못", "없")


class Fix(BaseModel):
    segment: int
    wrong: str
    right: str


class CorrectionOutput(BaseModel):
    fixes: list[Fix]


def correct_transcript(model: Runnable, question: str, segments: list[dict]) -> list[dict]:
    """segments: [{time_offset_sec, raw_text}] → [{time_offset_sec, raw_text, corrected_text}]."""
    if not segments:
        return []
    corrected = [s["raw_text"] for s in segments]
    try:
        fixes = invoke_structured(model, prompts.correct_transcript(question, corrected), CorrectionOutput).fixes
    except Exception as e:
        log.warning("STT 보정 실패, 원문을 쓴다: %s", e)
        fixes = []
    for fix in fixes:
        i, wrong, right = fix.segment - 1, fix.wrong.strip(), fix.right.strip()
        if 0 <= i < len(corrected) and _acceptable(corrected[i], wrong, right):
            corrected[i] = corrected[i].replace(wrong, right)
        else:
            log.warning("STT 보정 짝을 버린다: [%d] %r → %r", fix.segment, wrong, right)
    return [s | {"corrected_text": c} for s, c in zip(segments, corrected)]


def _acceptable(text: str, wrong: str, right: str) -> bool:
    if not wrong or not right or wrong == right or len(wrong) > MAX_WRONG_LEN or wrong not in text:
        return False
    if len(right) > len(wrong) * 2 + 4:
        return False
    if any(n in f"{wrong} " and n not in f"{right} " for n in NEGATIONS):
        return False
    if any(c.isascii() and c.isalnum() for c in right):
        return True  # 한글 소리로 적힌 용어·숫자를 영문·숫자로 고쳤다
    return SequenceMatcher(None, _jamo(wrong), _jamo(right)).ratio() >= MIN_JAMO_SIMILARITY


def _jamo(text: str) -> str:
    """한글 음절을 초성·중성·종성으로 나눈다. 띄어쓰기는 뺀다. 소리가 비슷한지 보기 위해서다."""
    out = []
    for ch in text.replace(" ", ""):
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out += [chr(0x1100 + code // 588), chr(0x1161 + code % 588 // 28)]
            if code % 28:
                out.append(chr(0x11A7 + code % 28))
        else:
            out.append(ch)
    return "".join(out)
