import os
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "/data/storage"))


class VideoPathError(ValueError):
    """루트 밖 경로 등 잘못된 경로"""


class VideoNotFound(FileNotFoundError):
    pass


class VideoUnreadable(RuntimeError):
    pass


def resolve_video(video_path: str) -> Path:
    """STORAGE_ROOT 기준 상대 경로를 실제 경로로 바꾼다. 루트 밖이면 거부한다."""
    root = STORAGE_ROOT.resolve()
    candidate = (root / video_path).resolve()  # ../ 와 심볼릭 링크를 풀어 준다
    if not candidate.is_relative_to(root):
        raise VideoPathError("STORAGE_ROOT 밖의 경로입니다")
    if not candidate.is_file():
        raise VideoNotFound(video_path)
    return candidate


def sample_frames(path: Path, interval_sec: float) -> Iterator[tuple[float, np.ndarray]]:
    """영상을 처음부터 읽으며 interval_sec 간격으로만 프레임을 돌려준다 (t, BGR 이미지).

    브라우저 녹화 webm은 길이·프레임 수 메타데이터가 없는 경우가 많아서
    프레임 번호로 건너뛰지 않고, 재생 시각(POS_MSEC)을 기준으로 순서대로 읽는다.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoUnreadable(f"영상을 열 수 없습니다: {path.name}")
    try:
        next_t = 0.0
        last_t = -1.0
        fallback_fps = cap.get(cv2.CAP_PROP_FPS)
        if not (1.0 <= fallback_fps <= 240.0):
            fallback_fps = 30.0
        index = 0
        while cap.grab():  # 디코딩만 하고, 필요한 프레임만 retrieve 한다
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if t <= last_t:  # 시각 정보가 없거나 멈춘 경우 프레임 번호로 대신한다
                t = index / fallback_fps
            last_t = t
            index += 1
            if t + 1e-6 < next_t:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                continue
            yield round(t, 3), frame
            next_t = t + interval_sec
    finally:
        cap.release()
