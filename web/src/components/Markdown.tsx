"use client";

import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "@/components/icons";
import clsx from "clsx";

/**
 * One shared Markdown renderer for everything in the chat — assistant answers,
 * thinking text, and tool result text. GitHub-flavored markdown is on (tables,
 * task lists, strikethrough, autolinks) and every element gets a styled
 * renderer so tables, code blocks, lists, quotes, headings etc. all look right
 * in the dark Cursor-style theme.
 *
 * Styling lives mostly in the `.md` scope in globals.css; this map adds the
 * pieces that need structure or behaviour (code copy button, safe links,
 * scrollable table wrapper).
 */

function CodeBlock({ language, value }: { language: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    });
  };
  return (
    <div className="group/code relative my-3 overflow-hidden rounded-lg border border-edge-subtle bg-[#0d0d0f]">
      <div className="flex h-8 items-center justify-between border-b border-edge-subtle bg-panel-elevated/60 px-3">
        <span className="font-mono text-[11px] uppercase tracking-wide text-ink-muted">
          {language || "code"}
        </span>
        <button
          onClick={copy}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-ink-muted opacity-0 transition hover:bg-panel-hover hover:text-ink group-hover/code:opacity-100"
        >
          {copied ? <Check className="h-3 w-3 text-state-ok" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3.5 py-3 text-[12.5px] leading-relaxed">
        <code className="font-mono text-ink">{value}</code>
      </pre>
    </div>
  );
}

const components: Components = {
  // Fenced blocks become CodeBlock; inline code stays inline.
  code({ className, children, ...props }) {
    const text = String(children ?? "").replace(/\n$/, "");
    const match = /language-(\w+)/.exec(className || "");
    const isBlock = match || text.includes("\n");
    if (isBlock) {
      return <CodeBlock language={match?.[1] ?? ""} value={text} />;
    }
    return (
      <code
        className="rounded bg-panel-active px-1.5 py-0.5 font-mono text-[0.85em] text-accent"
        {...props}
      >
        {children}
      </code>
    );
  },
  // react-markdown wraps our CodeBlock in <pre>; unwrap to avoid nested blocks.
  pre({ children }) {
    return <>{children}</>;
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
      >
        {children}
      </a>
    );
  },
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto rounded-lg border border-edge-subtle">
        <table className="w-full border-collapse text-[13px]">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return <thead className="bg-panel-elevated/70">{children}</thead>;
  },
  th({ children, style }) {
    return (
      <th
        style={style}
        className="border-b border-edge-subtle px-3 py-2 text-left font-semibold text-ink-secondary"
      >
        {children}
      </th>
    );
  },
  td({ children, style }) {
    return (
      <td style={style} className="border-b border-edge-subtle/60 px-3 py-2 align-top text-ink">
        {children}
      </td>
    );
  },
  tr({ children }) {
    return <tr className="transition-colors hover:bg-panel-hover/40">{children}</tr>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-3 border-l-2 border-accent/50 pl-3 text-ink-secondary italic">
        {children}
      </blockquote>
    );
  },
  ul({ children }) {
    return <ul className="my-2 list-disc space-y-1 pl-5 marker:text-ink-muted">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-ink-muted">{children}</ol>;
  },
  li({ children, className }) {
    // GFM task-list items carry a checkbox input as the first child.
    const isTask = className?.includes("task-list-item");
    return (
      <li className={clsx(isTask && "list-none -ml-5 flex items-start gap-2")}>{children}</li>
    );
  },
  input({ checked, type }) {
    if (type !== "checkbox") return null;
    return (
      <span
        className={clsx(
          "mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[4px] border",
          checked ? "border-state-ok bg-state-ok/20 text-state-ok" : "border-edge-strong"
        )}
      >
        {checked && <Check className="h-2.5 w-2.5" />}
      </span>
    );
  },
  h1: ({ children }) => <h1 className="mt-4 mb-2 text-[19px] font-semibold text-ink">{children}</h1>,
  h2: ({ children }) => <h2 className="mt-4 mb-2 text-[17px] font-semibold text-ink">{children}</h2>,
  h3: ({ children }) => <h3 className="mt-3 mb-1.5 text-[15px] font-semibold text-ink">{children}</h3>,
  h4: ({ children }) => <h4 className="mt-3 mb-1.5 text-[14px] font-semibold text-ink-secondary">{children}</h4>,
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  hr: () => <hr className="my-4 border-edge-subtle" />,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  del: ({ children }) => <del className="text-ink-muted line-through">{children}</del>,
  img: ({ src, alt }) =>
    typeof src === "string" ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt={alt ?? ""} className="my-3 max-w-full rounded-lg border border-edge-subtle" />
    ) : null,
};

export function Markdown({ children }: { children: string }): ReactNode {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  );
}
