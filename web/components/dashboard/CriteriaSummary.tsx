import Link from "next/link";
import Badge from "@/components/common/Badge";
import RatioBar from "@/components/posting/RatioBar";
import { DOC_RATIO_COLORS, INTERVIEW_RATIO_COLORS } from "@/lib/posting";
import type { DocCriteria, InterviewCriteria, PostingDetail } from "@/types/posting";
import styles from "./Dashboard.module.css";

type Props = {
  postingId: number;
  posting: PostingDetail;
  doc: DocCriteria;
  interview: InterviewCriteria;
};

// 평가기준 요약: 인재상, 서류·면접 평가기준 비율, 면접 진행 설정 (ADM-003)
export default function CriteriaSummary({ postingId, posting, doc, interview }: Props) {
  const settings = [
    interview.question_count !== null && `질문 ${interview.question_count}개`,
    interview.follow_up_enabled !== null && `꼬리질문 ${interview.follow_up_enabled ? "사용" : "사용 안 함"}`,
    interview.think_time_sec !== null && `생각 ${interview.think_time_sec}초`,
    interview.answer_time_sec !== null && `답변 ${interview.answer_time_sec}초`,
  ].filter((x): x is string => typeof x === "string");

  return (
    <div className={styles.col}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>평가기준 요약</h2>
        <span className={styles.spacer} />
        <Link href={`/admin/postings/${postingId}?tab=criteria`} className={styles.link}>
          상세 보기 ›
        </Link>
      </div>

      <div className={styles.block}>
        <p className={styles.blockTitle}>인재상</p>
        <div className={styles.talent}>
          <Badge tone="navy">기능적</Badge>
          <span>{posting.functional_talent ?? "-"}</span>
        </div>
        <div className={styles.talent}>
          <Badge tone="navy">비기능적</Badge>
          <span>{posting.nonfunctional_talent ?? "-"}</span>
        </div>
      </div>

      <hr className={styles.divider} />
      <div className={styles.block}>
        <p className={styles.blockTitle}>서류 평가기준 비율</p>
        <RatioBar items={doc.criteria.map((c) => ({ label: c.criteria_name, value: c.ratio }))} colors={DOC_RATIO_COLORS} />
      </div>

      <hr className={styles.divider} />
      <div className={styles.block}>
        <p className={styles.blockTitle}>면접 평가기준</p>
        <RatioBar items={interview.criteria.map((c) => ({ label: c.criteria_name, value: c.ratio }))} colors={INTERVIEW_RATIO_COLORS} />
        <div className={styles.badges}>
          {settings.map((s) => (
            <Badge key={s} tone="gray">
              {s}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );
}
