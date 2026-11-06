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

// 화면 02 회원가입 (ADM-001, APP-001)
export default function SignupForm() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("관리자");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  // 비밀번호 확인 칸을 벗어날 때 바로 일치 여부를 확인한다 (비워 둔 경우는 제출 때 검사)
  function checkPasswordMatch(e: React.FocusEvent<HTMLInputElement>) {
    const form = e.currentTarget.form;
    if (!form) return;
    const password = (form.elements.namedItem("password") as HTMLInputElement).value;
    const confirm = (form.elements.namedItem("password_confirm") as HTMLInputElement).value;
    setFieldErrors((prev) => {
      const next = { ...prev };
      if (confirm && password !== confirm) next.password_confirm = "비밀번호가 일치하지 않습니다.";
      else delete next.password_confirm;
      return next;
    });
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const value = (name: string) => String(form.get(name) ?? "").trim();
    const password = String(form.get("password") ?? "");
    const passwordConfirm = String(form.get("password_confirm") ?? "");

    // 서버(main-api)도 같은 규칙으로 다시 검증한다
    const errors: Record<string, string> = {};
    if (!value("name")) errors.name = "이름을 입력해 주세요.";
    if (!value("email")) errors.email = "이메일을 입력해 주세요.";
    else if (!EMAIL_PATTERN.test(value("email"))) errors.email = "올바른 이메일 형식이 아닙니다.";
    if (password.length < 8) errors.password = "비밀번호는 8자 이상이어야 합니다.";
    else if (new TextEncoder().encode(password).length > 72)
      errors.password = "비밀번호가 너무 깁니다.";
    if (password !== passwordConfirm) errors.password_confirm = "비밀번호가 일치하지 않습니다.";
    if (role === "관리자" && !value("company_name")) errors.company_name = "회사명을 입력해 주세요.";
    setFieldErrors(errors);
    setError(null);
    if (Object.keys(errors).length > 0) return;

    setSubmitting(true);
    try {
      await apiFetch("/api/auth/signup", {
        method: "POST",
        body: JSON.stringify({
          role,
          name: value("name"),
          email: value("email"),
          password,
          password_confirm: passwordConfirm,
          company_name: role === "관리자" ? value("company_name") : null,
        }),
      });
      router.push("/login");
    } catch (err) {
      if (err instanceof ApiError && err.code === "EMAIL_DUPLICATED") {
        setFieldErrors({ email: err.message });
      } else if (err instanceof ApiError && Object.keys(err.fields).length > 0) {
        // 서버 검증에서 걸린 필드를 해당 입력칸 아래에 표시한다
        const { _form, ...byField } = err.fields;
        setFieldErrors(
          Object.fromEntries(
            Object.keys(byField).map((k) => [
              k,
              k === "email" ? "올바른 이메일 형식이 아닙니다." : "입력값을 확인해 주세요.",
            ]),
          ),
        );
        setError(_form ?? null);
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
        <h1 className={styles.title}>회원가입</h1>
        <p className={styles.subtitle}>관리자는 채용공고를 등록하고, 지원자는 공고에 지원합니다.</p>
      </div>

      <RoleTabs value={role} onChange={setRole} />

      <div className={styles.fields}>
        <Field label="이름" name="name" placeholder="이름 입력" autoComplete="name" error={fieldErrors.name} />
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
          placeholder="8자 이상 입력"
          autoComplete="new-password"
          onBlur={checkPasswordMatch}
          error={fieldErrors.password}
        />
        <Field
          label="비밀번호 확인"
          name="password_confirm"
          type="password"
          placeholder="비밀번호 다시 입력"
          autoComplete="new-password"
          onBlur={checkPasswordMatch}
          error={fieldErrors.password_confirm}
        />
        {role === "관리자" && (
          <Field
            label="회사명 (관리자)"
            name="company_name"
            placeholder="소속 회사명 입력"
            error={fieldErrors.company_name}
          />
        )}
      </div>

      {error && (
        <p className={styles.formError} role="alert">
          {error}
        </p>
      )}

      <Button type="submit" disabled={submitting}>
        {submitting ? "가입 중..." : "가입하기"}
      </Button>

      <p className={styles.footer}>
        이미 계정이 있으신가요? <Link href="/login">로그인</Link>
      </p>
    </form>
  );
}
