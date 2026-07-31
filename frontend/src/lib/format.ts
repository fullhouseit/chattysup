/**
 * Presentation helpers: compact relative times, byte sizes, initials and the
 * deterministic avatar palette used wherever a person has no picture.
 */
import { format, isThisYear, isToday, isYesterday, parseISO } from "date-fns";

/** Parse an ISO-8601 string coming from the API (tolerates `null`). */
export function toDate(value: string | number | Date | null | undefined): Date | null {
  if (!value) return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const date = typeof value === "number" ? new Date(value) : parseISO(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Chatwoot-style compact age: `now`, `25m`, `3h`, `2d`, `3mo`, `2y`.
 */
export function relativeTime(value: string | Date | null | undefined): string {
  const date = toDate(value ?? null);
  if (!date) return "";
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return "now";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.floor(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = hours / 24;
  if (days < 7) return `${Math.floor(days)}d`;
  const weeks = days / 7;
  if (days < 30) return `${Math.floor(weeks)}w`;
  const months = days / 30.44;
  if (months < 12) return `${Math.floor(months)}mo`;
  return `${Math.floor(days / 365.25)}y`;
}

/** `3mo • 25m` — conversation age followed by the age of the last message. */
export function conversationAges(
  createdAt: string | null | undefined,
  lastActivityAt: string | null | undefined,
): string {
  const created = relativeTime(createdAt);
  const last = relativeTime(lastActivityAt);
  if (created && last) return `${created} • ${last}`;
  return created || last;
}

/** `14:32` for today, `Yesterday 14:32`, `12 Mar 14:32`, `12 Mar 2023 14:32`. */
export function messageTimestamp(value: string | null | undefined): string {
  const date = toDate(value ?? null);
  if (!date) return "";
  if (isToday(date)) return format(date, "HH:mm");
  if (isYesterday(date)) return `Yesterday ${format(date, "HH:mm")}`;
  if (isThisYear(date)) return format(date, "d MMM HH:mm");
  return format(date, "d MMM yyyy HH:mm");
}

/** Day separator label used between message groups. */
export function dayLabel(value: string | null | undefined): string {
  const date = toDate(value ?? null);
  if (!date) return "";
  if (isToday(date)) return "Today";
  if (isYesterday(date)) return "Yesterday";
  if (isThisYear(date)) return format(date, "EEEE, d MMMM");
  return format(date, "d MMMM yyyy");
}

/** Absolute timestamp for tooltips. */
export function fullTimestamp(value: string | null | undefined): string {
  const date = toDate(value ?? null);
  return date ? format(date, "EEE d MMM yyyy, HH:mm") : "";
}

/** `1.4 MB` — binary units, one decimal above the kilobyte. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return "";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

/** `mm:ss` (or `h:mm:ss`) for audio/video durations given in seconds. */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds < 0 || !Number.isFinite(seconds)) return "0:00";
  const total = Math.floor(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const mm = hrs ? String(mins).padStart(2, "0") : String(mins);
  return `${hrs ? `${hrs}:` : ""}${mm}:${String(secs).padStart(2, "0")}`;
}

/** Up to two uppercase initials from a display name. */
export function initials(name: string | null | undefined): string {
  const parts = (name ?? "")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (!parts.length) return "?";
  return parts.map((part) => part[0]!.toUpperCase()).join("");
}

const AVATAR_PALETTE = [
  { bg: "#DBEAFE", fg: "#1D4ED8" },
  { bg: "#DCFCE7", fg: "#15803D" },
  { bg: "#FEF3C7", fg: "#B45309" },
  { bg: "#FCE7F3", fg: "#BE185D" },
  { bg: "#EDE9FE", fg: "#6D28D9" },
  { bg: "#CCFBF1", fg: "#0F766E" },
  { bg: "#FFE4E6", fg: "#BE123C" },
  { bg: "#E0E7FF", fg: "#4338CA" },
];

/** Stable background/foreground pair derived from a seed string. */
export function avatarColor(seed: string | number | null | undefined): {
  bg: string;
  fg: string;
} {
  const text = String(seed ?? "");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0;
  }
  return AVATAR_PALETTE[Math.abs(hash) % AVATAR_PALETTE.length]!;
}

/** Clamp a long string, appending an ellipsis. */
export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}

/** Turn `snake_case` / `kebab-case` keys into `Title Case` labels. */
export function humanize(key: string): string {
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Escape a string for safe insertion into HTML. */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const URL_PATTERN = /(https?:\/\/[^\s<]+[^\s<.,:;"')\]}])/g;

/**
 * Render plain message text as safe HTML: escapes everything, then linkifies
 * URLs and applies the lightweight `*bold*` / `_italic_` / `` `code` `` marks
 * the composer's formatting toolbar produces.
 */
export function renderMessageHtml(text: string): string {
  let html = escapeHtml(text);
  html = html.replace(
    URL_PATTERN,
    (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`,
  );
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/(^|\W)\*([^*\n]+)\*(?=\W|$)/g, "$1<strong>$2</strong>");
  html = html.replace(/(^|\W)_([^_\n]+)_(?=\W|$)/g, "$1<em>$2</em>");
  return html;
}

/** One-line preview of a message for the conversation list. */
export function messagePreview(
  content: string | null | undefined,
  attachmentType?: string | null,
): string {
  const text = (content ?? "").replace(/\s+/g, " ").trim();
  if (text) return text;
  switch (attachmentType) {
    case "image":
      return "📷 Photo";
    case "video":
    case "video_note":
      return "🎬 Video";
    case "voice":
      return "🎤 Voice message";
    case "audio":
      return "🎵 Audio";
    case "sticker":
      return "Sticker";
    case "animation":
      return "GIF";
    case "location":
      return "📍 Location";
    case "contact_card":
      return "👤 Contact";
    case "file":
      return "📎 Attachment";
    default:
      return "No messages yet";
  }
}
