"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Button from "@/components/common/Button";
import fieldStyles from "@/components/common/Field.module.css";
import Stepper from "@/components/common/Stepper";
import { ApiError, apiFetch } from "@/lib/api";
import type { BasicItem, DocItems, PostingDetail } from "@/types/posting";
import shared from "./PostingInfoForm.module.css";
import styles from "./DocItemsForm.module.css";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "기업 질문", "검토"];
const CUTOFFS = [1, 2, 3, 4]; // 5점 척도에서 탈락 기준이 될 수 있는 점수

type SkillRow = { key: number; name: string; cutoff: number | null };
type TopicRow = { key: number; name: string };

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 05 서류 작성 문항 등록 (ADM-006, ADM-011)
export default function DocItemsForm({ postingId }: { postingId: number }) {
  const router = useRouter();
  const nextKey = useRef(0);
  const newKey = () => nextKey.current++;

  const [basicItems, setBasicItems] = useState<BasicItem[]>([]);
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [topics, setTopics] = useState<TopicRow[]>([]);
  const [writeStatus, setWriteStatus] = useState<PostingDetail["write_status"]>("임시 저장");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<PostingDetail>(`/api/admin/postings/${postingId}`),
      apiFetch<DocItems>(`/api/admin/postings/${postingId}/doc-items`),
    ])
      .then(([posting, d]) => {
        setWriteStatus(posting.write_status);
        setBasicItems(d.basic_items);
        // 처음 들어오면 비어 있으므로 바로 입력할 수 있게 빈 줄을 하나씩 둔다
        const skillRows = d.skills.map((s) => ({ key: newKey(), name: s.skill_name, cutoff: s.cutoff_score }));
        const topicRows = d.essay_topics.map((name) => ({ key: newKey(), name }));
        setSkills(skillRows.length ? skillRows : [{ key: newKey(), name: "", cutoff: null }]);
        setTopics(topicRows.length ? topicRows : [{ key: newKey(), name: "" }]);
      })
      .catch((e) => setLoadError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [postingId]);

  // 값을 고치면 이전 저장 결과(오류·안내)는 더 이상 맞지 않으므로 지운다
  function touch() {
    setError(null);
    setNotice(null);
  }

  function toggleItem(itemId: number) {
    touch();
    setBasicItems((items) => items.map((i) => (i.item_id === itemId ? { ...i, selected: !i.selected } : i)));
  }

  function updateSkill(key: number, patch: Partial<SkillRow>) {
    touch();
    setSkills((rows) => rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  function updateTopic(key: number, name: string) {
    touch();
    setTopics((rows) => rows.map((r) => (r.key === key ? { ...r, name } : r)));
  }

  // validate=false는 임시 저장(필수 항목 검사 없음), true는 '다음'
  async function save(validate: boolean): Promise<boolean> {
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      await apiFetch(`/api/admin/postings/${postingId}/doc-items?validate=${validate}`, {
        method: "PUT",
        body: JSON.stringify({
          basic_item_ids: basicItems.filter((i) => i.selected).map((i) => i.item_id),
          skills: skills.map((s) => ({ skill_name: s.name, cutoff_score: s.cutoff })),
          essay_topics: topics.map((t) => t.name),
        }),
      });
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function onTempSave() {
    if (await save(false)) setNotice("임시 저장되었습니다.");
  }

  async function onNext() {
    if (await save(true)) router.push(`/admin/postings/${postingId}/edit/doc-criteria`);
  }

  // 입력한 내용을 잃지 않도록 임시 저장하고 이동한다. 저장하지 못하면 이동하지 않는다
  async function onPrev() {
    if (await save(false)) router.push(`/admin/postings/${postingId}/edit/info`);
  }

  if (loading) return null;
  if (loadError) return <p className={shared.loadError}>{loadError}</p>;

  return (
    <div className={shared.page}>
      <header className={shared.header}>
        <h1 className={shared.title}>{writeStatus === "등록 완료" ? "채용공고 수정" : "새 채용공고 등록"}</h1>
        <p className={shared.subtitle}>지원자가 서류 전형에서 작성할 문항을 등록합니다.</p>
      </header>

      <Stepper steps={STEPS} current={1} />

      <section className={shared.card}>
        <div className={shared.cardHead}>
          <h2 className={shared.cardTitle}>기본 문항</h2>
          <p className={shared.cardDesc}>지원서에 포함할 항목을 선택합니다.</p>
        </div>
        <div className={styles.checks}>
          {basicItems.map((item) => (
            <label key={item.item_id} className={styles.check}>
              <input
                type="checkbox"
                checked={item.selected}
                disabled={item.is_required}
                onChange={() => toggleItem(item.item_id)}
              />
              {item.item_name}
              {item.is_required && " (필수)"}
            </label>
          ))}
        </div>
      </section>

      <section className={shared.card}>
        <div className={shared.cardHead}>
          <h2 className={shared.cardTitle}>필수 기술 *</h2>
          <p className={shared.cardDesc}>
            기술별 탈락 기준 점수를 정합니다. 지원자는 5점 척도로 자기평가를 입력합니다.
          </p>
        </div>
        <p className={styles.notice}>
          지원자가 입력한 점수는 자기평가임을 인지해 주세요. 기준 점수 이하이면 서류 제출 시 바로 탈락 처리됩니다.
        </p>
        <div className={`${styles.skillRow} ${styles.skillHead}`}>
          <span>기술명</span>
          <span>탈락 기준 점수</span>
          <span>관리</span>
        </div>
        {skills.map((row, i) => (
          <div key={row.key} className={styles.skillRow}>
            <input
              className={fieldStyles.input}
              aria-label={`기술명 ${i + 1}`}
              placeholder="예) Java"
              value={row.name}
              onChange={(e) => updateSkill(row.key, { name: e.target.value })}
            />
            <select
              className={`${fieldStyles.input} ${fieldStyles.select}`}
              aria-label={`탈락 기준 점수 ${i + 1}`}
              value={row.cutoff ?? ""}
              onChange={(e) => updateSkill(row.key, { cutoff: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">기준 없음</option>
              {CUTOFFS.map((c) => (
                <option key={c} value={c}>
                  {c}점 이하 탈락
                </option>
              ))}
            </select>
            <button
              type="button"
              className={styles.remove}
              onClick={() => {
                touch();
                setSkills((rows) => rows.filter((r) => r.key !== row.key));
              }}
            >
              삭제
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="secondary"
          inline
          className={styles.add}
          onClick={() => {
            touch();
            setSkills((rows) => [...rows, { key: newKey(), name: "", cutoff: null }]);
          }}
        >
          + 기술 추가
        </Button>
      </section>

      <section className={shared.card}>
        <div className={shared.cardHead}>
          <h2 className={shared.cardTitle}>자기소개서 주제 *</h2>
          <p className={shared.cardDesc}>지원자가 주제별로 자유롭게 작성합니다.</p>
        </div>
        {topics.map((row, i) => (
          <div key={row.key} className={styles.topicRow}>
            <span className={styles.topicNo}>{i + 1}</span>
            <input
              className={styles.topicInput}
              aria-label={`자기소개서 주제 ${i + 1}`}
              placeholder="예) 지원 동기"
              value={row.name}
              onChange={(e) => updateTopic(row.key, e.target.value)}
            />
            <button
              type="button"
              className={styles.remove}
              onClick={() => {
                touch();
                setTopics((rows) => rows.filter((r) => r.key !== row.key));
              }}
            >
              삭제
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="secondary"
          inline
          className={styles.add}
          onClick={() => {
            touch();
            setTopics((rows) => [...rows, { key: newKey(), name: "" }]);
          }}
        >
          + 주제 추가
        </Button>
      </section>

      {error && (
        <p className={shared.formError} role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className={shared.notice} role="status">
          {notice}
        </p>
      )}

      <div className={shared.actions}>
        <Button type="button" variant="secondary" inline disabled={saving} onClick={onTempSave}>
          임시 저장
        </Button>
        <span className={shared.spacer} />
        <Button type="button" variant="secondary" inline disabled={saving} onClick={onPrev}>
          이전
        </Button>
        <Button type="button" inline disabled={saving} onClick={onNext}>
          다음
        </Button>
      </div>
    </div>
  );
}
