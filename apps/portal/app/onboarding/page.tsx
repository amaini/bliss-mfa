"use client";

import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

type SignupStatus = {
  status: string;
  company_name: string;
  email: string;
  plan_code: string;
};

export default function OnboardingPage() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const api = process.env.NEXT_PUBLIC_API_BASE_URL;
  const [signup, setSignup] = useState<SignupStatus | null>(null);
  const [slug, setSlug] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api || !token) return;

    fetch(`${api}/v1/billing/onboarding-status?token=${encodeURIComponent(token)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Onboarding session is not available");
        return response.json();
      })
      .then((body) => {
        setSignup(body);
        setSlug(
          body.company_name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/(^-|-$)/g, "")
        );
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Unable to load onboarding")
      );
  }, [api, token]);

  async function complete(event: FormEvent) {
    event.preventDefault();
    if (!api) return;

    setError(null);
    const response = await fetch(`${api}/v1/billing/complete-onboarding`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        onboarding_token: token,
        organization_slug: slug,
      }),
    });

    const body = await response.json();
    if (!response.ok) {
      setError(body.detail ?? "Unable to complete onboarding");
      return;
    }

    setResult(
      `Organization ${body.organization_slug} is ready with ${body.seat_limit} seats.`
    );
  }

  if (error) {
    return <main className="publicPage"><div className="card">{error}</div></main>;
  }

  if (!signup) {
    return (
      <main className="publicPage">
        <div className="card">Loading secure onboarding…</div>
      </main>
    );
  }

  return (
    <main className="publicPage narrow">
      <p className="eyebrow">Bliss Secure MFA</p>
      <h1>Finish organization setup</h1>
      <div className="card onboardingCard">
        <dl className="health">
          <div><dt>Company</dt><dd>{signup.company_name}</dd></div>
          <div><dt>Plan</dt><dd>{signup.plan_code}</dd></div>
          <div><dt>Payment</dt><dd>{signup.status}</dd></div>
        </dl>

        {signup.status === "paid_pending_setup" && !result ? (
          <form onSubmit={complete}>
            <label htmlFor="slug">Organization URL name</label>
            <input
              id="slug"
              required
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
            <button className="primary" type="submit">
              Create MFA organization
            </button>
          </form>
        ) : null}

        {result ? <p className="successMessage">{result}</p> : null}
      </div>
    </main>
  );
}
