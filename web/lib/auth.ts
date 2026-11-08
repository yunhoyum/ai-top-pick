import { apiFetch } from "./api";

export type Me = {
  member_id: number;
  role: "관리자" | "지원자";
  name: string;
  email: string;
};

// 토큰은 HttpOnly 쿠키라 JS가 읽지 못한다. 로그인 상태와 역할은 서버에 물어서 확인한다
export const fetchMe = () => apiFetch<Me>("/api/auth/me");

export const logout = () => apiFetch<void>("/api/auth/logout", { method: "POST" });
