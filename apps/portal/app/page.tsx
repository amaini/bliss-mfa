const stats = [
  { label: "Organizations", value: "—" },
  { label: "Protected users", value: "—" },
  { label: "Pending enrollments", value: "—" },
  { label: "Attention required", value: "—" },
];

const actions = [
  "Onboard user",
  "Replace MFA device",
  "Revoke MFA device",
  "Unlock user",
];

export default function Dashboard() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">B</span>
          <div>
            <strong>Bliss Secure MFA</strong>
            <small>Management Portal</small>
          </div>
        </div>

        <nav>
          <a className="active" href="/">Dashboard</a>
          <a href="/organizations">Organizations</a>
          <a href="/users">Users</a>
          <a href="/enrollments">Enrollments</a>
          <a href="/audit">Audit log</a>
          <a href="/billing">Billing</a>
          <a href="/settings">Settings</a>
        </nav>

        <div className="sidebarFoot">
          <span>Bliss IT Solutions</span>
          <small>Secure MFA management</small>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Operations</p>
            <h1>MFA Dashboard</h1>
          </div>
          <button className="primary">Add user</button>
        </header>

        <div className="notice">
          <strong>Development workspace</strong>
          <span>Production authentication and live multiOTP connectivity are not enabled yet.</span>
        </div>

        <section className="stats">
          {stats.map((stat) => (
            <article className="card stat" key={stat.label}>
              <span>{stat.label}</span>
              <strong>{stat.value}</strong>
            </article>
          ))}
        </section>

        <section className="grid">
          <article className="card">
            <div className="cardHead">
              <div>
                <p className="eyebrow">Operations</p>
                <h2>Quick actions</h2>
              </div>
            </div>
            <div className="actionGrid">
              {actions.map((action) => (
                <button className="action" key={action}>{action}</button>
              ))}
            </div>
          </article>

          <article className="card">
            <div className="cardHead">
              <div>
                <p className="eyebrow">Security</p>
                <h2>Platform state</h2>
              </div>
            </div>
            <dl className="health">
              <div><dt>Portal API</dt><dd className="pending">Not connected</dd></div>
              <div><dt>multiOTP engine</dt><dd className="pending">Not connected</dd></div>
              <div><dt>Stripe billing</dt><dd className="pending">Not configured</dd></div>
              <div><dt>Audit pipeline</dt><dd>Designed</dd></div>
            </dl>
          </article>
        </section>
      </section>
    </main>
  );
}
