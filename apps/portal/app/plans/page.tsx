"use client";

import { FormEvent, useState } from "react";
import { CheckoutButton } from "../../components/CheckoutButton";

const plans = [
  {
    code: "starter" as const,
    name: "Starter",
    seats: 10,
    description: "Small offices and professional teams.",
  },
  {
    code: "business" as const,
    name: "Business",
    seats: 50,
    description: "Growing organizations with centralized MFA operations.",
  },
  {
    code: "business_plus" as const,
    name: "Business+",
    seats: 100,
    description: "Larger environments that need managed onboarding at scale.",
  },
];

export default function PlansPage() {
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [selectedPlan, setSelectedPlan] =
    useState<(typeof plans)[number]["code"]>("starter");
  const [ready, setReady] = useState(false);

  function continueToCheckout(event: FormEvent) {
    event.preventDefault();
    setReady(true);
  }

  return (
    <main className="publicPage">
      <div className="publicNav">
        <strong>Bliss Secure MFA</strong>
        <a href="/">Management portal</a>
      </div>

      <section className="hero">
        <p className="eyebrow">Managed multi-factor authentication</p>
        <h1>Protect business access without adding operational complexity.</h1>
        <p>
          Centralized MFA onboarding, recovery, revocation and audit controls,
          managed by Bliss IT Solutions.
        </p>
      </section>

      <section className="plans">
        {plans.map((plan) => (
          <button
            className={`plan ${selectedPlan === plan.code ? "selected" : ""}`}
            key={plan.code}
            onClick={() => {
              setSelectedPlan(plan.code);
              setReady(false);
            }}
          >
            <span>{plan.name}</span>
            <strong>Up to {plan.seats} users</strong>
            <small>{plan.description}</small>
          </button>
        ))}
      </section>

      <form className="checkoutForm card" onSubmit={continueToCheckout}>
        <div>
          <label htmlFor="company">Company</label>
          <input
            id="company"
            required
            value={companyName}
            onChange={(event) => {
              setCompanyName(event.target.value);
              setReady(false);
            }}
          />
        </div>
        <div>
          <label htmlFor="email">Billing / admin email</label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setReady(false);
            }}
          />
        </div>

        {ready ? (
          <CheckoutButton
            planCode={selectedPlan}
            companyName={companyName}
            email={email}
          />
        ) : (
          <button className="primary" type="submit">Review checkout</button>
        )}
      </form>
    </main>
  );
}
