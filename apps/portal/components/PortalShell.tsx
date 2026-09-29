import type { ReactNode } from "react";

export function PortalShell({
  children,
  title,
  eyebrow = "Operations",
}: {
  children: ReactNode;
  title: string;
  eyebrow?: string;
}) {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">B</span>
          <div>
            <strong>Bliss Secure MFA</strong>
            <small>Management Portal</small>
          </div>
        </div>

        <nav>
          <a href="/">Dashboard</a>
          <a href="/organizations">Organizations</a>
          <a href="/settings">Settings</a>
        </nav>

        <div className="sidebarFoot">
          <a href="/api/auth/logout">Sign out</a>
          <span>Bliss IT Solutions</span>
          <small>Secure MFA management</small>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1>{title}</h1>
          </div>
        </header>
        {children}
      </section>
    </main>
  );
}
