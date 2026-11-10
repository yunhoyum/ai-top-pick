import os
import threading

import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "nlpai-lab/KURE-v1"
EXPECTED_DIM = 1024
BATCH_SIZE = 16
# 긴 입력이 VRAM을 키우지 않게 제한한다 (기본 모델 한도는 8192)
MAX_SEQ_LEN = int(os.environ.get("EMBED_MAX_SEQ_LEN", "512"))

_model: SentenceTransformer | None = None
_lock = threading.Lock()


def load() -> None:
    global _model
    if not torch.cuda.is_available():
        # 조용히 CPU로 돌지 않게 한다
        raise RuntimeError("CUDA를 사용할 수 없습니다. embed-server는 GPU가 필요합니다.")
    # FP16으로 바로 올려 FP32 임시 메모리가 캐시에 남지 않게 한다
    model = SentenceTransformer(
        MODEL_NAME, device="cuda", model_kwargs={"torch_dtype": torch.float16}
    )
    model.half()  # FP16 보장
    model.max_seq_length = MAX_SEQ_LEN
    dim = model.get_embedding_dimension()
    if dim != EXPECTED_DIM:
        raise RuntimeError(f"임베딩 차원 불일치: {dim} (기대값 {EXPECTED_DIM})")
    _model = model
    encode(["예열"])  # 예열 1회
    torch.cuda.empty_cache()


def encode(texts: list[str]) -> list[list[float]]:
    if _model is None:
        raise RuntimeError("모델이 로드되지 않았습니다")
    with _lock:
        vecs = _model.encode(
            texts,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
    return vecs.astype("float32").tolist()


def tokenize(texts: list[str]) -> list[list[tuple[int, int]]]:
    """토큰별 글자 위치. 길이 제한 없이 전부 센다 (청크를 나누는 쪽이 길이를 정한다)."""
    if _model is None:
        raise RuntimeError("모델이 로드되지 않았습니다")
    with _lock:
        encoded = _model.tokenizer(
            texts, add_special_tokens=False, return_offsets_mapping=True, verbose=False
        )
    return [[tuple(o) for o in offsets] for offsets in encoded["offset_mapping"]]


def dim() -> int:
    return EXPECTED_DIM
