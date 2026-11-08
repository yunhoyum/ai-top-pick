import Badge from "@/components/common/Badge";
import type { DocItems } from "@/types/posting";
import styles from "./PostingDetail.module.css";

// 서류 문항 탭: 기본 문항, 필수 기술과 탈락 기준 점수, 자기소개서 주제 (ADM-037)
export default function DocItemsTab({ items }: { items: DocItems }) {
  return (
    <>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>기본 문항</h2>
        <div className={styles.chips}>
          {items.basic_items
            .filter((i) => i.selected)
            .map((i) => (
              <Badge key={i.item_id} tone="navy">
                {i.item_name}
              </Badge>
            ))}
        </div>
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>필수 기술</h2>
          <p className={styles.cardDesc}>지원자는 5점 척도로 자기평가를 입력합니다. 기준 점수 이하이면 제출 시 바로 탈락 처리됩니다.</p>
        </div>
        {items.skills.length === 0 && <p className={styles.empty}>등록한 필수 기술이 없습니다.</p>}
        {items.skills.map((s) => (
          <div key={s.skill_name} className={styles.line}>
            <span className={styles.lineName}>{s.skill_name}</span>
            <span className={styles.lineValue}>{s.cutoff_score === null ? "기준 없음" : `${s.cutoff_score}점 이하 탈락`}</span>
          </div>
        ))}
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>자기소개서 주제</h2>
        {items.essay_topics.length === 0 && <p className={styles.empty}>등록한 주제가 없습니다.</p>}
        {items.essay_topics.map((topic, i) => (
          <div key={i} className={styles.line}>
            <span className={styles.topicNo}>{i + 1}</span>
            <span className={styles.topicName}>{topic}</span>
          </div>
        ))}
      </section>
    </>
  );
}
