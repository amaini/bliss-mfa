"use client";

import { FormEvent, useEffect, useState } from "react";
import QRCode from "qrcode";

import { api } from "../lib/api";

export type Provisioning = { userId: string; username: string; uri: string };

/** Starts QR enrollment for a pending MFA user (shared by RDP Users and Windows Accounts). */
export async function startEnrollment(userId: string, username: string): Promise<Provisioning> {
  const enrollment = await api<{ provisioning_uri: string }>(`/users/${userId}/enrollment`, {
    method: "POST",
    body: "{}",
  });
  return { userId, username, uri: enrollment.provisioning_uri };
}

export function EnrollmentPanel({ provisioning, onVerified, onClose }: {
  provisioning: Provisioning;
  onVerified: (username: string) => void;
  onClose: () => void;
}) {
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setQr(null);
    QRCode.toDataURL(provisioning.uri, { width: 260, margin: 1 })
      .then((dataUrl) => { if (!cancelled) setQr(dataUrl); })
      .catch(() => { if (!cancelled) setError("Unable to draw the QR code. Use manual setup instead."); });
    return () => { cancelled = true; };
  }, [provisioning.uri]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const otp = String(new FormData(event.currentTarget).get("otp") ?? "").trim();
    setBusy(true);
    setError(null);
    try {
      await api(`/users/${provisioning.userId}/verify`, { method: "POST", body: JSON.stringify({ otp }) });
      onVerified(provisioning.username);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack enrollment" aria-labelledby="enrollment-title">
      <div>
        <p className="eyebrow">Enrollment</p>
        <h2 id="enrollment-title">Enroll {provisioning.username}</h2>
        <p className="muted">Keep this enrollment information private.</p>
      </div>
      {error ? <div className="notice" role="alert">{error}</div> : null}
      <div className="enrollmentGrid">
        {qr ? <img className="qr" src={qr} alt={`Authenticator enrollment QR code for ${provisioning.username}`} /> : null}
        <div className="enrollmentSteps">
          <p><strong>1. Add to your authenticator</strong><br /><span className="muted">Scan the QR code to add this account.</span></p>
          <details><summary>Manual setup</summary><code className="codeBox">{provisioning.uri}</code></details>
          <form className="otpForm" onSubmit={verify}>
            <label>2. Enter the first one-time code<input name="otp" inputMode="numeric" autoComplete="one-time-code" required placeholder="Code from your authenticator" /></label>
            <div className="actions"><button className="primary" type="submit" disabled={busy}>{busy ? "Verifying…" : "Verify enrollment"}</button><button type="button" disabled={busy} onClick={onClose}>Close</button></div>
          </form>
        </div>
      </div>
    </section>
  );
}
