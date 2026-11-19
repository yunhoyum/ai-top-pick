"""평가 공고의 청크에 문맥을 붙여 다시 임베딩한다 (contextual retrieval 실험). ai-service 이미지에서 실행한다.

청크마다 LLM이 "이 청크가 문서의 어디에 있고 무엇을 다루는지"를 1~2문장으로 쓴다.
임베딩만 "문맥 + 청크"로 바꾸고 doc_chunk.content는 원문 그대로 둔다. 채점·근거 번호는 원문을 쓴다.
문서 전체(KURE 8,532토큰)가 OLLAMA_CONTEXT_LENGTH 6144를 넘는다. 그래서 문서 앞부분(제목·목차)과
청크 앞뒤만 넣는다 (사용자 결정 2026-11-19).

ai-service는 원래 doc_chunk를 읽기만 한다. 이 스크립트는 평가 공고의 임베딩만 고친다.

먼저 PC1에서 index_eval_posting.py로 색인한다. 그러면 results/doc-<공고 ID>.txt가 생긴다.
필요한 것: postgres, embed-server, LLM 서버.

PC2의 final_project 폴더에서 (PowerShell):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/contextualize_eval_posting.py <공고 ID> <실험 ID>

만든 문맥은 results/contexts-<실험 ID>.json에 저장한다.

[문맥 파일]을 주면 LLM을 부르지 않고 그 파일의 문맥(seq별)으로 임베딩만 한다. LLM 서버가 없는 PC1에서도 돌릴 수 있다.
예: Claude가 직접 쓴 문맥으로 하는 상한 실험 E4c — python /eval/contextualize_eval_posting.py <공고 ID> E4c /eval/results/contexts-E4c.json
"""

import json
import statistics
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.chains.structured import invoke_structured
from app.clients.embed import EmbedClient
from app.core.llm import get_chat_model
from app.db.doc_chunk import DocChunk
from app.db.session import get_engine

# 문서 앞부분(제목·문서 정보·목차)과 청크 앞뒤 길이 (KURE 토큰). EXAONE 토큰으로는 조금 더 길다
HEAD_TOKENS = 600
AROUND_TOKENS = 1000
# embed-server 입력 한도(EMBED_MAX_SEQ_LEN 512)에서 시작·끝 특수 토큰 2개를 뺀 값
EMBED_LIMIT = 510


class ContextOutput(BaseModel):
    context: str


def prompt(head: str, around: str, chunk: str) -> list[HumanMessage]:
    return [
        HumanMessage(
            content=f"""<문서 앞부분>
{head}
</문서 앞부분>

<주변 내용>
{around}
</주변 내용>

다음은 위 문서에서 잘라 낸 청크다.
<청크>
{chunk}
</청크>

이 청크를 검색할 때 도움이 되도록, 문서 전체에서 이 청크가 어느 장·절에 있고 무엇을 다루는지 1~2문장으로 써라.
청크 내용을 되풀이하지 말고, 청크에 빠진 대상(무엇에 관한 내용인지)을 채워라. 문서에 없는 내용은 쓰지 마라.
JSON {{"context": "..."}}만 출력하라."""
        )
    ]


def main(posting_id: int, experiment: str, contexts_file: str | None = None) -> None:
    text = Path(f"/eval/results/doc-{posting_id}.txt").read_text(encoding="utf-8")
    client = EmbedClient()
    offsets = client.tokenize([text])[0]
    given = None
    if contexts_file:
        given = {r["seq"]: r["context"] for r in json.loads(Path(contexts_file).read_text(encoding="utf-8"))["chunks"]}
    else:
        model = get_chat_model()
    head = text[: offsets[min(HEAD_TOKENS, len(offsets)) - 1][1]]

    with Session(get_engine()) as db:
        chunks = db.execute(
            select(DocChunk.chunk_id, DocChunk.seq, DocChunk.content)
            .where(DocChunk.posting_id == posting_id)
            .order_by(DocChunk.source_id, DocChunk.seq)
        ).all()
    if not chunks:
        raise SystemExit(f"공고 {posting_id}에 청크가 없습니다.")

    rows, pos = [], 0
    for chunk_id, seq, content in chunks:
        # 청크는 문서 텍스트를 자른 것이다. 겹침이 있어 앞 청크 시작 뒤에서 찾는다
        start = text.find(content, pos)
        if start < 0:
            raise SystemExit(f"청크 {seq}를 문서 텍스트에서 찾지 못했습니다. doc-{posting_id}.txt가 색인한 문서와 같은지 확인하세요.")
        pos = start + 1
        first = next(i for i, (_, e) in enumerate(offsets) if e > start)
        last = next((i for i, (s, _) in enumerate(offsets) if s >= start + len(content)), len(offsets))
        lo, hi = max(0, first - AROUND_TOKENS), min(len(offsets), last + AROUND_TOKENS)
        around = text[offsets[lo][0] : offsets[hi - 1][1]]

        started = time.perf_counter()
        if given is not None:
            context = given[seq]
        else:
            context = invoke_structured(model, prompt(head, around, content), ContextOutput).context.strip()
        rows.append({"chunk_id": chunk_id, "seq": seq, "context": context, "content": content,
                     "s": round(time.perf_counter() - started, 1)})
        print(f"[{seq}] {rows[-1]['s']}s {context}")

    inputs = [f"{r['context']}\n\n{r['content']}" for r in rows]
    lengths = [len(o) for o in client.tokenize(inputs)]
    too_long = [r["seq"] for r, n in zip(rows, lengths) if n > EMBED_LIMIT]
    if too_long:
        # embed-server가 조용히 자르면 청크 끝이 임베딩에서 빠진다. 쓰지 않고 멈춘다
        raise SystemExit(f"문맥을 붙이면 {EMBED_LIMIT}토큰을 넘는 청크: {too_long}")
    vectors = client.embed(inputs)
    with Session(get_engine()) as db:
        for r, vector in zip(rows, vectors, strict=True):
            db.execute(update(DocChunk).where(DocChunk.chunk_id == r["chunk_id"]).values(embedding=vector))
        db.commit()

    seconds = [r["s"] for r in rows]
    print(f"청크 {len(rows)}개, 문맥 생성 중앙 {statistics.median(seconds)}s 합계 {sum(seconds):.0f}s, "
          f"임베딩 입력 토큰 최대 {max(lengths)}")
    out = Path("/eval/results") / f"contexts-{experiment}.json"
    if contexts_file and Path(contexts_file).resolve() == out.resolve():
        # 받은 문맥 파일을 덮어쓰지 않는다
        return
    out.write_text(json.dumps({"experiment": experiment, "posting_id": posting_id, "head_tokens": HEAD_TOKENS,
                               "around_tokens": AROUND_TOKENS, "chunks": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
