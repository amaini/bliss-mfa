"use client";

import { useEffect, useState } from "react";

import { PortalShell } from "../components/PortalShell";
import { apiFetch } from "../lib/browser-api";

type Organization = {
  id: string;
  name: string;
  slug: string;
  role?: string;
  seat_limit: number;
};

type Stats = {
  organization_id: string;
  total_users: number;
  active_users: number;
  pending_users: number;
  disabled_users: number;
  locked_users: number;
  active_devices: number;
  pending_enrollments: number;
  seat_limit: number;
};

export default function Dashboard() {
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        let organizations = await apiFetch<Organization[]>("/me/organizations");

        if (organizations.length === 0) {
          try {
            organizations = await apiFetch<Organization[]>("/organizations");
          } catch {
            // Customer users without Bliss staff access should simply see
            // their own organization list from /me/organizations.
          }
        }

        const first = organizations[0] ?? null;
        setOrganization(first);
        if (first) {
          setStats(await apiFetch<Stats>(`/organizations/${first.id}/stats`));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load dashboard");
      }
    }

    load();
  }, []);

  return (
    <PortalShell title="MFA Dashboard">
      {error ? <div className="notice">{error}</div> : null}

      {!organization ? (
        <div className="card">
          <p className="eyebrow">No organization</p>
          <h2>No MFA organization is assigned to this account yet.</h2>
        </div>
      ) : (
        <>
          <div className="contextBar">
            <div>
              <span>Organization</span>
              <strong>{organization.name}</strong>
            </div>
            <a className="textLink" href={`/organizations/${organization.id}/users`}>
              Manage users
            </a>
          </div>

          <section className="stats">
            <article className="card stat">
              <span>Protected users</span>
              <strong>{stats?.active_users ?? "—"}</strong>
            </article>
            <article className="card stat">
              <span>Pending enrollment</span>
              <strong>{stats?.pending_enrollments ?? "—"}</strong>
            </article>
            <article className="card stat">
              <span>Locked users</span>
              <strong>{stats?.locked_users ?? "—"}</strong>
            </article>
            <article className="card stat">
              <span>Seats</span>
              <strong>
                {stats ? `${stats.total_users}/${stats.seat_limit}` : "—"}
              </strong>
            </article>
          </section>

          <section className="grid">
            <article className="card">
              <div className="cardHead">
                <p className="eyebrow">Operations</p>
                <h2>Quick actions</h2>
              </div>
              <div className="actionGrid">
                <a className="action" href={`/organizations/${organization.id}/users?new=1`}>
                  Onboard user
                </a>
                <a className="action" href={`/organizations/${organization.id}/users`}>
                  Replace MFA device
                </a>
                <a className="action" href={`/organizations/${organization.id}/users`}>
                  Revoke MFA device
                </a>
                <a className="action" href={`/organizations/${organization.id}/audit`}>
                  Review audit log
                </a>
              </div>
            </article>

            <article className="card">
              <div className="cardHead">
                <p className="eyebrow">Status</p>
                <h2>{organization.name}</h2>
              </div>
              <dl className="health">
                <div><dt>Active users</dt><dd>{stats?.active_users ?? "—"}</dd></div>
                <div><dt>Pending users</dt><dd>{stats?.pending_users ?? "—"}</dd></div>
                <div><dt>Disabled users</dt><dd>{stats?.disabled_users ?? "—"}</dd></div>
                <div><dt>Active devices</dt><dd>{stats?.active_devices ?? "—"}</dd></div>
              </dl>
            </article>
          </section>
        </>
      )}
    </PortalShell>
  );
}
