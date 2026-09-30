"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { PortalShell } from "../../../../components/PortalShell";
import { apiFetch } from "../../../../lib/browser-api";

type AuditEvent = {
  id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  subject_type: string;
  subject_id: string | null;
  reason: string | null;
  success: boolean;
  created_at: string;
};

export default function AuditPage() {
  const params = useParams<{ id: string }>();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AuditEvent[]>(`/organizations/${params.id}/audit?limit=200`)
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load audit log"));
  }, [params.id]);

  return (
    <PortalShell title="Audit Log" eyebrow="Security">
      {error ? <div className="notice">{error}</div> : null}
      <div className="tableCard card">
        <div className="auditHeader">
          <span>Time</span>
          <span>Action</span>
          <span>Actor</span>
          <span>Reason</span>
          <span>Result</span>
        </div>
        {events.map((event) => (
          <div className="auditRow" key={event.id}>
            <span>{new Date(event.created_at).toLocaleString()}</span>
            <strong>{event.action}</strong>
            <span>{event.actor_id ?? event.actor_type}</span>
            <span>{event.reason ?? "—"}</span>
            <span className={event.success ? "good" : "bad"}>
              {event.success ? "Success" : "Failed"}
            </span>
          </div>
        ))}
        {events.length === 0 && !error ? (
          <div className="emptyState">No audit events yet.</div>
        ) : null}
      </div>
    </PortalShell>
  );
}
