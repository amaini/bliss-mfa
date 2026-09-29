"use client";

import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        email: String(form.get("email") ?? ""),
        password: String(form.get("password") ?? ""),
      }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body.detail ?? "Unable to sign in");
      return;
    }

    window.location.assign("/");
  }

  return (
    <main className="loginWrap">
      <form className="loginCard" onSubmit={submit}>
        <div className="brand loginBrand">
          <span className="brandMark">B</span>
          <div>
            <strong>Bliss Secure MFA</strong>
            <small>Local Appliance</small>
          </div>
        </div>
        <h1>Sign in</h1>
        <p>This management portal is hosted inside your office environment.</p>
        {error ? <div className="notice">{error}</div> : null}
        <label>
          Email
          <input name="email" type="email" required autoComplete="username" />
        </label>
        <label>
          Password
          <input name="password" type="password" required autoComplete="current-password" />
        </label>
        <button className="primary" type="submit">Sign in</button>
      </form>
    </main>
  );
}
