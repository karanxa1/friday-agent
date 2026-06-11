"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  BookOpen,
  Bot,
  Check,
  Loader2,
  Pencil,
  Pin,
  Plus,
  Trash2,
  User,
  X,
} from "@/components/icons";
import clsx from "clsx";
import { deleteJSON, getJSON, postJSON, putJSON } from "@/lib/api";
import type { SkillInfo } from "@/lib/types";

const NEW_SKILL_TEMPLATE = (name: string) => `---
name: ${name || "my-skill"}
description: One line describing when to use this skill.
---

# ${name || "My skill"}

Step-by-step procedure the agent should follow.
`;

type Mode =
  | { view: "list" }
  | { view: "edit"; name: string }
  | { view: "create" };

export function SkillsPanel() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [mode, setMode] = useState<Mode>({ view: "list" });
  const [content, setContent] = useState("");
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<{ ok: boolean; text: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await getJSON<{ items: SkillInfo[] }>("/api/skills");
      setSkills(r.items ?? []);
    } catch {
      // backend not up yet
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  function note(ok: boolean, text: string) {
    setFlash({ ok, text });
    setTimeout(() => setFlash(null), 2500);
  }

  async function openEditor(name: string) {
    setBusy(true);
    try {
      const r = await getJSON<{ content?: string; error?: string }>(`/api/skills/${name}`);
      if (r.content === undefined) {
        note(false, r.error ?? "failed to load skill");
        return;
      }
      setContent(r.content);
      setMode({ view: "edit", name });
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    try {
      if (mode.view === "edit") {
        const r = await putJSON<{ ok?: boolean; error?: string }>(`/api/skills/${mode.name}`, {
          content,
        });
        note(!!r.ok, r.ok ? `saved ${mode.name}` : (r.error ?? "save failed"));
        if (r.ok) setMode({ view: "list" });
      } else if (mode.view === "create") {
        const r = await postJSON<{ ok?: boolean; error?: string }>("/api/skills", {
          name: newName.trim(),
          content,
        });
        note(!!r.ok, r.ok ? `created ${newName}` : (r.error ?? "create failed"));
        if (r.ok) {
          setMode({ view: "list" });
          setNewName("");
        }
      }
      refresh();
    } finally {
      setBusy(false);
    }
  }

  async function remove(name: string) {
    const r = await deleteJSON<{ ok?: boolean; error?: string }>(`/api/skills/${name}`);
    note(!!r.ok, r.ok ? `deleted ${name}` : (r.error ?? "delete failed"));
    refresh();
  }

  if (mode.view !== "list") {
    const editing = mode.view === "edit";
    return (
      <div className="flex h-full flex-col">
        <div className="mb-2 flex items-center gap-1.5">
          <button
            onClick={() => setMode({ view: "list" })}
            className="flex h-6 w-6 items-center justify-center rounded-md text-ink-muted hover:bg-panel-hover hover:text-ink"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
          </button>
          {editing ? (
            <span className="font-mono text-[13px] text-ink">{mode.name}/SKILL.md</span>
          ) : (
            <input
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                setContent(NEW_SKILL_TEMPLATE(e.target.value));
              }}
              placeholder="skill-name"
              className="h-6 flex-1 rounded-md border border-edge-subtle bg-panel-elevated px-2 font-mono text-[13px] text-ink outline-none focus:border-accent/50"
            />
          )}
          <button
            onClick={save}
            disabled={busy || (!editing && !newName.trim())}
            className={clsx(
              "ml-auto flex h-6 items-center gap-1 rounded-md px-2 text-[12.5px] font-medium",
              busy || (!editing && !newName.trim())
                ? "bg-panel-active text-ink-muted"
                : "bg-accent text-[#0b1220] hover:bg-accent-hover"
            )}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
            Save
          </button>
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          spellCheck={false}
          className="flex-1 resize-none rounded-lg border border-edge-subtle bg-panel-editor p-3 font-mono text-[12.5px] leading-relaxed text-ink outline-none focus:border-accent/40"
        />
        <FlashNote flash={flash} />
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => {
          setContent(NEW_SKILL_TEMPLATE(""));
          setNewName("");
          setMode({ view: "create" });
        }}
        className="mb-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-edge-strong py-2 text-[13px] text-ink-muted hover:border-accent/50 hover:text-accent"
      >
        <Plus className="h-3 w-3" /> New skill
      </button>

      <AnimatePresence initial={false}>
        {skills.length === 0 ? (
          <p className="px-1 py-2 text-[13px] text-ink-muted">No skills yet.</p>
        ) : (
          skills.map((s) => (
            <motion.div
              key={s.name}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
              className="group mb-1.5 rounded-lg border border-edge-subtle bg-panel-elevated p-2.5"
            >
              <div className="flex items-center gap-1.5">
                <BookOpen className="h-3 w-3 shrink-0 text-accent/70" />
                <span className="truncate font-mono text-[13px] font-medium text-ink">{s.name}</span>
                {s.pinned && <Pin className="h-2.5 w-2.5 shrink-0 text-state-run" />}
                <span
                  title={s.created_by === "agent" ? "Created by Friday" : "Created by you"}
                  className="ml-auto flex shrink-0 items-center gap-1 rounded-full border border-edge-subtle px-1.5 py-0.5 text-[10px] text-ink-muted"
                >
                  {s.created_by === "agent" ? <Bot className="h-2.5 w-2.5" /> : <User className="h-2.5 w-2.5" />}
                  {s.created_by}
                </span>
              </div>
              {s.description && (
                <p className="mt-1 line-clamp-2 text-[12.5px] leading-snug text-ink-muted">{s.description}</p>
              )}
              <div className="mt-1.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={() => openEditor(s.name)}
                  className="flex items-center gap-1 rounded-md bg-panel-active px-2 py-1 text-[12px] text-ink-secondary hover:bg-panel-hover"
                >
                  <Pencil className="h-2.5 w-2.5" /> Edit
                </button>
                <button
                  onClick={() => remove(s.name)}
                  className="flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-ink-muted hover:bg-state-err/15 hover:text-state-err"
                >
                  <Trash2 className="h-2.5 w-2.5" /> Delete
                </button>
              </div>
            </motion.div>
          ))
        )}
      </AnimatePresence>
      <FlashNote flash={flash} />
    </div>
  );
}

function FlashNote({ flash }: { flash: { ok: boolean; text: string } | null }) {
  return (
    <AnimatePresence>
      {flash && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className={clsx(
            "mt-2 flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[12.5px]",
            flash.ok ? "bg-state-ok/10 text-state-ok" : "bg-state-err/10 text-state-err"
          )}
        >
          {flash.ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
          <span className="truncate">{flash.text}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
