"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const navigation = [["/", "Dashboard"], ["/users", "RDP Users"], ["/administrators", "Administrators"], ["/audit", "Audit"], ["/license", "License & Billing"]] as const;

export function Shell({ title, children }: { title: string; children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="shell">
      <header className="topBar">
        <Link className="brand" href="/" aria-label="Bliss Secure MFA dashboard">
          <span className="brandMark" aria-hidden="true">B</span>
          <div><strong>Bliss Secure MFA</strong><small>Local Appliance</small></div>
        </Link>
        <nav aria-label="Main navigation">
          {navigation.map(([href, label]) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}>{label}</Link>)}
        </nav>
        <a className="signout" href="/api/auth/logout">Sign out</a>
      </header>
      <main className="content" id="main-content">
        <header className="pageHeader"><p className="eyebrow">Local management</p><h1>{title}</h1></header>
        {children}
      </main>
      <footer className="footer">Bliss Secure MFA · Local management console</footer>
    </div>
  );
}
