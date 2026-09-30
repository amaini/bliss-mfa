"use client";

import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { api } from "../../lib/api";

type AuditEvent = {
  id: string;
  actor_id: string | null;
  action: string;
  subject_type: string;
  subject_id: string | null;
  reason: string | null;
  success: boolean;
  source_ip: string | null;
  previous_hash: string | null;
  event_hash: string;
  created_at: string;
};

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<AuditEvent[]>("/audit?limit=300")
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load audit log"));
  }, []);

  return (
    <Shell title="Audit">
      {error ? <div className="notice">{error}</div> : null}
      <section className="card table">
        <div className="headerRow auditGrid">
          <span>Time</span><span>Action</span><span>Actor</span><span>Reason</span><span>Result</span>
        </div>
        {events.map((event) => (
          <div className="row auditGrid" key={event.id}>
            <span>{new Date(event.created_at).toLocaleString()}</span>
            <strong>{event.action}</strong>
            <span>{event.actor_id ?? "system"}</span>
            <span>{event.reason ?? "—"}</span>
            <span className={event.success ? "active pill" : "locked pill"}>
              {event.success ? "Success" : "Failed"}
            </span>
          </div>
        ))}
        {events.length === 0 ? <div className="empty">No audit events yet.</div> : null}
      </section>

      <section className="card stack" style={{ marginTop: 16 }}>
        <p className="eyebrow">Integrity</p>
        <h2>Hash-chained local audit log</h2>
        <p className="muted">
          Each event stores the previous event hash and its own digest so deletion or modification
          of historical events can be detected during integrity verification.
        </p>
      </section>
    </Shell>
  );
}
