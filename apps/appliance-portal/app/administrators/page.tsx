"use client";

import { FormEvent, useEffect, useState } from "react";
import { Shell } from "../../components/Shell";
import { api } from "../../lib/api";

type Admin = {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  disabled: boolean;
  created_at: string;
};

export default function AdministratorsPage() {
  const [admins, setAdmins] = useState<Admin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);

  async function load() {
    try {
      setAdmins(await api<Admin[]>("/admins"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load administrators");
    }
  }

  useEffect(() => { load(); }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      await api<Admin>("/admins", {
        method: "POST",
        body: JSON.stringify({
          email: String(form.get("email") ?? ""),
          display_name: String(form.get("display_name") ?? "") || null,
          password: String(form.get("password") ?? ""),
          role: String(form.get("role") ?? "operator"),
        }),
      });
      event.currentTarget.reset();
      setShowNew(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create administrator");
    }
  }

  async function remove(admin: Admin) {
    const reason = window.prompt("Reason for removing this administrator:");
    if (!reason || !window.confirm(`Remove ${admin.email}?`)) return;
    try {
      await api<void>(`/admins/${admin.id}?reason=${encodeURIComponent(reason)}`, {
        method: "DELETE",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove administrator");
    }
  }

  return (
    <Shell title="Administrators">
      <div className="toolbar">
        <div>
          <strong>Office management accounts</strong>
          <div className="muted">Owners and admins control the local appliance. Operators manage users.</div>
        </div>
        <button className="primary" onClick={() => setShowNew((value) => !value)}>+ Add administrator</button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {showNew ? (
        <form className="card formCard" onSubmit={create}>
          <label>Email<input name="email" type="email" required /></label>
          <label>Display name<input name="display_name" /></label>
          <label>Temporary password<input name="password" type="password" minLength={12} required /></label>
          <label>Role
            <select name="role" defaultValue="operator">
              <option value="admin">Admin</option>
              <option value="operator">Operator</option>
              <option value="readonly">Read only</option>
              <option value="owner">Owner</option>
            </select>
          </label>
          <button className="primary" type="submit">Create</button>
        </form>
      ) : null}

      <section className="card table">
        <div className="headerRow adminGrid"><span>Administrator</span><span>Role</span><span>Status</span><span>Actions</span></div>
        {admins.map((admin) => (
          <div className="row adminGrid" key={admin.id}>
            <div className="nameBlock"><strong>{admin.display_name || admin.email}</strong><small>{admin.email}</small></div>
            <span className="pill">{admin.role}</span>
            <span>{admin.disabled ? "Disabled" : "Active"}</span>
            <div className="actions">
              <button className="dangerLink" onClick={() => remove(admin)}>Remove</button>
            </div>
          </div>
        ))}
        {admins.length === 0 ? <div className="empty">No local administrators.</div> : null}
      </section>
    </Shell>
  );
}
