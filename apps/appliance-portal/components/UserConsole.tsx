"use client";

import { FormEvent, useEffect, useState } from "react";
import QRCode from "qrcode";

import { Shell } from "./Shell";
import { api } from "../lib/api";

type User = {
  id: string;
  username: string;
  display_name: string | null;
  email: string | null;
  status: string;
  protected_rdp: boolean;
  created_at: string;
};

type WindowsAccount = {
  username: string;
  display_name: string | null;
  enabled: boolean;
  enrolled: boolean;
};

type UserAction = "disable" | "enable" | "unlock" | "revoke" | "delete";
const actionLabels: Record<UserAction, string> = {
  disable: "Disable OTP for", enable: "Re-enable OTP for", unlock: "Unlock", revoke: "Revoke OTP for", delete: "Delete",
};

export default function UserConsole({ title = "RDP Users" }: { title?: string }) {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [qr, setQr] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState<{ userId: string; username: string; uri: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [action, setAction] = useState<{ user: User; kind: UserAction } | null>(null);
  const [events, setEvents] = useState<{ id: string; action: string; created_at: string; success: boolean }[]>([]);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [windowsAccounts, setWindowsAccounts] = useState<WindowsAccount[] | null>(null);
  const [windowsAccountError, setWindowsAccountError] = useState<string | null>(null);
  const [scanningWindowsAccounts, setScanningWindowsAccounts] = useState(false);
  const managedUsers = users.filter((user) => !["disabled", "revoked"].includes(user.status));
  const inactiveUsers = users.filter((user) => ["disabled", "revoked"].includes(user.status));

  function closeEnrollment() { setProvisioning(null); setQr(null); }

  function openAction(user: User, kind: UserAction) {
    closeEnrollment();
    setShowNew(false);
    setError(null);
    setMessage(null);
    setAction({ user, kind });
  }

  async function load() {
    try {
      setUsers(await api<User[]>("/users"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load users");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function discoverWindowsAccounts() {
    setWindowsAccountError(null);
    setScanningWindowsAccounts(true);
    try {
      setWindowsAccounts(await api<WindowsAccount[]>("/windows-users"));
    } catch (err) {
      setWindowsAccountError(err instanceof Error ? err.message : "Unable to discover Windows accounts");
    } finally {
      setScanningWindowsAccounts(false);
    }
  }

  async function addWindowsAccount(account: WindowsAccount) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const user = await api<User>("/users", {
        method: "POST",
        body: JSON.stringify({ username: account.username, display_name: account.display_name, email: null }),
      });
      setWindowsAccounts((current) => current
        ? current.map((entry) =>
            entry.username.toLowerCase() === account.username.toLowerCase()
              ? { ...entry, enrolled: true }
              : entry)
        : current);
      await load();
      const enrollment = await api<{ provisioning_uri: string }>(`/users/${user.id}/enrollment`, {
        method: "POST",
        body: "{}",
      });
      setProvisioning({ userId: user.id, username: user.username, uri: enrollment.provisioning_uri });
      setQr(await QRCode.toDataURL(enrollment.provisioning_uri, { width: 260, margin: 1 }));
      setMessage(`MFA record created for ${user.username}. Scan the QR code to finish enrollment.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start enrollment");
      await load();
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (title === "Dashboard") {
      api<typeof events>("/audit?limit=8").then(setEvents)
        .catch((err) => setAuditError(err instanceof Error ? err.message : "Unable to load recent events"));
    }
  }, [title]);

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    setBusy(true);
    closeEnrollment();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const user = await api<User>("/users", {
        method: "POST",
        body: JSON.stringify({
          username: String(form.get("username") ?? "").trim(),
          display_name: String(form.get("display_name") ?? "").trim() || null,
          email: String(form.get("email") ?? "").trim() || null,
        }),
      });
      // Refresh immediately so a provisioning failure still leaves the created
      // pending record visible and available for an enrollment retry.
      await load();
      const enrollment = await api<{ provisioning_uri: string }>(`/users/${user.id}/enrollment`, {
        method: "POST",
        body: "{}",
      });
      const dataUrl = await QRCode.toDataURL(enrollment.provisioning_uri, { width: 260, margin: 1 });
      setProvisioning({ userId: user.id, username: user.username, uri: enrollment.provisioning_uri });
      setQr(dataUrl);
      formElement.reset();
      setShowNew(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create user");
    } finally {
      setBusy(false);
    }
  }

  async function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action) return;
    const { user, kind } = action;
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    if (!reason) { setError("Enter a reason for this action."); return; }
    setBusy(true);
    setError(null);
    setMessage(null);
    closeEnrollment();
    try {
      if (kind === "delete") {
        await api<void>(`/users/${user.id}?reason=${encodeURIComponent(reason)}`, { method: "DELETE" });
      } else {
        await api<User>(`/users/${user.id}/${kind}`, { method: "POST", body: JSON.stringify({ reason }) });
      }
      setAction(null);
      setMessage(`${actionLabels[kind]} ${user.username}: completed.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
      setAction(null);
      // A partial revoke can fail while persisting the safe revoked state.
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function beginEnrollment(user: User) {
    setAction(null);
    setShowNew(false);
    setBusy(true);
    setError(null);
    setMessage(null);
    closeEnrollment();
    try {
      const enrollment = await api<{ provisioning_uri: string }>(`/users/${user.id}/enrollment`, {
        method: "POST",
        body: "{}",
      });
      const dataUrl = await QRCode.toDataURL(enrollment.provisioning_uri, { width: 260, margin: 1 });
      setProvisioning({ userId: user.id, username: user.username, uri: enrollment.provisioning_uri });
      setQr(dataUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start enrollment");
    } finally {
      setBusy(false);
    }
  }

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!provisioning) return;
    const otp = String(new FormData(event.currentTarget).get("otp") ?? "").trim();
    setBusy(true);
    setError(null);
    try {
      await api<User>(`/users/${provisioning.userId}/verify`, {
        method: "POST",
        body: JSON.stringify({ otp }),
      });
      setMessage(`Enrollment verified for ${provisioning.username}.`);
      closeEnrollment();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  function userTable(records: User[], caption: string) {
    return (
      <div className="card table">
        <table className="usersTable">
          <caption className="srOnly">{caption}</caption>
          <thead><tr><th scope="col">Account</th><th scope="col">OTP status</th><th scope="col">RDP seat</th><th scope="col">Actions</th></tr></thead>
          <tbody>{records.map((user) => (
            <tr key={user.id}>
              <td><div className="nameBlock"><strong>{user.display_name || user.username}</strong><small>{user.username}</small>{user.email ? <small>{user.email}</small> : null}</div></td>
              <td data-label="OTP status"><span className={`pill ${user.status}`}>{user.status === "pending" ? "Not enrolled" : user.status.charAt(0).toUpperCase() + user.status.slice(1)}</span></td>
              <td data-label="RDP seat">{user.protected_rdp && ["pending", "active", "locked"].includes(user.status) ? "In use" : "Not in use"}</td>
              <td><div className="actions">
                {user.status === "pending" ? <button className="primary" disabled={busy} onClick={() => beginEnrollment(user)}>Enrollment</button> : null}
                {user.status === "disabled" ? <button className="success" disabled={busy} onClick={() => openAction(user, "enable")}>Re-enable OTP</button> : null}
                {user.status === "active" || user.status === "locked" ? <button disabled={busy} onClick={() => openAction(user, "disable")}>Disable OTP</button> : null}
                {user.status === "active" || user.status === "locked" ? <button disabled={busy} onClick={() => openAction(user, "unlock")}>Unlock</button> : null}
                {user.status !== "revoked" ? <button disabled={busy} onClick={() => openAction(user, "revoke")}>Revoke</button> : null}
                <button className="dangerLink" disabled={busy} onClick={() => openAction(user, "delete")}>Delete</button>
              </div></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    );
  }

  return (
    <Shell title={title}>
      <div className="toolbar">
        <div><strong>{loading ? "Loading accounts…" : `${users.length} MFA accounts`}</strong><div className="muted">Manage enrollment and OTP access for your RDP users.</div></div>
        <button className="primary" disabled={busy} onClick={() => { setAction(null); closeEnrollment(); setShowNew((value) => !value); }}>{showNew ? "Cancel new user" : "+ New user"}</button>
      </div>

      {error ? <div className="notice" role="alert">{error}</div> : null}
      {message ? <div className="notice goodNotice" role="status">{message}</div> : null}

      <section className="userSection" aria-labelledby="windows-accounts-title">
        <div className="sectionHeading windowsAccountsHeading">
          <div><h2 id="windows-accounts-title">Windows accounts</h2><p className="muted">Read-only discovery of local accounts on this computer. Domain accounts are not included.</p></div>
          <button className="secondary" disabled={scanningWindowsAccounts || busy} onClick={discoverWindowsAccounts}>
            {scanningWindowsAccounts ? "Scanning…" : "Detect accounts"}
          </button>
        </div>
        {windowsAccountError ? <div className="notice" role="alert">{windowsAccountError}</div> : null}
        {windowsAccounts?.length ? <div className="card windowsAccountsList">
          {windowsAccounts.map((account) => (
            <div className="row windowsAccountRow" key={account.username}>
              <div className="nameBlock"><strong>{account.display_name || account.username}</strong><small>{account.username}{account.enabled ? " · enabled" : " · disabled"}</small></div>
              <button className="primary" disabled={!account.enabled || account.enrolled || busy}
                onClick={() => addWindowsAccount(account)}>
                {account.enrolled ? "Already added" : !account.enabled ? "Account disabled" : busy ? "Starting…" : "Enroll in MFA"}
              </button>
            </div>
          ))}
        </div> : null}
        {windowsAccounts?.length === 0 ? <p className="muted">No local Windows accounts were found.</p> : null}
      </section>

      {action ? (
        <form key={`${action.user.id}:${action.kind}`} className="card stack actionPanel" onSubmit={submitAction} aria-labelledby="action-title">
          <div><p className="eyebrow">Confirm action</p><h2 id="action-title">{actionLabels[action.kind]} {action.user.username}?</h2>
            {action.kind === "delete" ? <p className="muted">This removes the MFA record and enrollment. The user will need a new enrollment to restore OTP access.</p> : null}
            {action.kind === "revoke" ? <p className="muted">This disables OTP access and removes the current token. Restoring access requires deleting and creating the MFA user again.</p> : null}
          </div>
          <label>Reason<input name="reason" required placeholder="Recorded in the audit log" autoFocus /></label>
          <div className="actions"><button type="submit" className={["delete", "revoke"].includes(action.kind) ? "danger" : "primary"} disabled={busy}>{busy ? "Applying…" : "Confirm action"}</button><button type="button" disabled={busy} onClick={() => setAction(null)}>Cancel</button></div>
        </form>
      ) : null}

      {showNew ? (
        <form className="card formCard" onSubmit={createUser}>
          <div className="formHeading"><h2>New MFA user</h2><p className="muted">Create the MFA record, then enroll an authenticator.</p></div>
          <label>Username<input name="username" required placeholder="jsmith" /></label>
          <label>Display name<input name="display_name" placeholder="John Smith" /></label>
          <label>Email<input name="email" type="email" placeholder="john@example.com" /></label>
          <button className="primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create & enroll"}</button>
        </form>
      ) : null}

      {provisioning ? (
        <section className="card stack enrollment" aria-labelledby="enrollment-title">
          <div>
            <p className="eyebrow">Enrollment</p>
            <h2 id="enrollment-title">Enroll {provisioning.username}</h2>
            <p className="muted">Keep this enrollment information private.</p>
          </div>
          <div className="enrollmentGrid">
            {qr ? <img className="qr" src={qr} alt={`Authenticator enrollment QR code for ${provisioning.username}`} /> : null}
            <div className="enrollmentSteps">
              <p><strong>1. Add to your authenticator</strong><br /><span className="muted">Scan the QR code to add this account.</span></p>
              <details><summary>Manual setup</summary><code className="codeBox">{provisioning.uri}</code></details>
              <form className="otpForm" onSubmit={verify}>
                <label>2. Enter the first one-time code<input name="otp" inputMode="numeric" autoComplete="one-time-code" required placeholder="Code from your authenticator" /></label>
                <div className="actions"><button className="primary" type="submit" disabled={busy}>{busy ? "Verifying…" : "Verify enrollment"}</button><button type="button" disabled={busy} onClick={closeEnrollment}>Close</button></div>
              </form>
            </div>
          </div>
        </section>
      ) : null}

      <section className="userSection" aria-labelledby="accounts-title">
        <div className="sectionHeading"><h2 id="accounts-title">MFA accounts</h2>{!loading ? <span className="count">{managedUsers.length} enrolled or awaiting enrollment</span> : null}</div>
        {loading ? <div className="card empty" role="status">Loading MFA accounts…</div> : managedUsers.length ? userTable(managedUsers, "Active and pending MFA accounts") : <div className="card empty">{error ? "Accounts could not be loaded." : "No active MFA accounts. Add a new user to begin enrollment."}</div>}
      </section>
      {inactiveUsers.length ? <details className="inactiveAccounts"><summary>Disabled & revoked accounts ({inactiveUsers.length})</summary>{userTable(inactiveUsers, "Disabled and revoked MFA accounts")}<p className="muted">Revoked users must be deleted and created again before a new enrollment.</p></details> : null}
      {title === "Dashboard" ? <section className="userSection" aria-labelledby="events-title">
        <div className="sectionHeading"><h2 id="events-title">Recent Events</h2><a href="/audit">View audit history</a></div>
        {auditError ? <p className="notice" role="alert">{auditError}</p> : events.length ? <ul className="recentEvents">{events.map((event) => <li key={event.id}><strong>{event.action}</strong><span>{new Date(event.created_at).toLocaleString()}</span><span className={`pill ${event.success ? "active" : "locked"}`}>{event.success ? "Success" : "Failed"}</span></li>)}</ul> : <p className="muted">No activity recorded yet.</p>}
      </section> : null}
    </Shell>
  );
}
