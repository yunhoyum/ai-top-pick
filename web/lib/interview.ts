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
