"use client";

import { useEffect, useState } from "react";
import { Shell } from "../components/Shell";
import { api } from "../lib/api";

type Stats = {
  company_name: string;
  protected_rdp_users: number;
  total_users: number;
  active_users: number;
  pending_users: number;
  disabled_users: number;
  locked_users: number;
};

type License = {
  state: string;
  max_rdp_users: number;
  license_type: string | null;
  license_id: string | null;
};

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [license, setLicense] = useState<License | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<Stats>("/stats"),
      api<License>("/license/status"),
    ])
      .then(([nextStats, nextLicense]) => {
        setStats(nextStats);
        setLicense(nextLicense);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load dashboard"));
  }, []);

  return (
    <Shell title={stats?.company_name ?? "Dashboard"}>
      {error ? <div className="notice">{error}</div> : null}

      <section className="stats">
        <article className="card stat"><span>Protected RDP users</span><strong>{stats?.protected_rdp_users ?? "—"}</strong></article>
        <article className="card stat"><span>Licensed RDP seats</span><strong>{license?.max_rdp_users ?? "—"}</strong></article>
        <article className="card stat"><span>Pending enrollment</span><strong>{stats?.pending_users ?? "—"}</strong></article>
        <article className="card stat"><span>License state</span><strong>{license?.state ?? "—"}</strong></article>
      </section>

      <section className="grid">
        <article className="card stack">
          <div>
            <p className="eyebrow">Operations</p>
            <h2>Office-managed MFA</h2>
            <p className="muted">User onboarding, revocation and day-to-day MFA operations stay inside this appliance.</p>
          </div>
          <div className="actions">
            <a href="/users">Manage RDP users</a>
            <a href="/administrators">Manage administrators</a>
            <a href="/audit">Review audit history</a>
          </div>
        </article>

        <article className="card stack">
          <div>
            <p className="eyebrow">Local status</p>
            <h2>{license?.license_type ?? "Unlicensed"}</h2>
          </div>
          <div className="split"><span>Active users</span><strong>{stats?.active_users ?? "—"}</strong></div>
          <div className="split"><span>Disabled users</span><strong>{stats?.disabled_users ?? "—"}</strong></div>
          <div className="split"><span>Locked users</span><strong>{stats?.locked_users ?? "—"}</strong></div>
          <div className="split"><span>Total records</span><strong>{stats?.total_users ?? "—"}</strong></div>
        </article>
      </section>
    </Shell>
  );
}
