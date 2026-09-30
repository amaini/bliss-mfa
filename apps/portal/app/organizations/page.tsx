"use client";

import { useEffect, useState } from "react";

import { PortalShell } from "../../components/PortalShell";
import { apiFetch } from "../../lib/browser-api";

type Organization = {
  id: string;
  name: string;
  slug: string;
  role?: string;
  seat_limit: number;
};

export default function OrganizationsPage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        let items = await apiFetch<Organization[]>("/me/organizations");
        if (items.length === 0) {
          try {
            items = await apiFetch<Organization[]>("/organizations");
          } catch {
            // Non-staff customer accounts may not access the global list.
          }
        }
        setOrganizations(items);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load organizations");
      }
    }
    load();
  }, []);

  return (
    <PortalShell title="Organizations">
      {error ? <div className="notice">{error}</div> : null}
      <div className="tableCard card">
        <div className="tableHeader">
          <span>Organization</span>
          <span>Role</span>
          <span>Seats</span>
          <span />
        </div>

        {organizations.map((organization) => (
          <div className="tableRow" key={organization.id}>
            <div>
              <strong>{organization.name}</strong>
              <small>{organization.slug}</small>
            </div>
            <span>{organization.role ?? "Bliss staff"}</span>
            <span>{organization.seat_limit}</span>
            <div className="rowActions">
              <a href={`/organizations/${organization.id}/users`}>Users</a>
              <a href={`/organizations/${organization.id}/audit`}>Audit</a>
            </div>
          </div>
        ))}

        {organizations.length === 0 && !error ? (
          <div className="emptyState">No organizations assigned.</div>
        ) : null}
      </div>
    </PortalShell>
  );
}
