// main-api 호출. 브라우저는 main-api 하나만 호출한다 (아키텍처 4.1-1)
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string,
    // 요청 검증 실패(422) 때 필드별 오류. 폼 전체에 걸린 오류는 "_form" 키에 담는다
    public fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    // JWT는 HttpOnly 쿠키라서 항상 함께 보낸다 (코드베이스 4.5)
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    // 오류 형식 {code, message}. 요청 검증 실패(422)는 {detail: [{loc, msg}, ...]}
    const fields: Record<string, string> = {};
    if (Array.isArray(body?.detail)) {
      for (const d of body.detail as { loc: string[]; msg: string }[]) {
        const key = d.loc.length > 1 ? d.loc[d.loc.length - 1] : "_form";
        fields[key] = d.msg.replace(/^Value error, /, "");
      }
    }
    throw new ApiError(
      res.status,
      body?.code ?? null,
      body?.message ?? "요청을 처리하지 못했습니다. 입력값을 확인해 주세요.",
      fields,
    );
  }
  return res.json() as Promise<T>;
}
