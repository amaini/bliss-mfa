"use client";

import { useEffect, useState } from "react";

import { Shell } from "./Shell";
import { RdpProtection } from "./RdpProtection";
import { EnrollmentPanel, Provisioning, startEnrollment } from "./EnrollmentPanel";
import { api } from "../lib/api";

type AccountState = "not_enrolled" | "pending" | "enrolled" | "mfa_inactive" | "disabled_account";

type WindowsAccount = {
  username: string;
  display_name: string | null;
  enabled: boolean;
  mfa_user_id: string | null;
  mfa_status: string | null;
  state: AccountState;
};

// "MFA enrolled" means the authenticator was verified. It deliberately does not say the account is
// protected: Windows sign-in enforcement depends on the Credential Provider / RDP protection setup.
function stateLabel(account: WindowsAccount): { text: string; pill: string } {
  switch (account.state) {
    case "disabled_account": return { text: "Disabled account", pill: "disabled" };
    case "not_enrolled": return { text: "Not enrolled", pill: "disabled" };
    case "pending": return { text: "Enrollment pending", pill: "pending" };
    case "enrolled": return account.mfa_status === "locked"
      ? { text: "MFA enrolled · locked", pill: "locked" }
      : { text: "MFA enrolled", pill: "active" };
    case "mfa_inactive": return { text: account.mfa_status === "revoked" ? "MFA revoked" : "MFA disabled", pill: "disabled" };
  }
}

export default function WindowsAccounts() {
  const [accounts, setAccounts] = useState<WindowsAccount[] | null>(null);
  const [verifiedUser, setVerifiedUser] = useState<string | undefined>(undefined);
  const [rdpRefresh, setRdpRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyUser, setBusyUser] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [provisioning, setProvisioning] = useState<Provisioning | null>(null);

  async function load() {
    setLoading(true);
    try {
      setAccounts(await api<WindowsAccount[]>("/windows-users"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to read Windows accounts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function enroll(account: WindowsAccount) {
    setBusyUser(account.username);
    setError(null);
    setMessage(null);
    setProvisioning(null);
    try {
      // The server re-checks the account (exists, enabled, not already enrolled) and the plan limit,
      // and stores the exact Windows account name.
      const user = await api<{ id: string; username: string }>("/users", {
        method: "POST",
        body: JSON.stringify({ username: account.username, display_name: account.display_name, email: null }),
      });
      await load();
      setProvisioning(await startEnrollment(user.id, user.username));
      setMessage(`MFA record created for ${user.username}. Scan the QR code to finish enrollment.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start enrollment");
      await load();
    } finally {
      setBusyUser(null);
    }
  }

  async function continueEnrollment(account: WindowsAccount) {
    if (!account.mfa_user_id) return;
    setBusyUser(account.username);
    setError(null);
    setMessage(null);
    try {
      setProvisioning(await startEnrollment(account.mfa_user_id, account.username));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start enrollment");
    } finally {
      setBusyUser(null);
    }
  }

  const busy = busyUser !== null;
  return (
    <Shell title="Windows Accounts">
      <RdpProtection suggestedUser={verifiedUser} refreshKey={rdpRefresh} />
      <div className="toolbar">
        <div>
          <strong>{loading && !accounts ? "Reading local accounts…" : `${accounts?.length ?? 0} local Windows accounts`}</strong>
          <div className="muted">Local accounts on this computer, matched to MFA records. Domain accounts are not included. Nothing here creates or changes Windows accounts.</div>
        </div>
        <button className="secondary" disabled={loading || busy} onClick={load}>{loading ? "Refreshing…" : "Refresh"}</button>
      </div>

      {error ? <div className="notice" role="alert">{error}</div> : null}
      {message ? <div className="notice goodNotice" role="status">{message}</div> : null}

      {provisioning ? (
        <EnrollmentPanel
          provisioning={provisioning}
          onClose={() => setProvisioning(null)}
          onVerified={(username) => { setProvisioning(null); setMessage(`Enrollment verified for ${username}.`); setVerifiedUser(username); setRdpRefresh((n) => n + 1); load(); }}
        />
      ) : null}

      {accounts?.length ? (
        <div className="card table">
          <table className="usersTable">
            <caption className="srOnly">Local Windows accounts and their MFA enrollment</caption>
            <thead><tr><th scope="col">Account</th><th scope="col">Windows account</th><th scope="col">MFA</th><th scope="col">Actions</th></tr></thead>
            <tbody>{accounts.map((account) => {
              const label = stateLabel(account);
              return (
                <tr key={account.username}>
                  <td><div className="nameBlock"><strong>{account.display_name || account.username}</strong><small>{account.username}</small></div></td>
                  <td data-label="Windows account">{account.enabled ? "Enabled" : "Disabled"}</td>
                  <td data-label="MFA"><span className={`pill ${label.pill}`}>{label.text}</span></td>
                  <td><div className="actions">
                    {account.state === "not_enrolled" ? (
                      <button className="primary" disabled={busy} onClick={() => enroll(account)}>
                        {busyUser === account.username ? "Starting…" : "Enroll MFA"}
                      </button>
                    ) : null}
                    {account.state === "pending" ? (
                      <button className="primary" disabled={busy} onClick={() => continueEnrollment(account)}>
                        {busyUser === account.username ? "Opening…" : "Continue enrollment"}
                      </button>
                    ) : null}
                    {account.state === "mfa_inactive" ? <a href="/users">Manage on RDP Users</a> : null}
                  </div></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      ) : null}
      {accounts?.length === 0 ? <div className="card empty">No local Windows accounts were found.</div> : null}
      <p className="muted">“MFA enrolled” means the authenticator was verified for that account. Whether Windows sign-in
        requires the code is configured separately (RDP protection) and is not shown on this page.</p>
    </Shell>
  );
}
