"use client";

import { useEffect, useState } from "react";

/**
 * Whole-app password gate. When the backend has FRIDAY_ACCESS_PASSWORD set,
 * /api/auth reports `required: true` and this renders a password screen until
 * the user logs in (POST /api/login sets an HttpOnly access cookie that every
 * later /api request carries automatically). When no password is configured the
 * gate is transparent — children render immediately.
 */

const API_BASE = process.env.NEXT_PUBLIC_FRIDAY_API ?? "";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "locked" | "open">("checking");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE}/api/auth`, { credentials: "include" })
      .then((r) => r.json())
      .then((d) => {
        if (alive) setState(d?.authed ? "open" : "locked");
      })
      .catch(() => {
        // Backend unreachable — don't hard-lock the UI; let it try to load.
        if (alive) setState("open");
      });
    return () => {
      alive = false;
    };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!pw || busy) return;
    setBusy(true);
    setErr("");
    try {
      const r = await fetch(`${API_BASE}/api/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ password: pw }),
      });
      if (r.ok) {
        setState("open");
      } else {
        setErr("Incorrect password");
        setPw("");
      }
    } catch {
      setErr("Network error — please try again");
    } finally {
      setBusy(false);
    }
  }

  if (state === "open") return <>{children}</>;

  if (state === "checking") {
    return <div className="h-screen w-screen bg-[#0f0f0f]" />;
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-[#0f0f0f] px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-2xl border border-edge-subtle bg-panel-elevated p-7 shadow-2xl"
      >
        <div className="mb-1 text-[19px] font-semibold text-ink">Friday</div>
        <p className="mb-5 text-[13px] leading-relaxed text-ink-muted">
          This deployment is protected. Enter the access password to continue.
        </p>
        <input
          type="password"
          autoFocus
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          placeholder="Access password"
          className="w-full rounded-lg border border-edge-strong bg-panel-sidebar px-3.5 py-2.5 text-[14px] text-ink outline-none transition placeholder:text-ink-muted focus:border-accent"
        />
        {err && <div className="mt-2 text-[12.5px] text-state-err">{err}</div>}
        <button
          type="submit"
          disabled={busy || !pw}
          className="mt-4 w-full rounded-lg bg-accent px-3 py-2.5 text-[14px] font-medium text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Checking…" : "Unlock"}
        </button>
      </form>
    </div>
  );
}
