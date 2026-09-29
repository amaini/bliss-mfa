"use client";

import { FormEvent, useState } from "react";

export default function SetupPage() {
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/bootstrap", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        setup_token: String(form.get("setup_token") ?? ""),
        email: String(form.get("email") ?? ""),
        display_name: String(form.get("display_name") ?? "") || null,
        password: String(form.get("password") ?? ""),
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail ?? "Setup failed");
      return;
    }
    window.location.assign("/");
  }

  return (
    <main className="loginWrap">
      <form className="loginCard" onSubmit={submit}>
        <div className="brand loginBrand">
          <span className="brandMark">B</span>
          <div><strong>Bliss Secure MFA</strong><small>First-time setup</small></div>
        </div>
        <h1>Create the office owner</h1>
        <p>This can only be completed before any local administrator exists.</p>
        {error ? <div className="notice">{error}</div> : null}
        <label>Setup token<input name="setup_token" type="password" required /></label>
        <label>Owner name<input name="display_name" /></label>
        <label>Owner email<input name="email" type="email" required /></label>
        <label>Password<input name="password" type="password" minLength={12} required /></label>
        <button className="primary" type="submit">Initialize appliance</button>
      </form>
    </main>
  );
}
