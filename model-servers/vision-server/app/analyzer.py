import threading

import numpy as np
from deepface import DeepFace

from .schemas import EMOTIONS, FrameEmotion

# DeepFace(TensorFlow)의 동시 호출 안전성이 확인되지 않아 한 번에 하나만 실행한다
_lock = threading.Lock()


def load() -> None:
    """감정 모델을 명시적으로 올리고(가중치가 없으면 여기서 받는다) 예열한다."""
    DeepFace.build_model(task="facial_attribute", model_name="Emotion")
    # 빈 이미지는 얼굴이 없으므로 None 이 나오는 게 정상이다 (검출기 로드까지 확인)
    analyze_frame(np.zeros((224, 224, 3), dtype=np.uint8), 0.0)


def analyze_frame(image: np.ndarray, t: float) -> FrameEmotion | None:
    """프레임 1장의 감정을 분석한다. 얼굴이 없으면 None."""
    with _lock:
        try:
            results = DeepFace.analyze(
                image,
                actions=["emotion"],
                enforce_detection=True,  # False면 얼굴이 없어도 전체 이미지를 분석해 버린다
                silent=True,
            )
        except ValueError:
            return None  # 얼굴을 찾지 못함
    if isinstance(results, dict):
        results = [results]
    if not results:
        return None
    # 얼굴이 여러 개면 가장 큰 얼굴을 쓴다
    face = max(results, key=lambda r: r["region"]["w"] * r["region"]["h"])
    raw = face["emotion"]  # DeepFace는 0~100 비율로 준다
    total = sum(float(raw[e]) for e in EMOTIONS) or 1.0
    scores = {e: round(float(raw[e]) / total, 4) for e in EMOTIONS}
    return FrameEmotion(t=t, emotion=max(scores, key=scores.get), scores=scores)


def analyze_video(path, interval_sec: float) -> tuple[list[FrameEmotion], int]:
    from .frames import sample_frames

    frames: list[FrameEmotion] = []
    skipped = 0
    for t, image in sample_frames(path, interval_sec):
        result = analyze_frame(image, t)
        if result is None:
            skipped += 1
        else:
            frames.append(result)
    return frames, skipped
