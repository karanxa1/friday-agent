"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  Search,
  FileText,
  Pencil,
  Terminal,
  Globe,
  FolderTree,
  Brain,
  Check,
  AlertCircle,
  Loader2,
  Eye,
  Wrench,
  Network,
  ShieldAlert,
  KeyRound,
  Megaphone,
  GitBranch,
  Hammer,
  Server,
  StickyNote,
  Download,
  ListTodo,
  History,
  ImageIcon,
  MousePointerClick,
  Camera,
  Monitor,
} from "@/components/icons";
import clsx from "clsx";
import type { ToolCard as ToolCardType } from "@/lib/types";
import { ArgsPreviewPane, diffStat, kindFor, MediaView, viewFor } from "./tool-views";

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  search_web: Globe,
  web_search: Globe,
  search_files: Search,
  glob_files: Search,
  grep_files: Search,
  run_command: Terminal,
  patch: Pencil,
  read_self: FileText,
  read_file: FileText,
  write_self: Pencil,
  edit_self: Pencil,
  validate_self: Check,
  git_snapshot: GitBranch,
  git_revert: GitBranch,
  skill_create: FileText,
  skill_edit: Pencil,
  skill_patch: Pencil,
  skill_view: FileText,
  skill_list: FolderTree,
  skill_delete: FolderTree,
  sandbox_exec: Terminal,
  sandbox_python: Terminal,
  sandbox_status: Terminal,
  spawn_subagent: Network,
  analyze_image: Eye,
  generate_image: ImageIcon,
  browser_navigate: Globe,
  browser_snapshot: MousePointerClick,
  browser_click: MousePointerClick,
  browser_type: MousePointerClick,
  browser_screenshot: Camera,
  browser_extract_text: Globe,
  browser_back: Globe,
  browser_close: Globe,
  computer_screenshot: Monitor,
  computer_screen_info: Monitor,
  computer_click: MousePointerClick,
  computer_type: MousePointerClick,
  computer_key: MousePointerClick,
  computer_scroll: MousePointerClick,
  apply_computer_action: Monitor,
  get_metrics: Brain,
  take_note: StickyNote,
  now_utc: Wrench,
  create_tool: Hammer,
  create_mcp_server: Server,
  apply_capability: Hammer,
  list_capabilities: Hammer,
  request_credential: KeyRound,
  list_credentials: KeyRound,
  credential_status: KeyRound,
  list_files: FolderTree,
  write_file: Pencil,
  edit_file: Pencil,
  delete_file: FolderTree,
  fetch_url: Globe,
  download_file: Download,
  todo_add: ListTodo,
  todo_list: ListTodo,
  todo_done: ListTodo,
  todo_clear: ListTodo,
  recall_search: Search,
  recent_activity: History,
  list_all_tools: Wrench,
  queue_post: Megaphone,
  draft_campaign: Megaphone,
  confirm_publish: Megaphone,
  confirm_campaign: Megaphone,
  list_queue: Megaphone,
  list_campaigns: Megaphone,
  adjust_budget: Megaphone,
};

// Tools whose effects pass through the human-approval queue.
const GATED = new Set([
  "write_self",
  "edit_self",
  "create_tool",
  "create_mcp_server",
  "confirm_publish",
  "confirm_campaign",
  "request_credential",
  "git_revert",
]);

const VERBS: Record<string, [string, string]> = {
  search_web: ["Searching the web", "Searched the web"],
  web_search: ["Searching the web", "Searched the web"],
  search_files: ["Searching files", "Searched files"],
  glob_files: ["Finding files", "Found files"],
  grep_files: ["Searching contents", "Searched contents"],
  run_command: ["Running command", "Ran command"],
  patch: ["Editing file", "Edited file"],
  read_self: ["Reading file", "Read file"],
  read_file: ["Reading file", "Read file"],
  write_self: ["Writing file", "Wrote file"],
  edit_self: ["Editing file", "Edited file"],
  validate_self: ["Validating code", "Validated code"],
  git_snapshot: ["Committing snapshot", "Committed snapshot"],
  git_revert: ["Reverting commit", "Reverted commit"],
  skill_create: ["Creating skill", "Created skill"],
  skill_edit: ["Editing skill", "Edited skill"],
  skill_patch: ["Patching skill", "Patched skill"],
  skill_view: ["Reading skill", "Read skill"],
  skill_list: ["Listing skills", "Listed skills"],
  skill_delete: ["Deleting skill", "Deleted skill"],
  sandbox_exec: ["Running command", "Ran command"],
  sandbox_python: ["Running Python", "Ran Python"],
  sandbox_status: ["Checking sandbox", "Checked sandbox"],
  spawn_subagent: ["Delegating to subagent", "Subagent finished"],
  get_metrics: ["Fetching metrics", "Fetched metrics"],
  analyze_image: ["Analyzing image", "Analyzed image"],
  generate_image: ["Generating image", "Generated image"],
  browser_navigate: ["Opening page", "Opened page"],
  browser_snapshot: ["Scanning page", "Scanned page"],
  browser_click: ["Clicking", "Clicked"],
  browser_type: ["Typing", "Typed"],
  browser_screenshot: ["Capturing screenshot", "Captured screenshot"],
  browser_extract_text: ["Reading page", "Read page"],
  browser_back: ["Going back", "Went back"],
  browser_close: ["Closing browser", "Closed browser"],
  computer_screenshot: ["Capturing screen", "Captured screen"],
  computer_screen_info: ["Reading screen", "Read screen"],
  computer_click: ["Clicking", "Clicked"],
  computer_type: ["Typing", "Typed"],
  computer_key: ["Pressing key", "Pressed key"],
  computer_scroll: ["Scrolling", "Scrolled"],
  apply_computer_action: ["Performing action", "Performed action"],
  take_note: ["Saving note", "Saved note"],
  create_tool: ["Authoring new tool", "Authored new tool"],
  create_mcp_server: ["Authoring MCP server", "Authored MCP server"],
  apply_capability: ["Applying capability", "Applied capability"],
  request_credential: ["Requesting credential", "Requested credential"],
  list_files: ["Listing files", "Listed files"],
  write_file: ["Writing file", "Wrote file"],
  edit_file: ["Editing file", "Edited file"],
  delete_file: ["Deleting file", "Deleted file"],
  fetch_url: ["Fetching page", "Fetched page"],
  download_file: ["Downloading file", "Downloaded file"],
  todo_add: ["Adding todo", "Added todo"],
  todo_list: ["Reading todos", "Read todos"],
  todo_done: ["Completing todo", "Completed todo"],
  todo_clear: ["Clearing todos", "Cleared todos"],
  recall_search: ["Searching memory", "Searched memory"],
  recent_activity: ["Reading activity", "Read activity"],
  list_all_tools: ["Discovering tools", "Discovered tools"],
  queue_post: ["Queueing post", "Queued post"],
  draft_campaign: ["Drafting campaign", "Drafted campaign"],
  confirm_publish: ["Publishing", "Published"],
  confirm_campaign: ["Launching campaign", "Launched campaign"],
  adjust_budget: ["Adjusting budget", "Adjusted budget"],
};

function titleFor(name: string, status: string): string {
  const pair = VERBS[name];
  if (!pair) return status === "running" ? `Running ${name}` : name;
  return status === "running" ? pair[0] : pair[1];
}

function targetFor(args: Record<string, unknown>): string {
  const keys = ["query", "path", "name", "task", "command", "code", "image_path", "platform", "service", "note"];
  for (const k of keys) {
    if (args[k]) return String(args[k]).replace(/\s+/g, " ").slice(0, 80);
  }
  return "";
}

// Kinds that auto-expand so the work is visible as it happens (Cursor-style).
const AUTO_OPEN = new Set(["edit", "write", "terminal", "search", "subagent", "image", "browser"]);

export function ToolCard({ card }: { card: ToolCardType }) {
  const kind = kindFor(card.name);
  const [open, setOpen] = useState(AUTO_OPEN.has(kind));
  const Icon = ICONS[card.name] ?? Wrench;
  const running = card.status === "running";
  const stat = kind === "edit" || kind === "write" ? diffStat(card) : null;
  const stripe =
    card.status === "running"
      ? "border-l-state-run"
      : card.status === "error"
        ? "border-l-state-err"
        : "border-l-state-ok";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.985 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      className={clsx(
        "group/card relative my-2 overflow-hidden rounded-xl border border-edge-subtle bg-panel-elevated border-l-2 transition-colors duration-300",
        stripe
      )}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-full items-center gap-2.5 px-3 transition-colors hover:bg-panel-hover"
      >
        <Icon className={clsx("h-4 w-4 shrink-0", running ? "text-state-run" : "text-ink-secondary")} />
        <span
          className={clsx(
            "shrink-0 text-[13.5px] font-medium",
            running
              ? "bg-[linear-gradient(90deg,#a8a8a8,rgba(255,255,255,0.9),#a8a8a8)] bg-[length:200%_100%] animate-shimmer bg-clip-text text-transparent"
              : "text-ink-secondary"
          )}
        >
          {titleFor(card.name, card.status)}
        </span>
        {targetFor(card.args) && (
          <span className="truncate font-mono text-[12.5px] text-ink-muted">{targetFor(card.args)}</span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {GATED.has(card.name) && (
            <span className="flex items-center gap-1 rounded-full border border-state-run/40 bg-state-run/10 px-2 py-0.5 text-[10.5px] text-state-run">
              <ShieldAlert className="h-3 w-3" /> needs approval
            </span>
          )}
          {stat && (
            <span className="font-mono text-[11.5px]">
              <span className="text-diff-addtext">+{stat.added}</span>{" "}
              {stat.removed > 0 && <span className="text-diff-rmtext">−{stat.removed}</span>}
            </span>
          )}
          <AnimatePresence mode="popLayout" initial={false}>
            {card.status === "running" && (
              <motion.span
                key="run"
                initial={{ scale: 0.6, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.6, opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <Loader2 className="h-4 w-4 animate-spin text-state-run" />
              </motion.span>
            )}
            {card.status === "done" && (
              <motion.span
                key="done"
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: [0.5, 1.25, 1], opacity: 1 }}
                transition={{ duration: 0.35 }}
              >
                <Check className="h-4 w-4 text-state-ok" />
              </motion.span>
            )}
            {card.status === "error" && (
              <motion.span
                key="err"
                initial={{ x: 0, opacity: 0 }}
                animate={{ x: [0, -3, 3, -2, 0], opacity: 1 }}
                transition={{ duration: 0.35 }}
              >
                <AlertCircle className="h-4 w-4 text-state-err" />
              </motion.span>
            )}
          </AnimatePresence>
          <ChevronDown
            className={clsx(
              "h-4 w-4 text-ink-muted transition-transform duration-200",
              open && "rotate-180"
            )}
          />
        </span>
      </button>

      {/* indeterminate progress bar while the tool runs (sits flush under header) */}
      <AnimatePresence>
        {running && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="h-[2px] w-full overflow-hidden bg-state-run/15"
          >
            <div className="h-full w-1/3 animate-progress rounded-full bg-state-run" />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="overflow-hidden"
          >
            {card.argsPreview && Object.keys(card.args).length === 0 ? (
              <ArgsPreviewPane card={card} />
            ) : (
              <>
                {viewFor(card)}
                {/* ImageView/BrowserView render media themselves; avoid double-render. */}
                {kind !== "image" && kind !== "browser" && <MediaView card={card} />}
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
