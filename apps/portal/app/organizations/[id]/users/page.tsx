"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import QRCode from "qrcode";

import { PortalShell } from "../../../../components/PortalShell";
import { apiFetch } from "../../../../lib/browser-api";

type User = {
  id: string;
  organization_id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  status: string;
  multiotp_username: string;
  created_at: string;
};

type Enrollment = {
  enrollment_token: string;
  provisioning_uri: string;
  expires_at: string;
};

export default function UsersPage() {
  const params = useParams<{ id: string }>();
  const organizationId = params.id;
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyUser, setBusyUser] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createdEnrollment, setCreatedEnrollment] = useState<Enrollment | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);

  async function loadUsers() {
    try {
      setUsers(await apiFetch<User[]>(`/organizations/${organizationId}/users`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load users");
    }
  }

  useEffect(() => {
    loadUsers();
  }, [organizationId]);

  useEffect(() => {
    if (!createdEnrollment) {
      setQrDataUrl(null);
      return;
    }

    QRCode.toDataURL(createdEnrollment.provisioning_uri, {
      errorCorrectionLevel: "M",
      margin: 1,
      width: 260,
    })
      .then(setQrDataUrl)
      .catch(() => setQrDataUrl(null));
  }, [createdEnrollment]);

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const username = String(form.get("username") ?? "").trim();
    const displayName = String(form.get("display_name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();

    try {
      const user = await apiFetch<User>(`/organizations/${organizationId}/users`, {
        method: "POST",
        body: JSON.stringify({
          username,
          display_name: displayName || null,
          email: email || null,
        }),
      });

      const enrollment = await apiFetch<Enrollment>(
        `/organizations/${organizationId}/users/${user.id}/enrollments`,
        { method: "POST", body: "{}" }
      );

      setCreatedEnrollment(enrollment);
      setShowCreate(false);
      event.currentTarget.reset();
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create user");
    }
  }

  async function reasonAction(user: User, action: "unlock" | "disable" | "enable") {
    const reason = window.prompt(`Reason for ${action}:`);
    if (!reason) return;

    setBusyUser(user.id);
    setError(null);
    try {
      await apiFetch(
        `/organizations/${organizationId}/users/${user.id}/${action}`,
        {
          method: "POST",
          body: JSON.stringify({ reason }),
        }
      );
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyUser(null);
    }
  }

  async function revoke(user: User) {
    const reason = window.prompt("Reason for revoking this MFA device:");
    if (!reason) return;
    if (!window.confirm(`Revoke MFA for ${user.username}?`)) return;

    setBusyUser(user.id);
    setError(null);
    try {
      await apiFetch(
        `/organizations/${organizationId}/users/${user.id}/revoke`,
        {
          method: "POST",
          body: JSON.stringify({ reason }),
        }
      );
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to revoke device");
    } finally {
      setBusyUser(null);
    }
  }

  async function beginEnrollment(user: User) {
    setBusyUser(user.id);
    setError(null);
    try {
      const enrollment = await apiFetch<Enrollment>(
        `/organizations/${organizationId}/users/${user.id}/enrollments`,
        { method: "POST", body: "{}" }
      );
      setCreatedEnrollment(enrollment);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start enrollment");
    } finally {
      setBusyUser(null);
    }
  }

  async function deleteUser(user: User) {
    const reason = window.prompt("Reason for permanently deleting this MFA user:");
    if (!reason) return;
    if (!window.confirm(`Permanently delete ${user.username}?`)) return;

    setBusyUser(user.id);
    setError(null);
    try {
      await apiFetch(
        `/organizations/${organizationId}/users/${user.id}?reason=${encodeURIComponent(reason)}`,
        { method: "DELETE" }
      );
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete user");
    } finally {
      setBusyUser(null);
    }
  }

  const activeCount = useMemo(
    () => users.filter((user) => user.status === "active").length,
    [users]
  );

  return (
    <PortalShell title="Users">
      <div className="contextBar">
        <div>
          <span>MFA users</span>
          <strong>{activeCount} active / {users.length} total</strong>
        </div>
        <button className="primary" onClick={() => setShowCreate((value) => !value)}>
          {showCreate ? "Cancel" : "Add user"}
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {showCreate ? (
        <form className="card inlineForm" onSubmit={createUser}>
          <div>
            <label htmlFor="username">Username</label>
            <input id="username" name="username" required placeholder="jsmith" />
          </div>
          <div>
            <label htmlFor="display_name">Display name</label>
            <input id="display_name" name="display_name" placeholder="John Smith" />
          </div>
          <div>
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" placeholder="john@example.com" />
          </div>
          <button className="primary" type="submit">Create and enroll</button>
        </form>
      ) : null}

      {createdEnrollment ? (
        <section className="card enrollmentPanel">
          <div>
            <p className="eyebrow">Enrollment</p>
            <h2>Scan with an authenticator app</h2>
            <p className="muted">
              This provisioning material is temporary. Do not send screenshots through
              insecure channels.
            </p>
          </div>
          {qrDataUrl ? <img className="qrImage" src={qrDataUrl} alt="MFA enrollment QR code" /> : null}
          <details>
            <summary>Manual provisioning URI</summary>
            <code className="secretCode">{createdEnrollment.provisioning_uri}</code>
          </details>
          <small>Expires {new Date(createdEnrollment.expires_at).toLocaleString()}</small>
          <button className="secondaryButton" onClick={() => setCreatedEnrollment(null)}>
            Close
          </button>
        </section>
      ) : null}

      <div className="tableCard card">
        <div className="userHeader">
          <span>User</span>
          <span>Status</span>
          <span>Email</span>
          <span>Actions</span>
        </div>

        {users.map((user) => (
          <div className="userRow" key={user.id}>
            <div>
              <strong>{user.display_name || user.username}</strong>
              <small>{user.username}</small>
            </div>
            <span className={`statusPill status-${user.status}`}>{user.status}</span>
            <span>{user.email || "—"}</span>
            <div className="rowActions wrap">
              {user.status === "disabled" ? (
                <button disabled={busyUser === user.id} onClick={() => reasonAction(user, "enable")}>
                  Enable
                </button>
              ) : (
                <button disabled={busyUser === user.id} onClick={() => reasonAction(user, "disable")}>
                  Disable
                </button>
              )}
              <button disabled={busyUser === user.id} onClick={() => reasonAction(user, "unlock")}>
                Unlock
              </button>
              <button disabled={busyUser === user.id} onClick={() => beginEnrollment(user)}>
                Enroll
              </button>
              <button className="dangerText" disabled={busyUser === user.id} onClick={() => revoke(user)}>
                Revoke
              </button>
              <button className="dangerText" disabled={busyUser === user.id} onClick={() => deleteUser(user)}>
                Delete
              </button>
            </div>
          </div>
        ))}

        {users.length === 0 ? <div className="emptyState">No MFA users yet.</div> : null}
      </div>
    </PortalShell>
  );
}
