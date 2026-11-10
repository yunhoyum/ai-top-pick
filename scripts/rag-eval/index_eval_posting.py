"""평가용 공고를 만들고 프로젝트 문서를 색인한다 (RAG 설계서 5.2). main-api 이미지에서 실행한다.

실제 API로 공고를 등록하고, worker가 하는 회사 문서 임베딩(embedding_batch)을 이 프로세스에서 직접 실행한다.
Celery·Redis만 거치지 않는다. 필요한 컨테이너: postgres, embed-server.

final_project 폴더에서:
  docker run --rm --network pc1_default --env-file pc1/.env -v pc1_storage:/data/storage \
    -v "$(pwd)/main-api:/src" -v "$(pwd)/scripts/rag-eval:/eval" -w /src pc1-main-api:latest \
    sh -c "pip install -q -r requirements-dev.txt; python /eval/index_eval_posting.py"

마지막 줄에 공고 ID를 출력한다. run_retrieval_eval.py에 넘긴다.
"""

import json
import sys
from pathlib import Path

sys.path[:0] = ["/src", "/src/tests"]

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.clients.embed import EmbedClient
from app.main import app
from app.services import embedding_batch, job_queue
from app.services.progress_batch import get_engine
from test_postings import _fill_all, _login

EVAL_SET = json.loads(Path("/eval/rag_eval_set.json").read_text(encoding="utf-8"))
PDF = Path("/src") / Path(EVAL_SET["document"]).relative_to("main-api")

# Celery로 보내지 않고 아래에서 직접 실행한다. 실행 중인 worker가 같은 작업을 집어 가지 않게 한다
job_queue.send = lambda job_type, job_id: None

with TestClient(app) as client:
    admin = _login(client)
    pid = admin.post("/api/admin/postings").json()["posting_id"]
    _fill_all(admin, pid)
    r = admin.post(
        f"/api/admin/postings/{pid}/documents", files={"file": (PDF.name, PDF.read_bytes(), "application/pdf")}
    )
    assert r.status_code == 201, r.text
    assert admin.post(f"/api/admin/postings/{pid}/publish").status_code == 200

engine = get_engine()
with engine.connect() as c:
    job_id = c.execute(text("SELECT job_id FROM batch_job WHERE posting_id = :p"), {"p": pid}).scalar_one()
embedding_batch.embed_company_documents(job_id)

with engine.connect() as c:
    status, error = c.execute(
        text("SELECT status, error_message FROM batch_job WHERE job_id = :j"), {"j": job_id}
    ).one()
    contents = c.scalars(text("SELECT content FROM doc_chunk WHERE posting_id = :p ORDER BY seq"), {"p": pid}).all()
assert status == "완료", error

lengths = [len(o) for o in EmbedClient().tokenize(contents)]
print(f"chunks={len(contents)} tokens min={min(lengths)} max={max(lengths)} total={sum(lengths)}")
print(pid)
