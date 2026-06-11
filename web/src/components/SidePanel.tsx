"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, X, ShieldAlert } from "@/components/icons";
import clsx from "clsx";
import { getJSON, postJSON } from "@/lib/api";
import { auditRowKey, type AuditEvent, type PendingApproval } from "@/lib/types";
import { McpPanel } from "./McpPanel";
import { SkillsPanel } from "./SkillsPanel";

export function SidePanel() {
  const [pending, setPending] = useState<PendingApproval[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [tab, setTab] = useState<"approvals" | "audit" | "mcp" | "skills">("approvals");

  async function refresh() {
    try {
      const ap = await getJSON<{ pending: PendingApproval[] }>("/api/approvals");
      setPending(ap.pending ?? []);
      const au = await getJSON<{ events: AuditEvent[] }>("/api/audit?limit=40");
      setAudit((au.events ?? []).slice().reverse());
    } catch {
      // backend not up yet
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  async function decide(id: string, approve: boolean) {
    await postJSON(`/api/approvals/${id}`, { approve });
    refresh();
  }

  return (
    <div className="flex h-full w-[88vw] max-w-[380px] shrink-0 flex-col border-l border-edge-subtle bg-panel-sidebar lg:w-[380px]">
      <div className="flex h-12 shrink-0 items-center gap-1 border-b border-edge-subtle px-2">
        <TabBtn active={tab === "approvals"} onClick={() => setTab("approvals")}>
          Approvals {pending.length > 0 && <span className="ml-1 text-state-run">{pending.length}</span>}
        </TabBtn>
        <TabBtn active={tab === "audit"} onClick={() => setTab("audit")}>
          Activity
        </TabBtn>
        <TabBtn active={tab === "skills"} onClick={() => setTab("skills")}>
          Skills
        </TabBtn>
        <TabBtn active={tab === "mcp"} onClick={() => setTab("mcp")}>
          MCP
        </TabBtn>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {tab === "skills" ? (
          <SkillsPanel />
        ) : tab === "mcp" ? (
          <McpPanel />
        ) : tab === "approvals" ? (
          <AnimatePresence initial={false}>
            {pending.length === 0 ? (
              <p className="px-1 py-2 text-[13px] text-ink-muted">No pending actions.</p>
            ) : (
              pending.map((p) => (
                <motion.div
                  key={p.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  className="mb-2.5 rounded-xl border border-edge-subtle bg-panel-elevated p-3"
                >
                  <div className="mb-2 flex items-center gap-1.5">
                    <ShieldAlert className="h-3.5 w-3.5 text-state-run" />
                    <span className="text-[11px] uppercase tracking-wide text-ink-muted">{p.type}</span>
                  </div>
                  <p className="mb-2.5 text-[13px] leading-relaxed text-ink-secondary">{p.summary}</p>
                  {p.type === "credential" ? (
                    <CredentialEntry approval={p} onDone={refresh} onReject={() => decide(p.id, false)} />
                  ) : (
                    <div className="flex gap-2">
                      <button
                        onClick={() => decide(p.id, true)}
                        className="flex items-center gap-1.5 rounded-md bg-state-ok/90 px-3 py-1.5 text-[12.5px] font-medium text-black hover:bg-state-ok"
                      >
                        <Check className="h-3.5 w-3.5" /> Approve
                      </button>
                      <button
                        onClick={() => decide(p.id, false)}
                        className="flex items-center gap-1.5 rounded-md bg-panel-active px-3 py-1.5 text-[12.5px] text-ink-secondary hover:bg-panel-hover"
                      >
                        <X className="h-3.5 w-3.5" /> Reject
                      </button>
                    </div>
                  )}
                </motion.div>
              ))
            )}
          </AnimatePresence>
        ) : (
          <div className="font-mono text-[12px] leading-relaxed text-ink-muted">
            {audit.map((e) => (
              <div key={auditRowKey(e)} className="flex gap-2 py-0.5">
                <span className="shrink-0 text-ink-muted/60">
                  {new Date(e.ts * 1000).toLocaleTimeString()}
                </span>
                <span className="text-ink-secondary">{e.event}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Inline secret entry for agent-requested credentials. The value goes straight
 *  to the encrypted vault (POST /api/credentials) and is never echoed back. */
function CredentialEntry({
  approval,
  onDone,
  onReject,
}: {
  approval: PendingApproval;
  onDone: () => void;
  onReject: () => void;
}) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const key = String(approval.payload?.key_name ?? "");
  const instructions = String(approval.payload?.instructions ?? "");

  async function save() {
    if (!key || !value.trim() || saving) return;
    setSaving(true);
    try {
      await postJSON("/api/credentials", { key, value: value.trim() });
      setValue("");
      onDone();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      {instructions && <p className="mb-2 text-[11.5px] text-ink-muted">{instructions}</p>}
      <div className="flex gap-2">
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder={key || "secret"}
          className="min-w-0 flex-1 rounded-md border border-edge-subtle bg-panel-sidebar px-2.5 py-1.5 font-mono text-[12px] text-ink outline-none focus:border-accent/50"
        />
        <button
          onClick={save}
          disabled={!value.trim() || saving}
          className="flex items-center gap-1.5 rounded-md bg-state-ok/90 px-3 py-1.5 text-[12.5px] font-medium text-black hover:bg-state-ok disabled:opacity-40"
        >
          <Check className="h-3.5 w-3.5" /> {saving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={onReject}
          title="Reject this request"
          className="flex items-center justify-center rounded-md bg-panel-active px-2.5 text-ink-secondary hover:bg-panel-hover"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <p className="mt-1.5 text-[10.5px] text-ink-muted/70">
        Stored encrypted in the vault — never shown to the model.
      </p>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
        active ? "bg-panel-active text-ink" : "text-ink-muted hover:text-ink-secondary"
      )}
    >
      {children}
    </button>
  );
}
