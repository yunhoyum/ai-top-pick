// 면접 질문 구성 계산 (SYS-006). 서버가 질문을 만들 때 쓰는 규칙을 입력 화면에서 미리 보여 주려고 같은 식을 쓴다

export type AiQuestionSplit = {
  ai: number;
  job: number;
  personality: number;
};

// AI 질문 수 = 출제 문제 개수 − 기업 질문 수
// 직무 질문 수 = AI 질문 수 × 직무 비율, 소수점 첫째 자리에서 반올림. 인성 질문 수 = AI 질문 수 − 직무 질문 수
export function splitAiQuestions(questionCount: number, companyCount: number, jobRatio: number): AiQuestionSplit {
  const ai = Math.max(questionCount - companyCount, 0);
  // 정수 계산으로 반올림한다 (0.5는 올림). 소수 계산은 오차가 생길 수 있다
  const job = Math.floor((ai * jobRatio + 50) / 100);
  return { ai, job, personality: ai - job };
}

export type AiSplitText = {
  // AI 질문이 한 개라도 있어서 비율이 적용된다
  hasAi: boolean;
  // "3개 (출제 6개 − 기업 질문 3개)"
  summary: string | null;
  // "직무 60% · 인성 40%" 또는 비율이 적용되지 않는 이유
  ratio: string | null;
  // "직무 2개 · 인성 1개"
  counts: string | null;
};

// 공고 상세와 검토 화면에서 보여줄 AI 질문 구성 문구
export function describeAiSplit(questionCount: number | null, companyCount: number, jobRatio: number | null): AiSplitText {
  const ratioText = jobRatio === null ? null : `직무 ${jobRatio}% · 인성 ${100 - jobRatio}%`;
  if (questionCount === null) return { hasAi: false, summary: null, ratio: ratioText, counts: null };

  const { ai, job, personality } = splitAiQuestions(questionCount, companyCount, jobRatio ?? 0);
  const summary = `${ai}개 (출제 ${questionCount}개 − 기업 질문 ${companyCount}개)`;
  if (ai === 0) {
    return { hasAi: false, summary, ratio: "AI 질문이 없어 비율은 적용되지 않습니다.", counts: "직무 0개 · 인성 0개" };
  }
  if (jobRatio === null) return { hasAi: true, summary, ratio: null, counts: null };
  return { hasAi: true, summary, ratio: ratioText, counts: `직무 ${job}개 · 인성 ${personality}개` };
}
