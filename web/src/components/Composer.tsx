"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp, Brain, ChevronDown, FileText, ImageIcon, Paperclip, Square, X } from "@/components/icons";
import clsx from "clsx";

const AGENTS = ["root", "trend_scout", "content_studio", "analyst", "publisher", "ad_manager"];

export type Attachment = { name: string; mime: string; data: string };

const MAX_FILES = 4;
const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPT = "image/*,.pdf,.txt,.md,.csv,.json";

export function Composer({
  onSend,
  onStop,
  streaming,
  agent,
  setAgent,
  thinkingOn,
  onToggleThinking,
  variant = "docked",
}: {
  onSend: (text: string, attachments: Attachment[]) => void;
  onStop: () => void;
  streaming: boolean;
  agent: string;
  setAgent: (a: string) => void;
  thinkingOn?: boolean;
  onToggleThinking?: () => void;
  variant?: "hero" | "docked";
}) {
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<Attachment[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const hero = variant === "hero";

  function submit() {
    const t = value.trim();
    if ((!t && files.length === 0) || streaming) return;
    onSend(t || "(see attached files)", files);
    setValue("");
    setFiles([]);
    if (ref.current) ref.current.style.height = "auto";
  }

  async function pickFiles(list: FileList | null) {
    if (!list) return;
    const next: Attachment[] = [...files];
    for (const f of Array.from(list)) {
      if (next.length >= MAX_FILES || f.size > MAX_BYTES) continue;
      const data = await new Promise<string>((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(String(r.result).split(",")[1] ?? "");
        r.onerror = rej;
        r.readAsDataURL(f);
      });
      next.push({ name: f.name, mime: f.type || "application/octet-stream", data });
    }
    setFiles(next);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div
      className={clsx(
        "rounded-2xl border border-edge-subtle bg-panel-elevated shadow-[0_8px_32px_rgba(0,0,0,0.3)] transition-colors focus-within:border-accent/40 focus-within:ring-1 focus-within:ring-accent/25",
        hero ? "px-4 pt-4 pb-3" : "px-4 pt-3 pb-2.5"
      )}
    >
      {files.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {files.map((f, i) => (
            <span
              key={`${f.name}${i}`}
              className="flex items-center gap-1.5 rounded-full border border-edge-subtle bg-panel-sidebar px-2.5 py-1 text-[11.5px] text-ink-secondary"
            >
              {f.mime.startsWith("image/") ? (
                <ImageIcon className="h-3 w-3 text-accent" />
              ) : (
                <FileText className="h-3 w-3 text-accent" />
              )}
              <span className="max-w-[160px] truncate">{f.name}</span>
              <button
                onClick={() => setFiles((p) => p.filter((_, k) => k !== i))}
                className="text-ink-muted hover:text-state-err"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <textarea
        ref={ref}
        value={value}
        autoFocus={hero}
        onChange={(e) => {
          setValue(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = Math.min(e.target.scrollHeight, 240) + "px";
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={1}
        placeholder={hero ? "Plan, Build, / for skills…" : "Ask Friday to do anything…"}
        className={clsx(
          "w-full resize-none bg-transparent leading-relaxed text-ink outline-none placeholder:text-ink-muted",
          hero ? "max-h-[240px] min-h-[64px] text-[16px]" : "max-h-[240px] min-h-[48px] text-[14.5px]"
        )}
      />
      <div className={clsx("flex items-center gap-1.5", hero ? "mt-3" : "mt-2")}>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => pickFiles(e.target.files)}
        />
        <button
          onClick={() => fileRef.current?.click()}
          title="Attach images, PDFs, or text files"
          className="flex h-8 w-8 items-center justify-center rounded-full border border-edge-subtle text-ink-muted hover:bg-panel-hover hover:text-ink"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <div className="relative">
          <button
            onClick={() => setPickerOpen((v) => !v)}
            className="flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-ink-secondary hover:bg-panel-hover"
          >
            ◈ {agent}
            <ChevronDown
              className={clsx("h-3.5 w-3.5 transition-transform duration-200", pickerOpen && "rotate-180")}
            />
          </button>
          {pickerOpen && (
            <motion.div
              initial={{ opacity: 0, y: 6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.15 }}
              className="absolute bottom-10 left-0 z-10 w-52 rounded-xl border border-edge-subtle bg-panel-elevated py-1.5 shadow-2xl"
            >
              {AGENTS.map((a) => (
                <button
                  key={a}
                  onClick={() => {
                    setAgent(a);
                    setPickerOpen(false);
                  }}
                  className={clsx(
                    "block w-full px-3.5 py-2 text-left text-[13px] hover:bg-panel-hover",
                    a === agent ? "text-accent" : "text-ink-secondary"
                  )}
                >
                  {a}
                </button>
              ))}
            </motion.div>
          )}
        </div>

        <span className="flex-1" />

        {onToggleThinking && (
          <button
            onClick={onToggleThinking}
            title={thinkingOn ? "Thinking on — click to disable" : "Thinking off — click to enable"}
            className={clsx(
              "flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[12.5px] font-medium transition-colors",
              thinkingOn
                ? "bg-accent/15 text-accent hover:bg-accent/25"
                : "text-ink-muted hover:bg-panel-hover hover:text-ink-secondary"
            )}
          >
            <Brain className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">thinking</span>
          </button>
        )}

        {streaming ? (
          <motion.button
            whileTap={{ scale: 0.92 }}
            onClick={onStop}
            title="Stop"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-panel-active text-ink-secondary hover:bg-panel-hover"
          >
            <Square className="h-3.5 w-3.5" fill="currentColor" />
          </motion.button>
        ) : (
          <motion.button
            whileTap={{ scale: 0.92 }}
            onClick={submit}
            disabled={!value.trim() && files.length === 0}
            className={clsx(
              "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
              value.trim() || files.length > 0
                ? "bg-accent text-[#0b1220] hover:bg-accent-hover"
                : "bg-panel-active text-ink-muted"
            )}
          >
            <ArrowUp className="h-4 w-4" />
          </motion.button>
        )}
      </div>
    </div>
  );
}
