"use client";

import { useState } from "react";

type Props = {
  planCode: "starter" | "business" | "business_plus";
  companyName: string;
  email: string;
};

export function CheckoutButton({ planCode, companyName, email }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startCheckout() {
    setBusy(true);
    setError(null);
    try {
      const api = process.env.NEXT_PUBLIC_API_BASE_URL;
      if (!api) throw new Error("Portal API URL is not configured");

      const response = await fetch(`${api}/v1/billing/checkout`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          company_name: companyName,
          email,
          plan_code: planCode,
        }),
      });

      if (!response.ok) throw new Error("Unable to start secure checkout");
      const body = await response.json();
      window.location.assign(body.checkout_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed");
      setBusy(false);
    }
  }

  return (
    <div>
      <button className="primary" disabled={busy} onClick={startCheckout}>
        {busy ? "Opening Stripe…" : "Continue to secure checkout"}
      </button>
      {error ? <p className="formError">{error}</p> : null}
    </div>
  );
}
