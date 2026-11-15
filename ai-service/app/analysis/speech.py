"""발화 수치 (ai-service 6장, SYS-007). 간투사·침묵·응답 지연과 STT 구간 나누기.

단어 시각은 STT 스트림 기준 초다. 답변 시간 시작(생각 시간 종료)도 같은 기준이다 (내부 API 규약 2.3).
"""

import math
import re
from decimal import Decimal

from app.schemas.internal import Word

_EDGE_PUNCT = re.compile(r"^[^\w]+|[^\w]+$")
_SENTENCE_END = re.compile(r"[.?!]$")
SEGMENT_GAP_SEC = 1.5  # 이만큼 말이 끊기면 다른 구간으로 본다 (SYS-004 '한 문장을 다 말한 후 1.5초', 제안)


def _token(word: str) -> str:
    return _EDGE_PUNCT.sub("", word)


def count_fillers(raw_text: str, fillers: list[str]) -> int:
    """보정 전 원문에서 간투사('아', '음' 등)를 센다. 앞뒤 문장부호를 떼고 낱말이 통째로 같은 것만 센다.
    '그 결과'의 '그'처럼 뜻이 있는 낱말과 겹치는 것은 목록에 넣지 않는다 (설정값)."""
    targets = set(fillers)
    return sum(1 for w in raw_text.split() if _token(w) in targets)


def calc_silence(words: list[Word], min_gap: float = 3.0) -> float:
    """단어 사이 min_gap초 이상 빈 구간만 더한다. 첫 단어 이전과 마지막 단어 이후(종료를 판정한 무발화)는 뺀다."""
    return round(sum(gap for a, b in zip(words, words[1:]) if (gap := b.start - a.end) >= min_gap), 2)


def calc_response_delay(answer_start_sec: float, words: list[Word]) -> float:
    """답변 시간 시작과 첫 단어 시작의 차이. 말을 하지 않았으면 0이다 (첫 단어가 없으면 발화 점수 0, 루브릭 4.2)."""
    return round(max(0.0, words[0].start - answer_start_sec), 2) if words else 0.0


def answer_duration(answer_start_sec: float, words: list[Word]) -> int:
    """답변 길이(초). 답변 시작부터 마지막 단어 끝까지. 말을 하지 않았으면 0."""
    return math.ceil(max(0.0, words[-1].end - answer_start_sec)) if words else 0


def split_segments(words: list[Word], answer_start_sec: float = 0.0) -> list[dict]:
    """STT 원문을 구간으로 나눈다 → stt_record. 문장 끝(. ? !)이나 SEGMENT_GAP_SEC 이상 끊긴 곳에서 나눈다.
    time_offset_sec는 답변 시작 기준 구간 시작 시각(초, 버림)이다."""
    segments: list[dict] = []
    current: list[Word] = []
    for w in words:
        if current and w.start - current[-1].end >= SEGMENT_GAP_SEC:
            segments.append(current)
            current = []
        current.append(w)
        if _SENTENCE_END.search(w.word):
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return [
        {"time_offset_sec": int(max(0.0, seg[0].start - answer_start_sec)), "raw_text": " ".join(w.word for w in seg)}
        for seg in segments
    ]


def calc_speech_score(filler_count: int, silence_sec: float, response_delay_sec: float, has_words: bool) -> Decimal:
    """100에서 간투사 1회당 3, 침묵 3초(버림)당 5, 응답 지연 10초 이상이면 10을 뺀다. 최저 0.
    첫 단어가 없으면 0점이다. 말을 하지 않아 감점할 값이 없어 100점이 되는 것을 막는다 (루브릭 설계서 4.2)."""
    if not has_words:
        return Decimal("0.00")
    score = 100 - 3 * filler_count - 5 * math.floor(silence_sec / 3) - (10 if response_delay_sec >= 10 else 0)
    return Decimal(max(0, score)).quantize(Decimal("0.01"))
