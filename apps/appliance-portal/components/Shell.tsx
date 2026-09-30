import type { ReactNode } from "react";

export function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">B</span>
          <div><strong>Bliss Secure MFA</strong><small>Local Appliance</small></div>
        </div>
        <nav>
          <a href="/">Dashboard</a>
          <a href="/users">RDP Users</a>
          <a href="/administrators">Administrators</a>
          <a href="/audit">Audit</a>
          <a href="/license">License & Billing</a>
        </nav>
        <a className="signout" href="/api/auth/logout">Sign out</a>
      </aside>
      <section className="content">
        <header><p className="eyebrow">Local management</p><h1>{title}</h1></header>
        {children}
      </section>
    </main>
  );
}
