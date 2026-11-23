// 질문 생성·면접 중 AI 처리 시간을 실제 서비스로 잰다 (RAG 개선 1·2 전후 비교).
//
// 원본 실험 공고는 건드리지 않고 복제본을 만든다 (clone_posting.sql). 그 복제본에서
//   1) 평가 지원자 D1~D3(../rag-eval/document_eval_set.json)으로 지원서를 제출하고 (API)
//   2) 서류 합격을 확정해 질문 생성 작업을 돌린다 → batch_job 시작~끝 = 지원자별 질문 생성 시간
//   3) Playwright 브라우저(가짜 카메라 + answer.wav 가짜 마이크)로 면접을 끝까지 본다
//      → WebSocket 'answer_end' ~ 다음 'question'(또는 'interview_end') = 답변마다 AI 처리 시간
//         (영상 업로드·STT 보정·채점 검색·채점·꼬리질문 판단/생성·다음 질문 TTS가 들어 있다)
// 서류 보고서는 만들지 않는다 (진행 상태를 DB로 바로 '서류 평가'로 바꿔 배치가 등록하지 않는다).
// 면접 보고서는 지원자가 끝날 때마다 생기므로, 끝날 때까지 기다린 뒤 다음 지원자를 시작한다 (LLM을 같이 쓰지 않게).
//
// 사용 (이 폴더에서, PC1 컨테이너가 떠 있어야 한다):
//   node run.mjs <조건 이름> <원본 공고 ID> [--applicants 3] [--answer-sec 20] [--headed]
//   예: node run.mjs before 3479   /   node run.mjs e1 8452   /   node run.mjs e1e2 8452
// 조건마다 PC2 ai-service 설정을 먼저 맞춘다 (README.md).
// 결과: results/<조건>-p<복제 공고 ID>.json. 비교는 node compare.mjs

import { execFileSync, spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, request } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const API = "http://localhost:8000";
const WEB = "http://localhost:3000";
const PASSWORD = "password1"; // 평가 공고를 만든 테스트 관리자 비밀번호 (main-api tests/test_postings.py)
const EMPTY_PDF = ["%PDF-1.4", "1 0 obj", "<<>>", "endobj", "trailer", "<<>>", "%%EOF", ""].join("\n");
const PG = ["exec", "-i", "pc1-postgres-1", "psql", "-U", "aitoppick", "-d", "aitoppick", "-v", "ON_ERROR_STOP=1"];

const args = process.argv.slice(2);
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i < 0 ? def : args[i + 1];
};
const [label, source] = args.filter((a, i) => !a.startsWith("--") && !["--applicants", "--answer-sec"].includes(args[i - 1]));
if (!label || !/^\d+$/.test(source ?? "")) {
  console.error("사용: node run.mjs <조건 이름> <원본 공고 ID> [--applicants 3] [--answer-sec 20] [--headed]");
  process.exit(1);
}
const APPLICANTS = Number(opt("applicants", 3));
const ANSWER_SEC = Number(opt("answer-sec", 20));
const HEADED = args.includes("--headed");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...m) => console.log(new Date().toLocaleTimeString("ko-KR"), ...m);

function sql(text) {
  return execFileSync("docker", [...PG, "-At", "-F", "\t"], { input: text, encoding: "utf8" }).trim();
}
const rows = (text) => (sql(text) ? sql(text).split("\n").map((l) => l.split("\t")) : []);

async function waitFor(check, timeoutMs, what) {
  const until = Date.now() + timeoutMs;
  for (;;) {
    const v = await check();
    if (v) return v;
    if (Date.now() > until) throw new Error(`${what}: ${timeoutMs / 1000}초 안에 끝나지 않았습니다`);
    await sleep(2000);
  }
}

async function api(ctx, method, path, body) {
  const r = await ctx.fetch(`${API}${path}`, { method, data: body });
  if (!r.ok()) throw new Error(`${method} ${path} → ${r.status()} ${await r.text()}`);
  return r.headers()["content-type"]?.includes("json") ? r.json() : null;
}

// ---------- 1. 공고 복제 ----------
function clonePosting() {
  const tpl = readFileSync(join(HERE, "clone_posting.sql"), "utf8");
  const r = spawnSync("docker", [...PG, "-v", `src=${source}`, "-v", `label=${label}`], { input: tpl, encoding: "utf8" });
  // NOTICE는 stderr로 나온다
  const id = r.stderr.match(/NEW_POSTING_ID=(\d+)/)?.[1];
  if (r.status !== 0 || !id) throw new Error(`공고 복제 실패: ${r.stderr}`);
  return Number(id);
}

// ---------- 2. 지원서 제출 ----------
async function apply(pid, applicant, i) {
  const ctx = await request.newContext();
  const email = `timing-${label}-${pid}-${i}@example.com`;
  await api(ctx, "POST", "/api/auth/signup", {
    role: "지원자", name: `시간측정${applicant.id}`, email, password: PASSWORD, password_confirm: PASSWORD, company_name: null,
  });
  await api(ctx, "POST", "/api/auth/login", { role: "지원자", email, password: PASSWORD });
  const d = applicant.documents;
  const base = `/api/postings/${pid}/application`;
  // 평가셋은 2019-03, 지원서는 2019.03 형식이다
  const period = (a, b) => `${a.replace("-", ".")} ~ ${(b ?? "").replace("-", ".")}`.trim();
  const got = await api(ctx, "GET", base);
  const form = got.form;
  await api(ctx, "PUT", `${base}/resume?validate=true`, {
    profile: { name: d.personal.name, phone: d.personal.phone, email },
    educations: d.educations.map((e) => ({ school_name: e.school_name, major: e.major, period: period(e.start_date, e.end_date) })),
    careers: !form.has_career ? [] : d.careers.map((c) => ({ company_name: c.company_name, job_role: c.job_role, period: period(c.start_date, c.end_date) })),
    projects: !form.has_project ? [] : d.projects.map((p) => ({ project_name: p.project_name, period: period(p.start_date, p.end_date), description: p.description })),
  });
  // 공고의 필수 기술(Java·SQL)에 점수를 주고, 사례는 평가 지원자의 기술 적용 사례를 그대로 쓴다
  const skills = got.skills.filter((s) => s.required).map((s) => s.skill_name);
  await api(ctx, "PUT", `${base}/skills?validate=true`, {
    skills: skills.map((name) => ({ skill_name: name, score: 4 })),
    cases: d.skill_cases.map((content, k) => ({ skill_name: skills[k % skills.length], content })),
  });
  await api(ctx, "PUT", `${base}/essays?validate=true`, {
    essays: form.essay_topics.map((t, k) => ({ topic_id: t.topic_id, content: d.essays[k]?.content ?? "" })),
  });
  // 포트폴리오는 필수 단계다. 내용 없는 PDF를 모든 조건에 똑같이 올린다 (평가셋 portfolio_text는 쓰지 않는다)
  const up = await ctx.post(`${API}${base}/portfolio`, {
    multipart: { file: { name: "portfolio.pdf", mimeType: "application/pdf", buffer: Buffer.from(EMPTY_PDF) } },
  });
  if (!up.ok()) throw new Error(`포트폴리오 업로드 → ${up.status()} ${await up.text()}`);
  const submitted = await api(ctx, "POST", `${base}/submit`);
  await ctx.dispose();
  const aid = Number(sql(`select a.application_id from application a join member m on m.member_id = a.applicant_id where m.email = '${email}' and a.posting_id = ${pid}`));
  return { applicant: applicant.id, email, application_id: aid, submitted };
}

// ---------- 3. 서류 합격 → 질문 생성 ----------
async function generateQuestions(pid, apps) {
  // 보고서 배치를 피하려고 진행 상태를 직접 '서류 평가'로 둔다 (배치는 앞으로만 가며 이미 같은 상태면 등록하지 않는다)
  sql(`update job_posting set doc_start_at = now() - interval '2 hours', doc_end_at = now() - interval '1 minute',
       progress_status = '서류 평가' where posting_id = ${pid}`);
  const adminEmail = sql(`select m.email from job_posting p join member m on m.member_id = p.admin_id where p.posting_id = ${pid}`);
  const admin = await request.newContext();
  await api(admin, "POST", "/api/auth/login", { role: "관리자", email: adminEmail, password: PASSWORD });
  await api(admin, "POST", `/api/admin/postings/${pid}/stages/document/pass`, { application_ids: apps.map((a) => a.application_id) });
  await admin.dispose();
  log(`서류 합격 확정 → 질문 생성 작업 ${apps.length}개`);
  const jobs = await waitFor(() => {
    const r = rows(`select application_id, status, extract(epoch from started_at - created_at), extract(epoch from finished_at - started_at), coalesce(error_message, '')
                    from batch_job where posting_id = ${pid} and job_type = '면접 질문 생성' order by application_id`);
    return r.length === apps.length && r.every(([, s]) => s === "완료" || s === "실패") ? r : null;
  }, 30 * 60_000, "질문 생성");
  return jobs.map(([aid, status, wait, secs, error]) => ({
    application_id: Number(aid), status, queue_wait_sec: Number(wait), seconds: Number(secs), error: error || undefined,
    questions: Number(sql(`select count(*) from interview_question where application_id = ${aid} and parent_question_id is null`)),
    ai_questions: Number(sql(`select count(*) from interview_question where application_id = ${aid} and parent_question_id is null and company_question_id is null`)),
  }));
}

// ---------- 4. 면접 ----------
async function interview(browser, app) {
  const context = await browser.newContext({ permissions: ["camera", "microphone"] });
  await context.grantPermissions(["camera", "microphone"], { origin: WEB });
  await api(context.request, "POST", "/api/auth/login", { role: "지원자", email: app.email, password: PASSWORD });
  const page = await context.newPage();

  const frames = []; // {t, dir, msg}
  let phase = null;
  let ended = false;
  page.on("websocket", (ws) => {
    if (!ws.url().includes("/ws/interview/")) return;
    ws.on("framesent", ({ payload }) => {
      if (typeof payload === "string") frames.push({ t: Date.now(), dir: "sent", msg: JSON.parse(payload) });
    });
    ws.on("framereceived", ({ payload }) => {
      if (typeof payload !== "string") return frames.push({ t: Date.now(), dir: "recv", msg: { type: "audio" } });
      const msg = JSON.parse(payload);
      frames.push({ t: Date.now(), dir: "recv", msg });
      if (msg.type === "phase") phase = { ...msg, qid: [...frames].reverse().find((f) => f.msg.type === "question")?.msg.question_id };
      if (msg.type === "interview_end" || msg.type === "suspended") ended = true;
    });
  });

  await page.goto(`${WEB}/interview/${app.application_id}/guide`);
  await page.getByText("안내사항을 모두 확인했습니다").click();
  await page.getByRole("button", { name: "기술적 테스트 시작" }).click();
  const start = page.getByRole("button", { name: "면접 시작" });
  await start.waitFor();
  await waitFor(() => start.isEnabled(), 60_000, "기술적 테스트(카메라·마이크 정상)");
  await start.click();
  log(`  ${app.applicant} 면접 시작`);

  let answered = null;
  await waitFor(async () => {
    if (ended) return true;
    if (phase?.phase === "answer" && phase.qid !== answered) {
      answered = phase.qid;
      await sleep(ANSWER_SEC * 1000);
      const done = page.getByRole("button", { name: "답변 완료" });
      if (await done.isEnabled()) await done.click();
      log(`  ${app.applicant} 질문 ${answered} 답변 완료`);
    }
    return false;
  }, 60 * 60_000, "면접");
  await sleep(1000);
  await context.close();
  return frames;
}

function transitions(frames) {
  const out = [];
  frames.forEach((f, i) => {
    if (f.dir !== "recv" || f.msg.type !== "answer_end") return;
    const next = frames.slice(i + 1).find((g) => g.dir === "recv" && ["question", "interview_end", "suspended"].includes(g.msg.type));
    out.push({
      question_id: f.msg.question_id, reason: f.msg.reason,
      next: next?.msg.type === "question" ? next.msg.question_id : next?.msg.type ?? null,
      seconds: next ? (next.t - f.t) / 1000 : null,
    });
  });
  return out;
}

function describe(qids) {
  if (!qids.length) return {};
  const r = rows(`select question_id, coalesce(parent_question_id::text, ''), coalesce(question_type, ''), company_question_id is not null
                  from interview_question where question_id in (${qids.join(",")})`);
  return Object.fromEntries(r.map(([id, parent, type, company]) => [
    id, { kind: parent ? "꼬리질문" : company === "t" ? "기업" : type },
  ]));
}

// ---------- 실행 ----------
const evalSet = JSON.parse(readFileSync(join(HERE, "../rag-eval/document_eval_set.json"), "utf8"));
const applicants = evalSet.applicants.slice(0, APPLICANTS);

const pid = clonePosting();
log(`조건 ${label}: 공고 ${source} → 복제 공고 ${pid}`);
const apps = [];
for (const [i, a] of applicants.entries()) apps.push(await apply(pid, a, i + 1));
log(`지원서 제출 ${apps.map((a) => a.application_id).join(", ")}`);

const questionJobs = await generateQuestions(pid, apps);
questionJobs.forEach((j) => log(`  지원서 ${j.application_id} 질문 생성 ${j.status} ${j.seconds.toFixed(1)}초 (대기 ${j.queue_wait_sec.toFixed(1)}초)`));

// 면접 진행으로 옮긴다 (일정 순서 제약: 서류 마감 < 결과 발표 < 면접 시작)
sql(`update job_posting set doc_end_at = now() - interval '3 minutes', doc_result_at = now() - interval '2 minutes',
     interview_start_at = now() - interval '1 minute', progress_status = '면접 진행' where posting_id = ${pid}`);

// Chromium은 경로에 공백이 있으면 가짜 마이크 파일을 못 읽고 기본 비프음을 낸다 (이 폴더는 'ai top-pick' 아래다)
const wav = join(tmpdir(), "timing-e2e-answer.wav");
if (/\s/.test(wav)) throw new Error(`임시 폴더 경로에 공백이 있습니다: ${wav}`);
copyFileSync(join(HERE, "answer.wav"), wav);
const browser = await chromium.launch({
  headless: !HEADED,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${wav}`,
    "--autoplay-policy=no-user-gesture-required",
  ],
});
const interviews = [];
for (const app of apps.filter((a) => questionJobs.find((j) => j.application_id === a.application_id)?.status === "완료")) {
  const frames = await interview(browser, app);
  const trans = transitions(frames);
  const kinds = describe([...new Set(trans.flatMap((t) => [t.question_id, t.next]).filter((x) => typeof x === "number"))]);
  trans.forEach((t) => {
    t.kind = kinds[t.question_id]?.kind;
    t.next_kind = typeof t.next === "number" ? kinds[t.next]?.kind : t.next;
  });
  trans.forEach((t) => log(`  ${app.applicant} ${t.kind} ${t.question_id} → ${t.next_kind} ${t.next}: ${t.seconds}초`));
  // 면접 보고서(LLM)가 끝나야 다음 지원자의 면접 시간이 섞이지 않는다
  await waitFor(() => ["완료", "실패"].includes(sql(`select status from batch_job where application_id = ${app.application_id} and job_type = '면접 보고서'`)),
    30 * 60_000, "면접 보고서");
  interviews.push({ ...app, transitions: trans, frames });
}
await browser.close();

mkdirSync(join(HERE, "results"), { recursive: true });
const file = join(HERE, "results", `${label}-p${pid}.json`);
writeFileSync(file, JSON.stringify({
  label, source_posting_id: Number(source), posting_id: pid, run_at: new Date().toISOString(), answer_sec: ANSWER_SEC,
  question_jobs: questionJobs, interviews,
}, null, 2));
log(`저장: ${file}`);
