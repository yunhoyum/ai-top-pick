"""발화 수치 (ai-service 6장)."""

from app.analysis.speech import answer_duration, calc_response_delay, calc_silence, count_fillers, split_segments
from app.schemas.internal import Word


def _w(word, start, end):
    return Word(word=word, start=start, end=end)


def test_count_fillers_counts_whole_tokens_only():
    assert count_fillers("음, 저는 어 음음 그 결과 아. 음?", ["음", "어", "아"]) == 4  # '음음'은 세지 않는다


def test_silence_counts_only_gaps_between_words_of_three_seconds_or_more():
    words = [_w("a", 1, 2), _w("b", 4.9, 5), _w("c", 8, 9), _w("d", 9.5, 10)]
    assert calc_silence(words) == 3.0  # 2.9초 간격은 빼고, 첫 단어 앞과 끝 뒤는 세지 않는다
    assert calc_silence([]) == 0


def test_response_delay_and_duration():
    words = [_w("a", 3.5, 4), _w("b", 4.5, 7.2)]
    assert calc_response_delay(2.0, words) == 1.5 and answer_duration(2.0, words) == 6
    assert calc_response_delay(2.0, []) == 0.0 and answer_duration(2.0, []) == 0


def test_segments_split_at_sentence_end_or_long_pause():
    words = [_w("하나", 0, 1), _w("둘.", 1, 2), _w("셋", 2.2, 3), _w("넷", 5, 6)]
    assert split_segments(words, answer_start_sec=0.5) == [
        {"time_offset_sec": 0, "raw_text": "하나 둘."},
        {"time_offset_sec": 1, "raw_text": "셋"},
        {"time_offset_sec": 4, "raw_text": "넷"},  # 2초 끊김 → 다른 구간
    ]
