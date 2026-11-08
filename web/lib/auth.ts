import { API_URL, apiFetch } from "./api";

export type Me = {
  member_id: number;
  role: "관리자" | "지원자";
  name: string;
  email: string;
};

// 토큰은 HttpOnly 쿠키라 JS가 읽지 못한다. 로그인 상태와 역할은 서버에 물어서 확인한다
export const fetchMe = () => apiFetch<Me>("/api/auth/me");

// 비로그인도 볼 수 있는 화면용. 로그인하지 않았으면 로그인 화면으로 보내지 않고 null을 돌려준다
export async function fetchMeIfLoggedIn(): Promise<Me | null> {
  try {
    const res = await fetch(`${API_URL}/api/auth/me`, { credentials: "include" });
    return res.ok ? ((await res.json()) as Me) : null;
  } catch {
    return null;
  }
}

export const logout =() => apiFetch<void>("/api/auth/logout", { method: "POST" });
