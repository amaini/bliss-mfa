"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";

type Status = {
  on: boolean;
  recovery_account: string | null;
  protected: string[];
  password_only: string[];
  disabled: string[];
};

/**
 * RDP protection status and the owner's on/off control. Only Remote Desktop sign-in is protected;
 * signing in at the computer itself never asks for a code. After an enrollment is verified, pass
 * that account as `suggestedUser` to offer turning protection on straight away.
 */
export function RdpProtection({ suggestedUser, refreshKey = 0 }: { suggestedUser?: string; refreshKey?: number }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await api<Status>("/rdp-protection"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to read RDP protection status");
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    if (suggestedUser && status && !status.on) {
      setUsername(suggestedUser);
      setOpen(true);
    }
  }, [suggestedUser, status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      if (status?.on) {
        await api("/rdp-protection/disable", { method: "POST", body: JSON.stringify({ password }) });
        setMessage("RDP protection is off. Remote Desktop sign-in no longer asks for codes.");
      } else {
        const otp = String(form.get("otp") ?? "").trim();
        await api("/rdp-protection/enable", { method: "POST", body: JSON.stringify({ password, username, otp }) });
        setMessage("RDP protection is on. Enrolled accounts are asked for a code on a second screen over RDP.");
      }
      setOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  if (!status) return error ? <div className="notice" role="alert">{error}</div> : null;
  return (
    <div className="card">
      <div className="toolbar">
        <div>
          <strong>RDP protection: {status.on ? "On" : "Off"}</strong>
          <div className="muted">
            Only Remote Desktop sign-in is protected. Signing in at the computer itself never asks for a code.
          </div>
        </div>
        {!open ? (
          <button className={status.on ? "secondary" : "primary"} disabled={busy} onClick={() => setOpen(true)}>
            {status.on ? "Turn off RDP protection" : "Turn on RDP protection"}
          </button>
        ) : null}
      </div>
      <p className="muted">
        Code required over RDP: {status.protected.join(", ") || "none"}.{" "}
        Password only over RDP (not enrolled): {status.password_only.join(", ") || "none"}.{" "}
        Recovery account, never asked for a code: {status.recovery_account ?? "not set"}.
      </p>
      {error ? <div className="notice" role="alert">{error}</div> : null}
      {message ? <div className="notice goodNotice" role="status">{message}</div> : null}
      {open ? (
        <form onSubmit={submit}>
          {!status.on && suggestedUser ? <p><strong>Protect RDP sign-in now?</strong></p> : null}
          <label>
            Your portal password
            <input name="password" type="password" autoComplete="current-password" required />
          </label>
          {!status.on ? (
            <>
              <label>
                Enrolled Windows account
                <select value={username} onChange={(e) => setUsername(e.target.value)} required>
                  <option value="">Choose…</option>
                  {status.protected.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
              <label>
                Next code for that account (wait for it to change; a code already used is refused)
                <input name="otp" inputMode="numeric" pattern="\d{6}" maxLength={6} autoComplete="one-time-code" required />
              </label>
              <p className="muted">
                After this, enrolled accounts are asked for a code on a second screen when they connect over RDP.
                Other accounts keep signing in over RDP with their password.
              </p>
            </>
          ) : null}
          <div className="actions">
            <button className="primary" disabled={busy}>{status.on ? "Turn off" : "Turn on"}</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => { setOpen(false); setError(null); }}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
