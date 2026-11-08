"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchMe, logout, type Me } from "@/lib/auth";
import BrandLogo from "./BrandLogo";
import styles from "./AdminShell.module.css";

const NAV = [
  { href: "/admin/dashboard", label: "대시보드" },
  { href: "/admin/postings", label: "채용공고 관리" },
  { href: "/admin/inquiries", label: "문의·예외 처리" },
];

// 관리자 화면 틀 (Figma Admin/Sidebar). 로그인과 역할 확인이 끝나기 전에는 화면을 숨긴다
// (내용을 아예 그리지 않으면 Next.js가 그려지지 않은 구간으로 보고 개발 모드에서 오류를 낸다)
export default function AdminShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    // 로그인 안 했거나 만료되었으면 apiFetch가 /login으로 보낸다 (401)
    fetchMe()
      .then((m) => {
        if (m.role !== "관리자") router.replace("/postings"); // 지원자는 자기 화면으로
        else setMe(m);
      })
      .catch(() => {});
  }, [router]);

  async function onLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <div className={styles.shell} hidden={!me}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <BrandLogo />
        </div>
        <nav className={styles.nav}>
          {NAV.map(({ href, label }) => {
            const active = pathname.startsWith(href);
            return (
              <Link key={href} href={href} className={`${styles.item} ${active ? styles.active : ""}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={active ? "/admin/nav-dot-active.svg" : "/admin/nav-dot.svg"} alt="" width={6} height={6} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className={styles.spacer} />
        <div className={styles.user}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/admin/avatar.svg" alt="" width={32} height={32} />
          <div className={styles.info}>
            <span className={styles.name}>{me?.name}</span>
            <button type="button" className={styles.logout} onClick={onLogout}>
              로그아웃
            </button>
          </div>
        </div>
      </aside>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
