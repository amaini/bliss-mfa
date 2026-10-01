"use client";

import { useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { api } from "../../lib/api";

type Progress = {
  complete: boolean;
  steps: { id: string; title: string; complete: boolean; href: string }[];
  active_users: { id: string; username: string }[];
};

export default function OnboardingPage() {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [tested, setTested] = useState(false);
  const [saving, setSaving] = useState(false);
  async function load() {
    try { setProgress(await api<Progress>("/onboarding")); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to load setup progress"); }
  }
  useEffect(() => { load(); }, []);
  async function confirm() {
    setSaving(true); setError(null);
    try { await api(`/onboarding/rdp/${encodeURIComponent(selected)}`, { method: "POST" }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Unable to confirm RDP test"); }
    finally { setSaving(false); }
  }
  return <Shell title="Get started">
    {error ? <div className="notice" role="alert">{error}</div> : null}
    <section className="card stack">
      <h2>{progress?.complete ? "Your first user is ready" : "Set up your office MFA"}</h2>
      <p className="muted">Follow these steps on your Windows server. Your authenticator keys stay in your environment.</p>
      <ol>{progress?.steps.map(step => <li key={step.id}>
        <a href={step.href}>{step.title}</a> — {step.complete ? "Complete" : "To do"}
      </li>)}</ol>
    </section>
    <section className="card stack">
      <h2>Verify protected Windows access</h2>
      <p>Keep your recovery administrator session available. Install and configure the Bliss credential provider before testing.</p>
      <ol>
        <li>Add the existing Windows account on the RDP Users page.</li>
        <li>Scan its QR code and verify a fresh authenticator code. Wait for the next code before signing in.</li>
        <li>Connect through RDP with that account and its Windows password. Enter the fresh code at the MFA prompt.</li>
        <li>Confirm the desktop opens. Then confirm that an incorrect or empty code denies access.</li>
      </ol>
      <label>Tested account<select value={selected} onChange={e => { setSelected(e.target.value); setTested(false); }}>
        <option value="">Select an enrolled account</option>
        {progress?.active_users.map(user => <option key={user.id} value={user.id}>{user.username}</option>)}
      </select></label>
      <label><input type="checkbox" checked={tested} onChange={e => setTested(e.target.checked)} /> I tested successful RDP sign-in and incorrect OTP rejection for this account.</label>
      <button className="primary" disabled={!selected || !tested || saving} onClick={confirm}>{saving ? "Saving…" : "Confirm test as owner"}</button>
      <p className="muted">This records your test confirmation in the local audit log.</p>
    </section>
  </Shell>;
}
