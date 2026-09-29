"use client";

import { FormEvent, useEffect, useState } from "react";
import QRCode from "qrcode";

import { Shell } from "../../components/Shell";
import { api } from "../../lib/api";

type User = {
  id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  status: string;
  protected_rdp: boolean;
  created_at: string;
};

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [qr, setQr] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState<{ userId: string; uri: string } | null>(null);

  async function load() {
    try {
      setUsers(await api<User[]>("/users"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load users");
    }
  }

  useEffect(() => { load(); }, []);

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const user = await api<User>("/users", {
        method: "POST",
        body: JSON.stringify({
          username: String(form.get("username") ?? "").trim(),
          display_name: String(form.get("display_name") ?? "").trim() || null,
          email: String(form.get("email") ?? "").trim() || null,
          protected_rdp: true,
        }),
      });
      const enrollment = await api<{ provisioning_uri: string }>(`/users/${user.id}/enrollment`, {
        method: "POST",
        body: "{}",
      });
      const dataUrl = await QRCode.toDataURL(enrollment.provisioning_uri, { width: 260, margin: 1 });
      setProvisioning({ userId: user.id, uri: enrollment.provisioning_uri });
      setQr(dataUrl);
      setShowNew(false);
      event.currentTarget.reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create user");
    }
  }

  async function simpleAction(user: User, action: "disable" | "enable" | "unlock" | "revoke") {
    const reason = window.prompt(`Reason for ${action}:`);
    if (!reason) return;
    try {
      await api<User>(`/users/${user.id}/${action}`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    }
  }

  async function beginEnrollment(user: User) {
    try {
      const enrollment = await api<{ provisioning_uri: string }>(`/users/${user.id}/enrollment`, {
        method: "POST",
        body: "{}",
      });
      const dataUrl = await QRCode.toDataURL(enrollment.provisioning_uri, { width: 260, margin: 1 });
      setProvisioning({ userId: user.id, uri: enrollment.provisioning_uri });
      setQr(dataUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start enrollment");
    }
  }

  async function verify() {
    if (!provisioning) return;
    const otp = window.prompt("Enter the one-time code shown by the authenticator app:");
    if (!otp) return;
    try {
      await api<User>(`/users/${provisioning.userId}/verify`, {
        method: "POST",
        body: JSON.stringify({ otp }),
      });
      setProvisioning(null);
      setQr(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    }
  }

  async function deleteUser(user: User) {
    const reason = window.prompt("Reason for deleting this user:");
    if (!reason || !window.confirm(`Delete ${user.username} from Bliss Secure MFA?`)) return;
    try {
      await api<void>(`/users/${user.id}?reason=${encodeURIComponent(reason)}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <Shell title="RDP Users">
      <div className="toolbar">
        <div><strong>{users.length} local user records</strong><div className="muted">Protected users consume RDP seats.</div></div>
        <button className="primary" onClick={() => setShowNew((value) => !value)}>+ Add RDP user</button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {showNew ? (
        <form className="card formCard" onSubmit={createUser}>
          <label>Username<input name="username" required placeholder="jsmith" /></label>
          <label>Display name<input name="display_name" placeholder="John Smith" /></label>
          <label>Email<input name="email" type="email" placeholder="john@example.com" /></label>
          <button className="primary" type="submit">Create</button>
        </form>
      ) : null}

      {provisioning ? (
        <section className="card stack" style={{ marginBottom: 14 }}>
          <div>
            <p className="eyebrow">Enrollment</p>
            <h2>Scan this QR code locally</h2>
            <p className="muted">Provisioning information is shown only for a pending user. Do not email or screenshot it unless your office policy explicitly permits that.</p>
          </div>
          {qr ? <img className="qr" src={qr} alt="Authenticator enrollment QR code" /> : null}
          <details><summary>Manual provisioning URI</summary><code className="codeBox">{provisioning.uri}</code></details>
          <div className="actions">
            <button className="primary" onClick={verify}>Verify first code</button>
            <button className="secondary" onClick={() => { setProvisioning(null); setQr(null); }}>Close</button>
          </div>
        </section>
      ) : null}

      <section className="card table">
        <div className="headerRow userGrid"><span>User</span><span>Status</span><span>Email</span><span>Actions</span></div>
        {users.map((user) => (
          <div className="row userGrid" key={user.id}>
            <div className="nameBlock"><strong>{user.display_name || user.username}</strong><small>{user.username}</small></div>
            <span className={`pill ${user.status}`}>{user.status}</span>
            <span>{user.email || "—"}</span>
            <div className="actions">
              {user.status === "disabled"
                ? <button onClick={() => simpleAction(user, "enable")}>Enable</button>
                : <button onClick={() => simpleAction(user, "disable")}>Disable</button>}
              <button onClick={() => simpleAction(user, "unlock")}>Unlock</button>
              {user.status === "pending" ? <button onClick={() => beginEnrollment(user)}>Enroll</button> : null}
              <button onClick={() => simpleAction(user, "revoke")}>Revoke</button>
              <button className="dangerLink" onClick={() => deleteUser(user)}>Delete</button>
            </div>
          </div>
        ))}
        {users.length === 0 ? <div className="empty">No RDP users configured yet.</div> : null}
      </section>
    </Shell>
  );
}
