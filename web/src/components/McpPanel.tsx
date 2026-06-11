"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Plus, Trash2, Plug, CheckCircle2, KeyRound, Loader2 } from "@/components/icons";
import { deleteJSON, getJSON, postJSON } from "@/lib/api";

type McpServer = {
  name: string;
  command: string;
  args: string[];
  description: string;
  used_by: string[];
  requires: string[];
  missing: string[];
  authenticated: boolean;
};

export function McpPanel() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [adding, setAdding] = useState(false);
  const [testResult, setTestResult] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState<string | null>(null);

  // form
  const [name, setName] = useState("");
  const [command, setCommand] = useState("npx");
  const [argsStr, setArgsStr] = useState("");
  const [desc, setDesc] = useState("");
  const [requiresStr, setRequiresStr] = useState("");

  async function refresh() {
    try {
      const r = await getJSON<{ servers: McpServer[] }>("/api/mcp");
      setServers(r.servers ?? []);
    } catch {
      /* backend down */
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  async function add() {
    if (!name.trim() || !command.trim()) return;
    const args = argsStr.trim() ? argsStr.trim().split(/\s+/) : [];
    const requires = requiresStr.trim() ? requiresStr.split(",").map((s) => s.trim()).filter(Boolean) : [];
    await postJSON("/api/mcp", {
      name: name.trim(),
      command: command.trim(),
      args,
      description: desc.trim(),
      requires,
    });
    setName("");
    setArgsStr("");
    setDesc("");
    setRequiresStr("");
    setAdding(false);
    refresh();
  }

  async function del(n: string) {
    await deleteJSON(`/api/mcp/${n}`);
    refresh();
  }

  async function attach(n: string) {
    await postJSON("/api/mcp/attach", { server: n, agent: "root" });
    refresh();
  }

  async function test(n: string) {
    setTesting(n);
    try {
      const r = await postJSON<{ ok: boolean; tools?: string[]; error?: string }>(`/api/mcp/test/${n}`, {});
      setTestResult((p) => ({
        ...p,
        [n]: r.ok ? `✓ ${r.tools?.length ?? 0} tools: ${(r.tools ?? []).join(", ")}` : `✕ ${r.error}`,
      }));
    } catch (e) {
      setTestResult((p) => ({ ...p, [n]: `✕ ${String(e)}` }));
    } finally {
      setTesting(null);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between px-1">
        <span className="text-[11px] uppercase tracking-wide text-ink-muted">MCP servers</span>
        <button
          onClick={() => setAdding((v) => !v)}
          className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-accent hover:bg-panel-hover"
        >
          <Plus className="h-3 w-3" /> Add
        </button>
      </div>

      {adding && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="overflow-hidden rounded-lg border border-edge-subtle bg-panel-elevated p-2"
        >
          <Field label="name" value={name} onChange={setName} placeholder="my_server" />
          <Field label="command" value={command} onChange={setCommand} placeholder="npx" />
          <Field label="args" value={argsStr} onChange={setArgsStr} placeholder="-y @scope/mcp-server" />
          <Field label="description" value={desc} onChange={setDesc} placeholder="what it does" />
          <Field
            label="required env keys (comma-separated, optional)"
            value={requiresStr}
            onChange={setRequiresStr}
            placeholder="GITHUB_TOKEN, OTHER_KEY"
          />
          <button
            onClick={add}
            className="mt-1 w-full rounded-md bg-accent py-1 text-[11px] font-medium text-[#0b1220] hover:bg-accent-hover"
          >
            Register server
          </button>
        </motion.div>
      )}

      {servers.length === 0 && <p className="px-1 text-[11.5px] text-ink-muted">No MCP servers.</p>}

      {servers.map((s) => (
        <div key={s.name} className="rounded-lg border border-edge-subtle bg-panel-elevated p-2">
          <div className="flex items-center justify-between">
            <span className="text-[12.5px] font-medium text-ink-secondary">{s.name}</span>
            <div className="flex items-center gap-1">
              <button onClick={() => test(s.name)} title="Test connection" className="rounded p-1 hover:bg-panel-hover">
                {testing === s.name ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-ink-muted" />
                ) : (
                  <Plug className="h-3.5 w-3.5 text-ink-muted" />
                )}
              </button>
              <button onClick={() => del(s.name)} title="Remove" className="rounded p-1 hover:bg-panel-hover">
                <Trash2 className="h-3.5 w-3.5 text-state-err/80" />
              </button>
            </div>
          </div>
          {s.description && <p className="mt-0.5 text-[11px] text-ink-muted">{s.description}</p>}
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {s.used_by.length > 0 ? (
              <span className="flex items-center gap-1 text-[10.5px] text-state-ok">
                <CheckCircle2 className="h-3 w-3" /> attached: {s.used_by.join(", ")}
              </span>
            ) : (
              <button
                onClick={() => attach(s.name)}
                className="rounded-md bg-panel-active px-2 py-0.5 text-[10.5px] text-ink-secondary hover:bg-panel-hover"
              >
                attach to root
              </button>
            )}
            {(s.requires ?? []).length > 0 &&
              (s.authenticated ? (
                <span className="flex items-center gap-1 rounded-full border border-state-ok/30 bg-state-ok/10 px-2 py-0.5 text-[10.5px] text-state-ok">
                  <KeyRound className="h-3 w-3" /> authenticated
                </span>
              ) : (
                <span className="flex items-center gap-1 rounded-full border border-state-run/40 bg-state-run/10 px-2 py-0.5 text-[10.5px] text-state-run">
                  <KeyRound className="h-3 w-3" /> needs auth
                </span>
              ))}
          </div>
          {(s.missing ?? []).map((key) => (
            <AuthKeyEntry key={key} keyName={key} onSaved={refresh} />
          ))}
          {testResult[s.name] && (
            <p
              className={`mt-1 font-mono text-[10.5px] ${testResult[s.name].startsWith("✓") ? "text-state-ok" : "text-state-err"}`}
            >
              {testResult[s.name]}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

/** Inline secret entry for a missing MCP credential — straight to the vault. */
function AuthKeyEntry({ keyName, onSaved }: { keyName: string; onSaved: () => void }) {
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!value.trim() || saving) return;
    setSaving(true);
    try {
      await postJSON("/api/credentials", { key: keyName, value: value.trim() });
      setValue("");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-1.5 flex items-center gap-1.5">
      <input
        type="password"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && save()}
        placeholder={keyName}
        className="min-w-0 flex-1 rounded-md border border-edge-subtle bg-panel-sidebar px-2 py-1 font-mono text-[11px] text-ink outline-none focus:border-accent/50"
      />
      <button
        onClick={save}
        disabled={!value.trim() || saving}
        className="rounded-md bg-accent px-2 py-1 text-[10.5px] font-medium text-[#0b1220] hover:bg-accent-hover disabled:opacity-40"
      >
        {saving ? "…" : "Save key"}
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="mb-1.5 block">
      <span className="mb-0.5 block text-[10px] text-ink-muted">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-edge-subtle bg-panel-sidebar px-2 py-1 text-[12px] text-ink outline-none focus:border-edge-strong"
      />
    </label>
  );
}
