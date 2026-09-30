"use client";

import { FormEvent, useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { api } from "../../lib/api";

type License = {
  state: string;
  max_rdp_users: number;
  license_type: string | null;
  license_id: string | null;
  lease_expires_at?: string;
  grace_expires_at?: string | null;
};

type Stats = {
  protected_rdp_users: number;
};

export default function LicensePage() {
  const [license, setLicense] = useState<License | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [offlineCode, setOfflineCode] = useState<string | null>(null);
  const [releaseCode, setReleaseCode] = useState<string | null>(null);
  const [transferActivationCode, setTransferActivationCode] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [nextLicense, nextStats] = await Promise.all([
        api<License>("/license/status"),
        api<Stats>("/stats"),
      ]);
      setLicense(nextLicense);
      setStats(nextStats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load license");
    }
  }

  useEffect(() => { load(); }, []);

  async function activateOnline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    try {
      await api("/license/activate/online", {
        method: "POST",
        body: JSON.stringify({ activation_code: String(form.get("activation_code") ?? "") }),
      });
      setMessage("Online license activated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Activation failed");
    }
  }

  async function createOfflineRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    try {
      const result = await api<{ installation_code: string }>("/license/offline/request", {
        method: "POST",
        body: JSON.stringify({ activation_code: String(form.get("activation_code") ?? "") }),
      });
      setOfflineCode(result.installation_code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create offline request");
    }
  }

  async function applyOffline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    try {
      await api("/license/offline/apply", {
        method: "POST",
        body: JSON.stringify({ activation_response: String(form.get("activation_response") ?? "") }),
      });
      setMessage("Offline license activated.");
      setOfflineCode(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Offline activation failed");
    }
  }

  async function manageSubscription() {
    try {
      const result = await api<{ url: string }>("/license/billing", {
        method: "POST",
        body: "{}",
      });
      window.location.assign(result.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Billing portal unavailable");
    }
  }

  async function heartbeat() {
    try {
      await api("/license/heartbeat", { method: "POST", body: "{}" });
      setMessage("License validation completed.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    }
  }


  async function releaseOffline() {
    if (!window.confirm("Deactivate this offline license on this appliance?")) return;
    try {
      const result = await api<{ release_code: string }>("/license/offline/release-code", {
        method: "POST",
        body: "{}",
      });
      setReleaseCode(result.release_code);
      setMessage("This appliance has locally released the offline license. Send the release code to Bliss to transfer it.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Offline release failed");
    }
  }

  async function release() {
    if (!window.confirm("Deactivate this license so it can be transferred to another appliance?")) return;
    try {
      const result = await api<{ replacement_activation_code: string }>("/license/release", {
        method: "POST",
        body: "{}",
      });
      setTransferActivationCode(result.replacement_activation_code);
      setMessage("License released from this appliance.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Release failed");
    }
  }

  return (
    <Shell title="License & Billing">
      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice goodNotice">{message}</div> : null}

      <section className="licenseHero">
        <article className="card">
          <p className="eyebrow">Current license</p>
          <h2>{license?.state ?? "Loading..."}</h2>
          <p className="muted">Type: {license?.license_type ?? "Not activated"}</p>
          <div className="licenseNumbers">
            <div className="metricBox"><span>Protected RDP users</span><strong>{stats?.protected_rdp_users ?? "—"}</strong></div>
            <div className="metricBox"><span>Licensed RDP seats</span><strong>{license?.max_rdp_users ?? "—"}</strong></div>
          </div>
        </article>

        <article className="card stack">
          <p className="eyebrow">Subscription</p>
          <button className="primary" onClick={manageSubscription}>Manage subscription / buy more users</button>
          {license?.license_type === "online" ? <button className="secondary" onClick={heartbeat}>Validate license now</button> : null}
          {license?.license_type === "online" && license?.license_id ? <button className="danger" onClick={release}>Deactivate / transfer license</button> : null}
          {license?.license_type === "offline" && license?.license_id ? <button className="danger" onClick={releaseOffline}>Deactivate offline license</button> : null}
          <p className="muted">Credit-card details are handled on the hosted billing portal, not by this appliance.</p>
        </article>
      </section>

      {!license?.license_id ? (
        <section className="grid">
          <form className="card stack" onSubmit={activateOnline}>
            <div><p className="eyebrow">Online activation</p><h2>Internet-connected office</h2></div>
            <label>Activation code<input name="activation_code" required placeholder="BLS-..." /></label>
            <button className="primary" type="submit">Activate online</button>
          </form>

          <form className="card stack" onSubmit={createOfflineRequest}>
            <div><p className="eyebrow">Offline activation</p><h2>Air-gapped office</h2></div>
            <label>Activation code<input name="activation_code" required placeholder="BLS-..." /></label>
            <button className="secondary" type="submit">Generate installation code</button>
          </form>
        </section>
      ) : null}

      {offlineCode ? (
        <section className="card stack" style={{ marginTop: 16 }}>
          <div>
            <p className="eyebrow">Offline request</p>
            <h2>Send this installation code to Bliss IT Solutions</h2>
          </div>
          <code className="codeBox">{offlineCode}</code>
          <form className="stack" onSubmit={applyOffline}>
            <label>Activation response
              <input name="activation_response" required placeholder="Paste the response from Bliss" />
            </label>
            <button className="primary" type="submit">Apply offline license</button>
          </form>
        </section>
      ) : null}


      {transferActivationCode ? (
        <section className="card stack" style={{ marginTop: 16 }}>
          <div>
            <p className="eyebrow">Transfer ready</p>
            <h2>Use this activation code on the replacement appliance</h2>
          </div>
          <code className="codeBox">{transferActivationCode}</code>
          <p className="muted">Treat this one-time code as a licensing credential until the new appliance consumes it.</p>
        </section>
      ) : null}
      {releaseCode ? (
        <section className="card stack" style={{ marginTop: 16 }}>
          <div>
            <p className="eyebrow">Offline release</p>
            <h2>Send this release code to Bliss IT Solutions</h2>
            <p className="muted">Bliss verifies the code against this appliance key before the license can be transferred.</p>
          </div>
          <code className="codeBox">{releaseCode}</code>
        </section>
      ) : null}
    </Shell>
  );
}
