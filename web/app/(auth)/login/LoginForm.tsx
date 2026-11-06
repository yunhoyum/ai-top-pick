"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Button from "@/components/common/Button";
import Field from "@/components/common/Field";
import RoleTabs, { type Role } from "@/components/common/RoleTabs";
import { ApiError, apiFetch } from "@/lib/api";
import { EMAIL_PATTERN } from "@/lib/validation";
import styles from "../form.module.css";

// 로그인 후 역할별 첫 화면 (코드베이스 5. web)
const HOME: Record<Role, string> = {
  관리자: "/admin/dashboard",
  지원자: "/postings",
};

// 화면 01 로그인 (ADM-002, APP-002)
export default function LoginForm() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("관리자");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");

    const errors: Record<string, string> = {};
    if (!email) errors.email = "이메일을 입력해 주세요.";
    else if (!EMAIL_PATTERN.test(email)) errors.email = "올바른 이메일 형식이 아닙니다.";
    if (!password) errors.password = "비밀번호를 입력해 주세요.";
    setFieldErrors(errors);
    setError(null);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      // 성공하면 main-api가 JWT를 HttpOnly 쿠키로 내려준다. 응답 본문에는 토큰이 없다
      await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ role, email, password }),
      });
      router.push(HOME[role]);
    } catch (err) {
      if (err instanceof ApiError && err.fields.email) {
        setFieldErrors({ email: "올바른 이메일 형식이 아닙니다." });
      } else {
        setError(err instanceof ApiError ? err.message : "서버에 연결하지 못했습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={onSubmit} noValidate>
      <div className={styles.heading}>
        <h1 className={styles.title}>로그인</h1>
        <p className={styles.subtitle}>역할을 선택하고 계정 정보를 입력해 주세요.</p>
      </div>

      <RoleTabs value={role} onChange={setRole} />

      <div className={styles.fields}>
        <Field
          label="이메일"
          name="email"
          type="email"
          placeholder="name@company.com"
          autoComplete="email"
          error={fieldErrors.email}
        />
        <Field
          label="비밀번호"
          name="password"
          type="password"
          placeholder="비밀번호 입력"
          autoComplete="current-password"
          error={fieldErrors.password}
        />
      </div>

      {error && (
        <p className={styles.formError} role="alert">
          {error}
        </p>
      )}

      <Button type="submit" disabled={submitting}>
        {submitting ? "로그인 중..." : "로그인"}
      </Button>

      <p className={styles.footer}>
        계정이 없으신가요? <Link href="/signup">회원가입</Link>
      </p>
    </form>
  );
}
