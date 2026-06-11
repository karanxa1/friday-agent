"use client";

/**
 * Cursor-style specialized tool bodies. Each view knows how to render one
 * family of tools (file edits as diffs, sandbox as a terminal, web search as
 * result rows, …). `viewFor()` at the bottom dispatches by tool name.
 */

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  Globe,
  Network,
  Wrench,
  XCircle,
} from "@/components/icons";
import clsx from "clsx";
import { getJSON } from "@/lib/api";
import { auditRowKey, type AuditEvent, type ToolCard } from "@/lib/types";
import { Markdown } from "./Markdown";
import { ImageGeneration } from "./ImageGeneration";

const str = (v: unknown) => (v === undefined || v === null ? "" : String(v));

/* ---------------------------------------------------------------- shared */

const lineIn = {
  initial: { opacity: 0, x: -4 },
  animate: { opacity: 1, x: 0 },
};

function MonoPane({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={clsx(
        "max-h-[380px] overflow-auto border-t border-edge-subtle bg-panel-sidebar font-mono text-[12.5px] leading-[1.65]",
        className
      )}
    >
      {children}
    </div>
  );
}

function NumberedLine({
  n,
  text,
  tone,
  index,
}: {
  n?: number | string;
  text: string;
  tone?: "add" | "rm" | "plain";
  index: number;
}) {
  return (
    <motion.div
      {...lineIn}
      transition={{ duration: 0.18, delay: Math.min(index * 0.015, 0.45) }}
      className={clsx(
        "flex whitespace-pre px-0",
        tone === "add" && "bg-diff-addbg text-diff-addtext",
        tone === "rm" && "bg-diff-rmbg text-diff-rmtext",
        tone === "plain" && "text-ink-secondary"
      )}
    >
      <span className="w-11 shrink-0 select-none pr-2 text-right text-ink-muted/60">{n ?? ""}</span>
      <span className="w-4 shrink-0 select-none text-center">
        {tone === "add" ? "+" : tone === "rm" ? "−" : " "}
      </span>
      <span className="pr-3">{text || " "}</span>
    </motion.div>
  );
}

/**
 * Live "typewriter" reveal for file edits. Gemini ships a tool call's whole
 * argument in one chunk (so the backend tee can't stream it character by
 * character), which made edits pop in fully-formed. This reveals the new lines
 * progressively the first time the card renders while still running — so you
 * watch the file being written, Cursor/Manus-style. Historical cards (loaded
 * already "done") show everything immediately and never replay.
 */
function useReveal(total: number, animate: boolean): number {
  const [shown, setShown] = useState(() => (animate ? 0 : total));
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!animate || total <= 0) {
      setShown(total);
      return;
    }
    const perTick = Math.max(1, Math.ceil(total / 60)); // ~ up to 1.4s for big files
    let n = 0;
    const iv = setInterval(() => {
      n += perTick;
      setShown(Math.min(n, total));
      if (n >= total) clearInterval(iv);
    }, 24);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return Math.min(shown, total);
}

function RevealCaret() {
  return (
    <div className="flex whitespace-pre px-0 text-state-run">
      <span className="w-11 shrink-0 pr-2" />
      <span className="w-4 shrink-0 text-center">▍</span>
      <span className="animate-caret">writing…</span>
    </div>
  );
}

/* ------------------------------------------------------------------ diff */

export type DiffStat = { added: number; removed: number };

/** Minimal line diff: shared prefix/suffix kept, middle = removed + added. */
function lineDiff(oldText: string, newText: string) {
  const a = oldText.split("\n");
  const b = newText.split("\n");
  let pre = 0;
  while (pre < a.length && pre < b.length && a[pre] === b[pre]) pre++;
  let post = 0;
  while (
    post < a.length - pre &&
    post < b.length - pre &&
    a[a.length - 1 - post] === b[b.length - 1 - post]
  )
    post++;
  return {
    context: a.slice(Math.max(0, pre - 2), pre),
    removed: a.slice(pre, a.length - post),
    added: b.slice(pre, b.length - post),
    preLine: pre,
  };
}

export function diffStat(card: ToolCard): DiffStat | null {
  const args = card.args;
  if (args.old !== undefined && args.new !== undefined) {
    const d = lineDiff(str(args.old), str(args.new));
    return { added: d.added.length, removed: d.removed.length };
  }
  const content = str(args.content || args.function_code || args.server_code);
  if (content) return { added: content.split("\n").length, removed: 0 };
  return null;
}

export function DiffView({ card }: { card: ToolCard }) {
  const d = lineDiff(str(card.args.old), str(card.args.new));
  const shownAdded = useReveal(d.added.length, card.status === "running");
  const revealing = shownAdded < d.added.length;
  let i = 0;
  let ln = Math.max(1, d.preLine - d.context.length + 1);
  return (
    <MonoPane className="py-1">
      {d.context.map((t) => (
        <NumberedLine key={`c${i}`} index={i++} n={ln++} text={t} tone="plain" />
      ))}
      {d.removed.map((t, k) => (
        <NumberedLine key={`r${k}`} index={i++} n={d.preLine + k + 1} text={t} tone="rm" />
      ))}
      {d.added.slice(0, shownAdded).map((t, k) => (
        <NumberedLine key={`a${k}`} index={i++} n={d.preLine + k + 1} text={t} tone="add" />
      ))}
      {revealing && <RevealCaret />}
      {!revealing && card.result && <ResultNote result={card.result} ok={card.status !== "error"} />}
    </MonoPane>
  );
}

/* ---------------------------------------------------------- file write -- */

export function FileWriteView({ card }: { card: ToolCard }) {
  const content = str(card.args.content || card.args.function_code || card.args.server_code);
  const lines = content.split("\n").slice(0, 400);
  const shown = useReveal(lines.length, card.status === "running");
  const revealing = shown < lines.length;
  return (
    <MonoPane className="py-1">
      {lines.slice(0, shown).map((t, k) => (
        <NumberedLine key={k} index={k} n={k + 1} text={t} tone="add" />
      ))}
      {revealing && <RevealCaret />}
      {!revealing && card.result && <ResultNote result={card.result} ok={card.status !== "error"} />}
    </MonoPane>
  );
}

/* ------------------------------------------------------------- terminal */

export function TerminalView({ card }: { card: ToolCard }) {
  const cmd = str(card.args.command || card.args.code);
  return (
    <MonoPane>
      <div className="flex items-center gap-1.5 border-b border-edge-subtle px-3 py-1.5">
        <span className="h-2 w-2 rounded-full bg-state-err/70" />
        <span className="h-2 w-2 rounded-full bg-state-run/70" />
        <span className="h-2 w-2 rounded-full bg-state-ok/70" />
        <span className="ml-2 text-[11.5px] text-ink-muted">
          {card.name === "sandbox_python"
            ? "python · docker (no network)"
            : card.name === "run_command"
              ? "sh · workspace"
              : "sh · docker (no network)"}
        </span>
      </div>
      <div className="px-3 py-2">
        <div className="whitespace-pre-wrap text-ink">
          <span className="select-none text-state-ok">$ </span>
          {cmd}
        </div>
        {card.status === "running" ? (
          <div className="mt-1 text-ink-muted">
            running<span className="animate-caret">▍</span>
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={clsx(
              "mt-1 whitespace-pre-wrap",
              card.status === "error" ? "text-diff-rmtext" : "text-ink-secondary"
            )}
          >
            {str(card.result) || "(no output)"}
          </motion.div>
        )}
      </div>
    </MonoPane>
  );
}

/* ----------------------------------------------------------- web search */

type SearchResult = { title?: string; url?: string; snippet?: string; source?: string };

function parseSearch(result?: string): SearchResult[] | null {
  if (!result) return null;
  try {
    const j = JSON.parse(result);
    if (Array.isArray(j?.results)) return j.results as SearchResult[];
  } catch {
    /* not JSON */
  }
  return null;
}

function domainOf(url?: string): string {
  try {
    return url ? new URL(url).hostname.replace(/^www\./, "") : "";
  } catch {
    return "";
  }
}

export function SearchView({ card }: { card: ToolCard }) {
  const results = parseSearch(card.result);
  return (
    <div className="border-t border-edge-subtle bg-panel-sidebar">
      {card.status === "running" && (
        <div className="space-y-2 px-3 py-2.5">
          {[0, 1, 2].map((k) => (
            <div
              key={k}
              className="h-3.5 animate-shimmer rounded bg-[linear-gradient(90deg,#202020,#2c2c2c,#202020)] bg-[length:200%_100%]"
              style={{ width: `${85 - k * 18}%` }}
            />
          ))}
        </div>
      )}
      {results && (
        <div className="max-h-[320px] overflow-auto px-2 py-1.5">
          {results.slice(0, 8).map((r, k) => (
            <motion.a
              key={k}
              href={r.url}
              target="_blank"
              rel="noreferrer"
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: k * 0.05 }}
              className="group flex gap-2.5 rounded-md px-2 py-1.5 hover:bg-panel-hover"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-panel-active text-[10px] text-ink-muted">
                {k + 1}
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-[13.5px] font-medium text-accent group-hover:underline">
                    {r.title || r.url}
                  </span>
                  <ExternalLink className="h-3 w-3 shrink-0 text-ink-muted opacity-0 transition-opacity group-hover:opacity-100" />
                </span>
                <span className="block truncate text-[11.5px] text-state-ok/80">{domainOf(r.url)}</span>
                {r.snippet && (
                  <span className="line-clamp-2 text-[12.5px] leading-snug text-ink-muted">{r.snippet}</span>
                )}
              </span>
            </motion.a>
          ))}
        </div>
      )}
      {!results && card.result && (
        <div className="max-h-[320px] overflow-auto whitespace-pre-wrap px-3.5 py-2.5 font-mono text-[12.5px] text-ink-secondary">
          {card.result}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- subagent */

/** Live ticker: while the subagent runs, poll the audit log and surface what
 *  the child agent is doing (its tool calls) in real time. */
function useLiveActivity(active: boolean) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  useEffect(() => {
    if (!active) return;
    let stop = false;
    const startTs = Date.now() / 1000 - 1;
    async function poll() {
      try {
        const r = await getJSON<{ events: AuditEvent[] }>("/api/audit?limit=30");
        if (stop) return;
        const fresh = (r.events ?? []).filter(
          (e) => e.ts >= startTs && (e.event.startsWith("run.tool_call") || e.event.startsWith("spawn."))
        );
        setEvents(fresh.slice(-6));
      } catch {
        /* backend hiccup; keep last */
      }
    }
    poll();
    const t = setInterval(poll, 1200);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [active]);
  return events;
}

export function SubagentView({ card }: { card: ToolCard }) {
  const tier = str(card.args.force_tier) || "auto";
  const role = str(card.args.role) || "leaf";
  const running = card.status === "running";
  const activity = useLiveActivity(running);
  return (
    <div className="border-t border-edge-subtle bg-panel-sidebar px-3.5 py-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-[11px] text-accent">
          <Network className="h-3 w-3" /> subagent · {role}
        </span>
        <span className="rounded-full border border-edge-subtle px-2.5 py-0.5 text-[11px] text-ink-muted">
          tier: {tier}
        </span>
        {running && (
          <span className="flex items-center gap-1.5 text-[11px] text-state-run">
            <span className="h-1.5 w-1.5 animate-pulsedot rounded-full bg-state-run" /> live
          </span>
        )}
      </div>
      <div className="flex items-start gap-2 text-[13.5px] text-ink-secondary">
        <ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-ink-muted" />
        <span>{str(card.args.task)}</span>
      </div>

      {running && (
        <div className="mt-2.5 rounded-lg border border-edge-subtle bg-panel-elevated/60 px-3 py-2">
          <AnimatePresence initial={false}>
            {activity.length === 0 ? (
              <motion.div
                key="warm"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-[12px] text-ink-muted"
              >
                child agent starting up<span className="animate-caret">▍</span>
              </motion.div>
            ) : (
              activity.map((e) => (
                <motion.div
                  key={auditRowKey(e)}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center gap-2 py-0.5 font-mono text-[11.5px] text-ink-secondary"
                >
                  <Wrench className="h-3 w-3 shrink-0 text-state-run/80" />
                  <span className="text-ink-muted">{String(e.agent ?? "agent")}</span>
                  <span>{String(e.tool ?? e.event)}</span>
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </div>
      )}

      {!running && card.result && (
        <motion.div
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="md mt-2.5 max-h-[320px] overflow-auto rounded-lg border border-edge-subtle bg-panel-elevated px-3 py-2.5 text-[13.5px] text-ink-secondary"
        >
          <Markdown>{card.result}</Markdown>
        </motion.div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- code */

export function CodeView({ card }: { card: ToolCard }) {
  const lines = str(card.result).split("\n").slice(0, 400);
  return (
    <MonoPane className="py-1">
      {card.status === "running" ? (
        <div className="px-3 py-1.5 text-ink-muted">reading…</div>
      ) : (
        lines.map((t, k) => <NumberedLine key={k} index={k} n={k + 1} text={t} tone="plain" />)
      )}
    </MonoPane>
  );
}

/* --------------------------------------------------------------- social */

const PLATFORM_COLORS: Record<string, string> = {
  twitter: "#1d9bf0",
  x: "#e7e9ea",
  linkedin: "#0a66c2",
  instagram: "#e1306c",
  facebook: "#1877f2",
  threads: "#e6e6e6",
  tiktok: "#69c9d0",
};

export function SocialView({ card }: { card: ToolCard }) {
  const platform = str(card.args.platform).toLowerCase();
  const color = PLATFORM_COLORS[platform] ?? "#4daafc";
  const text = str(card.args.text);
  const budget = card.args.daily_budget;
  return (
    <div className="border-t border-edge-subtle bg-panel-sidebar px-3 py-2.5">
      <div className="mb-1.5 flex items-center gap-2">
        {platform && (
          <span
            className="rounded-full px-2.5 py-0.5 text-[11px] font-medium"
            style={{ backgroundColor: `${color}22`, color, border: `1px solid ${color}44` }}
          >
            {platform}
          </span>
        )}
        {budget !== undefined && (
          <span className="rounded-full border border-state-run/40 bg-state-run/10 px-2.5 py-0.5 text-[11px] text-state-run">
            ${String(budget)}/day
          </span>
        )}
        {card.args.objective !== undefined && (
          <span className="rounded-full border border-edge-subtle px-2.5 py-0.5 text-[11px] text-ink-muted">
            {str(card.args.objective)}
          </span>
        )}
      </div>
      {text && (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="rounded-lg border border-edge-subtle bg-panel-elevated px-3.5 py-2.5 text-[13.5px] leading-relaxed text-ink"
        >
          {text}
        </motion.div>
      )}
      {card.result && <ResultNote result={card.result} ok={card.status !== "error"} bare />}
    </div>
  );
}

/* -------------------------------------------------------------- generic */

export function GenericView({ card }: { card: ToolCard }) {
  return (
    <MonoPane className="px-3 py-2">
      {Object.keys(card.args).length > 0 && (
        <div className="mb-2 whitespace-pre-wrap text-ink-muted">
          {JSON.stringify(card.args, null, 2)}
        </div>
      )}
      {card.result !== undefined ? (
        <div className="whitespace-pre-wrap text-ink-secondary">{card.result || "(empty result)"}</div>
      ) : (
        card.status === "running" && <div className="text-ink-muted">running…</div>
      )}
    </MonoPane>
  );
}

/* --------------------------------------------------------- live preview */

/** While the model is still WRITING a tool call, stream its raw arguments
 *  into the card (Cursor-style live edit). Replaced by the real view once
 *  the call completes. */
export function ArgsPreviewPane({ card }: { card: ToolCard }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [card.argsPreview]);
  // Partial JSON with escaped newlines is unreadable — soften for display.
  const text = (card.argsPreview ?? "")
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "  ")
    .replace(/\\"/g, '"');
  return (
    <div
      ref={ref}
      className="max-h-[280px] overflow-auto border-t border-edge-subtle bg-panel-sidebar px-3 py-2 font-mono text-[12.5px] leading-[1.65]"
    >
      <span className="whitespace-pre-wrap text-diff-addtext/90">{text}</span>
      <span className="animate-caret text-ink-secondary">▍</span>
    </div>
  );
}

/* ---------------------------------------------------------------- image */

/** Parse the generate_image result text into display fields. */
function parseImageResult(result?: string): {
  model?: string;
  size?: string;
  verdict?: "PASS" | "FAIL";
  reasoning?: string;
} {
  if (!result) return {};
  const out: ReturnType<typeof parseImageResult> = {};
  const ms = /model:\s*([^\s|]+)\s*\|\s*size:\s*(\S+)/i.exec(result);
  if (ms) {
    out.model = ms[1];
    out.size = ms[2];
  }
  const v = /VERDICT:\s*(PASS|FAIL)/i.exec(result);
  if (v) {
    out.verdict = v[1].toUpperCase() as "PASS" | "FAIL";
    const after = result.slice(v.index + v[0].length).trim();
    out.reasoning = after.split("\n").filter(Boolean).slice(0, 3).join(" ").slice(0, 280);
  }
  return out;
}

/** Rich view for image generation: progressive blur-reveal while generating,
 *  then the image with model/size and the agent's vision self-check verdict. */
export function ImageView({ card }: { card: ToolCard }) {
  const prompt = typeof card.args.prompt === "string" ? card.args.prompt : "";
  const status = card.status;
  const meta = parseImageResult(card.result);
  const images = card.media?.images ?? [];
  const img = images[0];

  return (
    <div className="flex flex-col gap-2.5 border-t border-edge-subtle bg-panel-sidebar px-3 py-3">
      {prompt && (
        <div className="text-[12.5px] leading-relaxed text-ink-secondary">
          <span className="text-ink-muted">prompt:</span> {prompt}
        </div>
      )}

      {status !== "error" && (img || status === "running") ? (
        <ImageGeneration status={status}>
          {img ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={`data:${img.mime};base64,${img.data}`}
              alt={prompt || "generated image"}
              className="block h-auto w-full"
            />
          ) : (
            // Placeholder the blur mask wipes over while we wait for the image.
            <div className="aspect-square w-full bg-[radial-gradient(circle_at_30%_30%,#2a2a32,#15151a)]" />
          )}
        </ImageGeneration>
      ) : (
        card.result && (
          <div className="rounded-lg border border-state-err/40 bg-state-err/5 px-3 py-2 text-[12.5px] text-diff-rmtext">
            {card.result.slice(0, 300)}
          </div>
        )
      )}

      {(meta.model || meta.verdict) && (
        <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
          {meta.model && (
            <span className="rounded-full border border-edge-subtle px-2 py-0.5 font-mono text-ink-muted">
              {meta.model}
              {meta.size ? ` · ${meta.size}` : ""}
            </span>
          )}
          {meta.verdict && (
            <span
              className={clsx(
                "flex items-center gap-1 rounded-full px-2 py-0.5 font-medium",
                meta.verdict === "PASS"
                  ? "bg-state-ok/15 text-state-ok"
                  : "bg-state-err/15 text-diff-rmtext"
              )}
            >
              {meta.verdict === "PASS" ? (
                <CheckCircle2 className="h-3 w-3" />
              ) : (
                <XCircle className="h-3 w-3" />
              )}
              vision self-check: {meta.verdict}
            </span>
          )}
        </div>
      )}
      {meta.reasoning && (
        <div className="text-[12px] italic leading-relaxed text-ink-muted">{meta.reasoning}</div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- browser */

/** View for the browser_* tools: shows the target (url/text), a screenshot if
 *  one was captured, and the page text result. Screenshots arrive as media via
 *  the streaming bridge's image-path detector. */
export function BrowserView({ card }: { card: ToolCard }) {
  const running = card.status === "running";
  const target = (() => {
    const a = card.args;
    if (typeof a.url === "string" && a.url) return a.url;
    if (typeof a.text === "string" && a.text) return `"${a.text}"`;
    if (typeof a.ref === "number") return `element [${a.ref}]`;
    return "";
  })();
  const images = card.media?.images ?? [];

  return (
    <div className="flex flex-col gap-2 border-t border-edge-subtle bg-panel-sidebar px-3 py-2.5">
      {target && (
        <div className="truncate font-mono text-[12px] text-ink-muted">
          <Globe className="mr-1.5 inline h-3.5 w-3.5 -translate-y-px" />
          {target}
        </div>
      )}
      {images.map((img, i) => (
        <motion.img
          key={`shot${i}`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          src={`data:${img.mime};base64,${img.data}`}
          alt="page screenshot"
          className="max-h-[460px] w-auto max-w-full rounded-lg border border-edge-subtle shadow-md"
        />
      ))}
      {running && images.length === 0 ? (
        <div className="text-[12.5px] text-ink-muted">working…</div>
      ) : (
        card.result && (
          <div className="max-h-[280px] overflow-auto whitespace-pre-wrap rounded-lg border border-edge-subtle bg-panel-elevated px-3 py-2 text-[12.5px] leading-relaxed text-ink-secondary">
            {card.result.slice(0, 2500)}
          </div>
        )
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- media */

/** Visual MCP results: images render inline; interactive HTML renders in a
 *  sandboxed iframe (scripts allowed, no same-origin/top-navigation access). */
export function MediaView({ card }: { card: ToolCard }) {
  const m = card.media;
  const uris = m?.uris ?? [];
  if (!m || (m.images.length === 0 && m.html.length === 0 && uris.length === 0)) return null;
  return (
    <div className="flex flex-col gap-2 border-t border-edge-subtle bg-panel-sidebar px-3 py-2.5">
      {m.images.map((img, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={`img${i}`}
          src={`data:${img.mime};base64,${img.data}`}
          alt={`${card.name} output ${i + 1}`}
          className="max-h-[420px] w-auto max-w-full rounded-lg border border-edge-subtle"
        />
      ))}
      {m.html.map((html, i) => (
        <iframe
          key={`html${i}`}
          srcDoc={html}
          sandbox="allow-scripts"
          title={`${card.name} interactive output ${i + 1}`}
          className="h-[360px] w-full rounded-lg border border-edge-subtle bg-white"
        />
      ))}
      {uris.map((uri, i) => (
        <div key={`uri${i}`} className="flex flex-col gap-1">
          <iframe
            src={uri}
            // No allow-same-origin: with allow-scripts that combo lets framed
            // content rewrite its own sandbox and escape. Opaque origin keeps
            // these MCP-supplied app URLs isolated from the Friday UI.
            sandbox="allow-scripts allow-forms allow-popups"
            referrerPolicy="no-referrer"
            title={`${card.name} interactive app ${i + 1}`}
            className="h-[440px] w-full rounded-lg border border-edge-subtle bg-white"
          />
          <a
            href={uri}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 self-end text-[11.5px] text-accent hover:underline"
          >
            <ExternalLink className="h-3 w-3" /> open app in new tab
          </a>
        </div>
      ))}
    </div>
  );
}

function ResultNote({ result, ok, bare }: { result: string; ok: boolean; bare?: boolean }) {
  return (
    <div
      className={clsx(
        "px-3 py-1.5 font-mono text-[12px]",
        !bare && "mt-1 border-t border-edge-subtle",
        bare && "mt-2 px-0",
        ok ? "text-ink-muted" : "text-diff-rmtext"
      )}
    >
      {result.slice(0, 500)}
    </div>
  );
}

/* ------------------------------------------------------------- dispatch */

export type ToolKind =
  | "edit"
  | "write"
  | "terminal"
  | "search"
  | "subagent"
  | "read"
  | "social"
  | "image"
  | "browser"
  | "generic";

export function kindFor(name: string): ToolKind {
  if (["edit_self", "skill_patch", "edit_file", "patch"].includes(name)) return "edit";
  if (
    ["write_self", "skill_create", "skill_edit", "create_tool", "create_mcp_server", "write_file"].includes(
      name
    )
  )
    return "write";
  if (["sandbox_exec", "sandbox_python", "run_command"].includes(name)) return "terminal";
  if (["web_search", "search_web", "search_files", "glob_files", "grep_files"].includes(name)) return "search";
  if (name === "spawn_subagent") return "subagent";
  if (["generate_image", "image_generate", "text_to_image"].includes(name)) return "image";
  if (name.startsWith("browser_")) return "browser";
  if (name.startsWith("computer_") || name === "apply_computer_action") return "browser";
  if (["read_self", "read_file", "skill_view", "fetch_url"].includes(name)) return "read";
  if (
    [
      "queue_post",
      "draft_campaign",
      "confirm_publish",
      "confirm_campaign",
      "adjust_budget",
    ].includes(name)
  )
    return "social";
  return "generic";
}

export function viewFor(card: ToolCard): React.ReactNode {
  switch (kindFor(card.name)) {
    case "edit":
      return <DiffView card={card} />;
    case "write":
      return <FileWriteView card={card} />;
    case "terminal":
      return <TerminalView card={card} />;
    case "search":
      return <SearchView card={card} />;
    case "subagent":
      return <SubagentView card={card} />;
    case "image":
      return <ImageView card={card} />;
    case "browser":
      return <BrowserView card={card} />;
    case "read":
      return <CodeView card={card} />;
    case "social":
      return <SocialView card={card} />;
    default:
      return <GenericView card={card} />;
  }
}
