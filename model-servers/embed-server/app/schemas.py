from pydantic import BaseModel, Field, field_validator


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)

    @field_validator("texts")
    @classmethod
    def no_blank(cls, v: list[str]) -> list[str]:
        if any(not t.strip() for t in v):
            raise ValueError("공백뿐인 문장은 허용되지 않습니다")
        return v


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    dim: int


class TokenizeRequest(EmbedRequest):
    """청크 분할용. 글마다 KURE-v1 토큰의 글자 위치를 돌려준다."""


class TokenizeResponse(BaseModel):
    # 글마다 [시작, 끝] 글자 위치 목록. 시작·끝 특수 토큰은 넣지 않는다
    offsets: list[list[tuple[int, int]]]
