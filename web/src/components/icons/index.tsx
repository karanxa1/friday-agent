/**
 * Friday custom icon set — transparent strokes, no backgrounds, modern geometric style.
 * Distinct from Lucide: asymmetric cuts, dual-radius corners, orbital motifs.
 */
import clsx from "clsx";
import { createIcon, Icon, type IconProps } from "./Icon";

// ── Navigation & shell ─────────────────────────────────────────────────────

export const MessageSquare = createIcon("MessageSquare", (
  <>
    <path d="M5 6.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3.5V8.5a2 2 0 0 1 2-2z" />
    <path d="M8.5 11h7M8.5 14.5h4" strokeOpacity="0.55" />
  </>
));

export const BookOpen = createIcon("BookOpen", (
  <>
    <path d="M5 5.5c0-1 1.2-1.8 2.5-1.5L12 5l4.5-1c1.3-.3 2.5.5 2.5 1.5V18c0 1-1.2 1.6-2.3 1.2L12 17.5l-4.7 1.7c-1.1.4-2.3-.2-2.3-1.2z" />
    <path d="M12 5v12.5" strokeOpacity="0.4" />
  </>
));

export const Brain = createIcon("Brain", (
  <>
    <path d="M9 5.5c-2 0-3.5 1.6-3.5 3.5 0 1.2.6 2.2 1.5 2.8-.4.7-.6 1.5-.6 2.3 0 2.2 1.8 4 4 4h.5" />
    <path d="M15 5.5c2 0 3.5 1.6 3.5 3.5 0 1.2-.6 2.2-1.5 2.8.4.7.6 1.5.6 2.3 0 2.2-1.8 4-4 4h-.5" />
    <circle cx="9" cy="9" r="0.9" fill="currentColor" stroke="none" />
    <circle cx="15" cy="9" r="0.9" fill="currentColor" stroke="none" />
    <path d="M10.5 13.5h3" strokeOpacity="0.5" />
  </>
));

export const History = createIcon("History", (
  <>
    <path d="M12 4.5v3l2.5 1.5" />
    <path d="M5.2 7.2A7.5 7.5 0 1 0 12 4.5" />
    <path d="M4 4.5H2.5M4 4.5V6" strokeOpacity="0.6" />
  </>
));

export const Server = createIcon("Server", (
  <>
    <rect x="4" y="5" width="16" height="5" rx="1.5" />
    <rect x="4" y="12" width="16" height="5" rx="1.5" />
    <circle cx="7.5" cy="7.5" r="0.75" fill="currentColor" stroke="none" />
    <circle cx="7.5" cy="14.5" r="0.75" fill="currentColor" stroke="none" />
    <path d="M17 7.5h2M17 14.5h2" strokeOpacity="0.45" />
  </>
));

export const Settings = createIcon("Settings", (
  <>
    <circle cx="12" cy="12" r="2.25" />
    <path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2" />
    <path d="M6.1 6.1l1.4 1.4M16.5 16.5l1.4 1.4M6.1 17.9l1.4-1.4M16.5 7.5l1.4-1.4" strokeOpacity="0.55" />
  </>
));

export const Settings2 = Settings;

export const Zap = createIcon("Zap", (
  <path d="M13.5 3.5L6.5 13h5l-1 7.5L17.5 11h-5l1-7.5z" />
));

export const Menu = createIcon("Menu", (
  <>
    <path d="M4.5 7h15M4.5 12h11M4.5 17h7" />
  </>
));

export const PanelRight = createIcon("PanelRight", (
  <>
    <rect x="4" y="4.5" width="16" height="15" rx="2" />
    <path d="M14 4.5v15" />
    <path d="M17 9h2M17 12h2" strokeOpacity="0.45" />
  </>
));

export const Laptop = createIcon("Laptop", (
  <>
    <rect x="5" y="6" width="14" height="9" rx="1.5" />
    <path d="M3.5 17.5h17" strokeWidth="2" />
  </>
));

// ── Actions ───────────────────────────────────────────────────────────────

export const Plus = createIcon("Plus", (
  <path d="M12 5.5v13M5.5 12h13" />
));

export const X = createIcon("X", (
  <path d="M7 7l10 10M17 7L7 17" />
));

export const Check = createIcon("Check", (
  <path d="M6 12.5l4 4 8-8.5" strokeWidth="2" />
));

export const Copy = createIcon("Copy", (
  <>
    <rect x="8.5" y="8.5" width="10" height="10" rx="1.5" />
    <path d="M6.5 15.5V6.5a2 2 0 0 1 2-2H15.5" strokeOpacity="0.65" />
  </>
));

export const Trash2 = createIcon("Trash2", (
  <>
    <path d="M5 7.5h14M9 7.5V5.5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    <path d="M7.5 7.5l.75 11a1.5 1.5 0 0 0 1.5 1.5h6.5a1.5 1.5 0 0 0 1.5-1.5l.75-11" />
    <path d="M10 11v5M14 11v5" strokeOpacity="0.5" />
  </>
));

export const ArrowUp = createIcon("ArrowUp", (
  <>
    <path d="M12 18.5V6" />
    <path d="M7.5 10.5L12 6l4.5 4.5" />
  </>
));

export const ArrowLeft = createIcon("ArrowLeft", (
  <>
    <path d="M5.5 12h13" />
    <path d="M10.5 7.5L5.5 12l5 4.5" />
  </>
));

export const ArrowRight = createIcon("ArrowRight", (
  <>
    <path d="M5.5 12h13" />
    <path d="M13.5 7.5L18.5 12l-5 4.5" />
  </>
));

export const ChevronDown = createIcon("ChevronDown", (
  <path d="M7 9.5l5 5 5-5" />
));

export const Square = createIcon("Square", (
  <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none" />
));

export const SquarePen = createIcon("SquarePen", (
  <>
    <path d="M14.5 4.5l4 4L9 18.5H5.5V15l9.5-9.5z" />
    <path d="M13 6l3 3" strokeOpacity="0.45" />
  </>
));

export const Paperclip = createIcon("Paperclip", (
  <path d="M8.5 13.5a3.5 3.5 0 0 0 7 0V7.5a2.5 2.5 0 0 0-5 0v7a1.5 1.5 0 0 0 3 0V8" />
));

export const Pin = createIcon("Pin", (
  <>
    <path d="M12 3.5v9" />
    <path d="M8.5 9.5h7l-2 4.5H9.5l-1 4" />
  </>
));

export const Plug = createIcon("Plug", (
  <>
    <path d="M9 6.5V4M15 6.5V4" />
    <path d="M6.5 9.5h11v5a4 4 0 0 1-4 4h-3a4 4 0 0 1-4-4z" />
    <path d="M12 14.5v3" />
  </>
));

export const KeyRound = createIcon("KeyRound", (
  <>
    <circle cx="9" cy="11" r="3.5" />
    <path d="M11.5 13.5l7 7M16 16l2 2" />
  </>
));

export const ExternalLink = createIcon("ExternalLink", (
  <>
    <path d="M11 5.5h7.5V13" />
    <path d="M8.5 15.5H18.5V5.5" strokeOpacity="0.55" />
    <path d="M14 5.5l4 4" />
  </>
));

// ── Status ──────────────────────────────────────────────────────────────────

export const AlertCircle = createIcon("AlertCircle", (
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 8.5v5" />
    <circle cx="12" cy="16" r="0.75" fill="currentColor" stroke="none" />
  </>
));

export const CheckCircle2 = createIcon("CheckCircle2", (
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M8 12l2.5 2.5L16 9" strokeWidth="2" />
  </>
));

export const XCircle = createIcon("XCircle", (
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9 9l6 6M15 9l-6 6" />
  </>
));

export const Shield = createIcon("Shield", (
  <path d="M12 3.5l7 3v5.5c0 4.5-3 7.5-7 8.5-4-1-7-4-7-8.5V6.5l7-3z" />
));

export const ShieldAlert = createIcon("ShieldAlert", (
  <>
    <path d="M12 3.5l7 3v5.5c0 4.5-3 7.5-7 8.5-4-1-7-4-7-8.5V6.5l7-3z" />
    <path d="M12 8.5v4" />
    <circle cx="12" cy="16" r="0.75" fill="currentColor" stroke="none" />
  </>
));

export function Loader2({ className, ...props }: IconProps) {
  return (
    <Icon className={clsx("animate-spin", className)} {...props}>
      <circle cx="12" cy="12" r="8.5" strokeOpacity="0.2" />
      <path d="M12 3.5a8.5 8.5 0 0 1 8.5 8.5" strokeWidth="2" />
    </Icon>
  );
}

// ── Content & files ─────────────────────────────────────────────────────────

export const FileText = createIcon("FileText", (
  <>
    <path d="M8 4.5h6l4 4v11.5a1.5 1.5 0 0 1-1.5 1.5H8a1.5 1.5 0 0 1-1.5-1.5v-14A1.5 1.5 0 0 1 8 4.5z" />
    <path d="M14 4.5v4h4M9 12h6M9 15h4" strokeOpacity="0.5" />
  </>
));

export const ImageIcon = createIcon("ImageIcon", (
  <>
    <rect x="4.5" y="5.5" width="15" height="13" rx="2" />
    <circle cx="9" cy="10" r="1.5" />
    <path d="M4.5 16l5-4.5 3 2.5L19.5 9" />
  </>
));

export const Archive = createIcon("Archive", (
  <>
    <rect x="4" y="5" width="16" height="4" rx="1" />
    <path d="M6 9v9.5a1.5 1.5 0 0 0 1.5 1.5h9a1.5 1.5 0 0 0 1.5-1.5V9" />
    <path d="M10 13h4" strokeOpacity="0.5" />
  </>
));

export const Download = createIcon("Download", (
  <>
    <path d="M12 4.5v9" />
    <path d="M8.5 11l3.5 3.5L15.5 11" />
    <path d="M5.5 18.5h13" />
  </>
));

export const StickyNote = createIcon("StickyNote", (
  <>
    <path d="M8 4.5h8l3.5 3.5V18a1.5 1.5 0 0 1-1.5 1.5H8A1.5 1.5 0 0 1 6.5 18V6a1.5 1.5 0 0 1 1.5-1.5z" />
    <path d="M16 4.5v4h4" strokeOpacity="0.45" />
  </>
));

// ── Tools & workspace ─────────────────────────────────────────────────────────

export const Search = createIcon("Search", (
  <>
    <circle cx="11" cy="11" r="5.5" />
    <path d="M15.5 15.5L19 19" strokeWidth="2" />
  </>
));

export const Pencil = createIcon("Pencil", (
  <path d="M16.5 4.5l3 3L9.5 18.5H6.5v-3l10-10z" />
));

export const Terminal = createIcon("Terminal", (
  <>
    <rect x="4" y="5.5" width="16" height="13" rx="2" />
    <path d="M7.5 10.5l2.5 2-2.5 2M11.5 14.5h5" />
  </>
));

export const Globe = createIcon("Globe", (
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17M12 3.5c2.5 2.8 2.5 13.2 0 16M12 3.5c-2.5 2.8-2.5 13.2 0 16" strokeOpacity="0.45" />
  </>
));

export const FolderTree = createIcon("FolderTree", (
  <>
    <path d="M4.5 7.5h5l2 2h8.5v9a1.5 1.5 0 0 1-1.5 1.5H6a1.5 1.5 0 0 1-1.5-1.5z" />
    <path d="M4.5 7.5V6a1.5 1.5 0 0 1 1.5-1.5h4l2 2" strokeOpacity="0.55" />
    <path d="M9.5 13h5M9.5 16h3" strokeOpacity="0.4" />
  </>
));

export const Eye = createIcon("Eye", (
  <>
    <path d="M3.5 12s3.5-6 8.5-6 8.5 6 8.5 6-3.5 6-8.5 6-8.5-6-8.5-6z" />
    <circle cx="12" cy="12" r="2.25" />
  </>
));

export const Wrench = createIcon("Wrench", (
  <path d="M14.5 6.5a4.5 4.5 0 0 1-1.2 8.8L6.5 18.5l-1.5-1.5 6.8-6.8A4.5 4.5 0 0 1 14.5 6.5z" />
));

export const Network = createIcon("Network", (
  <>
    <circle cx="6" cy="6" r="2.25" />
    <circle cx="18" cy="6" r="2.25" />
    <circle cx="12" cy="18" r="2.25" />
    <path d="M7.8 7.8l3.2 7.2M16.2 7.8l-3.2 7.2" strokeOpacity="0.55" />
  </>
));

export const GitBranch = createIcon("GitBranch", (
  <>
    <circle cx="7" cy="6" r="2.25" />
    <circle cx="7" cy="18" r="2.25" />
    <circle cx="17" cy="10" r="2.25" />
    <path d="M7 8.25v7.5M7 10h7.75a2 2 0 0 1 2 2v0" />
  </>
));

export const Hammer = createIcon("Hammer", (
  <>
    <path d="M14 4.5l5.5 5.5-2 2-5.5-5.5z" />
    <path d="M6.5 13.5l4 4 2.5-2.5-4-4z" />
    <path d="M4.5 19.5l2-2" strokeWidth="2" />
  </>
));

export const Megaphone = createIcon("Megaphone", (
  <>
    <path d="M5 10.5h4l6.5-3.5v11L9 14.5H5a1.5 1.5 0 0 1-1.5-1.5v-3A1.5 1.5 0 0 1 5 10.5z" />
    <path d="M16.5 7v10" strokeOpacity="0.45" />
    <path d="M5 14.5v3a1.5 1.5 0 0 0 1.5 1.5H9" />
  </>
));

export const ListTodo = createIcon("ListTodo", (
  <>
    <path d="M9 7.5l1.5 1.5L13 7" strokeWidth="2" />
    <path d="M9 12.5l1.5 1.5L13 12" strokeWidth="2" />
    <path d="M15 7.5h5M15 12.5h5" strokeOpacity="0.45" />
    <path d="M5 18.5h14" strokeOpacity="0.35" />
  </>
));

export const Monitor = createIcon("Monitor", (
  <>
    <rect x="3.5" y="5" width="17" height="11" rx="2" />
    <path d="M9 19.5h6" />
    <path d="M12 16v3.5" />
  </>
));

export const Camera = createIcon("Camera", (
  <>
    <path d="M5 8.5h3l1.5-2h6l1.5 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z" />
    <circle cx="12" cy="13" r="2.75" />
  </>
));

export const MousePointerClick = createIcon("MousePointerClick", (
  <>
    <path d="M12 4.5v5.5l-3 3" />
    <path d="M9 9.5L5.5 6" />
    <circle cx="17" cy="8" r="2" strokeOpacity="0.55" />
    <path d="M17 6.5v3M15.5 8h3" strokeOpacity="0.55" />
  </>
));

// ── Agents & users ──────────────────────────────────────────────────────────

export const Bot = createIcon("Bot", (
  <>
    <rect x="5.5" y="8.5" width="13" height="9" rx="2.5" />
    <path d="M9.5 8.5V6.5a2.5 2.5 0 0 1 5 0v2" />
    <circle cx="9.5" cy="13" r="1" fill="currentColor" stroke="none" />
    <circle cx="14.5" cy="13" r="1" fill="currentColor" stroke="none" />
    <path d="M10.5 16h3" strokeOpacity="0.45" />
  </>
));

export const User = createIcon("User", (
  <>
    <circle cx="12" cy="9" r="3.25" />
    <path d="M6 19.5c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" />
  </>
));

/** Friday brand mark — caduceus-inspired minimal glyph, no background. */
export const FridayMark = createIcon("FridayMark", (
  <>
    <path d="M12 3.5v16" strokeOpacity="0.35" />
    <path d="M9 6.5c2 2 4 2 6 0M9 17.5c2-2 4-2 6 0" />
    <circle cx="12" cy="12" r="1.25" fill="currentColor" stroke="none" />
  </>
));
