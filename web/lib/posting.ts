import type { BadgeTone } from "@/components/common/Badge";
import type { ReviewStep } from "@/types/posting";

// 진행 상태 → 배지 색 (Figma: 서류 접수 중 청록, 서류 평가 주황, 면접 진행 남색, 마감 회색)
export const PROGRESS_TONES: Record<string, BadgeTone> = {
  "모집 전": "gray",
  "서류 접수 중": "teal",
  "서류 평가": "amber",
  "면접 진행": "navy",
  "면접 평가": "amber",
  마감: "gray",
};

// 수정 화면 주소의 단계 이름 → 화면에 보이는 이름
export const STEP_LABELS: Record<ReviewStep, string> = {
  info: "공고 정보",
  "doc-items": "서류 문항",
  "doc-criteria": "서류 평가기준",
  "interview-criteria": "면접 평가기준",
  "company-questions": "면접 질문",
};

// 공고 수정·삭제는 '모집 전'에서만 할 수 있다 (ADM-014~020)
export const isEditableProgress = (progress: string | null) => progress === "모집 전";

export type StageState = {
  label: string;
  tone: BadgeTone;
  // 전형이 마감되면 해당 전형 평가 화면으로 갈 수 있다 (ADM-013)
  closed: boolean;
  started: boolean;
};

const BEFORE: StageState = { label: "시작 전", tone: "gray", closed: false, started: false };
const ONGOING = (label: string): StageState => ({ label, tone: "teal", closed: false, started: true });
const CLOSED: StageState = { label: "마감", tone: "gray", closed: true, started: true };

// 서류 전형: 서류 접수 마감 일시가 지나면 마감 (진행 상태가 서류 평가 이후)
export function docStage(progress: string | null): StageState {
  if (progress === "서류 접수 중") return ONGOING("접수 중");
  if (progress === null || progress === "모집 전") return BEFORE;
  return CLOSED;
}

// 면접 전형: 면접 마감 일시가 지나면 마감 (진행 상태가 면접 평가 이후)
export function interviewStage(progress: string | null): StageState {
  if (progress === "면접 진행") return ONGOING("진행 중");
  if (progress === "면접 평가" || progress === "마감") return CLOSED;
  return BEFORE;
}

// 평가 비율 막대 색 (Figma): 서류 평가기준은 4색, 면접 평가기준은 3색 (언어는 accent-600, 비언어는 accent-300)
export const DOC_RATIO_COLORS = ["var(--primary-700)", "var(--primary-500)", "var(--accent-600)", "var(--accent-300)"];
export const INTERVIEW_RATIO_COLORS = ["var(--primary-700)", "var(--accent-600)", "var(--accent-300)"];
