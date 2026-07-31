/**
 * Attachment rendering inside a message bubble: image grids with a lightbox,
 * video players, file cards, location cards and stickers.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  MapPin,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { formatBytes } from "@/lib/format";
import type { Attachment } from "@/lib/types";
import { IconButton } from "@/components/ui";
import { VoicePlayer } from "./VoicePlayer";

/* ------------------------------------------------------------- lightbox */

export interface LightboxProps {
  items: Attachment[];
  index: number;
  onClose: () => void;
  onIndexChange: (index: number) => void;
}

export function Lightbox({ items, index, onClose, onIndexChange }: LightboxProps) {
  const current = items[index];

  const step = useCallback(
    (delta: number) => {
      if (!items.length) return;
      onIndexChange((index + delta + items.length) % items.length);
    },
    [index, items.length, onIndexChange],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight") step(1);
      if (event.key === "ArrowLeft") step(-1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, step]);

  if (!current) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex animate-fade-in items-center justify-center bg-black/85 p-6"
      onClick={onClose}
    >
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
      >
        <X className="h-5 w-5" />
      </button>

      {items.length > 1 && (
        <>
          <button
            type="button"
            aria-label="Previous"
            onClick={(event) => {
              event.stopPropagation();
              step(-1);
            }}
            className="absolute left-4 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
          <button
            type="button"
            aria-label="Next"
            onClick={(event) => {
              event.stopPropagation();
              step(1);
            }}
            className="absolute right-4 top-1/2 rounded-full bg-white/10 p-2 text-white transition hover:bg-white/20"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        </>
      )}

      <figure
        className="flex max-h-full max-w-full flex-col items-center gap-3"
        onClick={(event) => event.stopPropagation()}
      >
        <img
          src={current.url ?? ""}
          alt={current.file_name ?? "Attachment"}
          className="max-h-[80vh] max-w-full rounded-lg object-contain"
        />
        <figcaption className="flex items-center gap-3 text-xs text-white/80">
          <span className="truncate">{current.file_name}</span>
          {current.url && (
            <a
              href={current.url}
              download={current.file_name ?? undefined}
              className="inline-flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 transition hover:bg-white/20"
            >
              <Download className="h-3.5 w-3.5" /> Download
            </a>
          )}
        </figcaption>
      </figure>
    </div>,
    document.body,
  );
}

/* ---------------------------------------------------------------- pieces */

function FileCard({ attachment, outgoing }: { attachment: Attachment; outgoing: boolean }) {
  return (
    <a
      href={attachment.url ?? "#"}
      target="_blank"
      rel="noopener noreferrer"
      download={attachment.file_name ?? undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-lg border p-2 transition-colors",
        outgoing
          ? "border-primary-200 bg-white/70 hover:bg-white dark:border-slate-700 dark:bg-slate-800/70"
          : "border-line bg-surface-muted hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800",
      )}
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary dark:bg-primary-900/40">
        <FileText className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-ink dark:text-slate-100">
          {attachment.file_name ?? "Attachment"}
        </span>
        <span className="block text-2xs text-ink-muted dark:text-slate-400">
          {[formatBytes(attachment.file_size), attachment.mime_type]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
      <Download className="h-4 w-4 shrink-0 text-ink-faint" />
    </a>
  );
}

function VideoPlayer({ attachment }: { attachment: Attachment }) {
  const round = attachment.file_type === "video_note";
  return (
    <video
      controls
      preload="metadata"
      poster={attachment.thumb_url ?? undefined}
      src={attachment.url ?? undefined}
      className={cn(
        "max-h-[320px] w-full max-w-[320px] bg-black object-cover",
        round ? "aspect-square rounded-full" : "rounded-lg",
      )}
    />
  );
}

function LocationCard({ attachment }: { attachment: Attachment }) {
  const lat = Number(attachment.meta?.latitude ?? attachment.meta?.lat);
  const lng = Number(attachment.meta?.longitude ?? attachment.meta?.lng);
  const valid = Number.isFinite(lat) && Number.isFinite(lng);
  const href = valid
    ? `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`
    : undefined;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex w-[240px] items-center gap-2.5 rounded-lg border border-line bg-surface-muted p-2.5 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-500 dark:bg-red-900/30">
        <MapPin className="h-4 w-4" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink dark:text-slate-100">
          {(attachment.meta?.title as string) ?? "Shared location"}
        </span>
        <span className="block truncate text-2xs text-ink-muted dark:text-slate-400">
          {valid ? `${lat.toFixed(5)}, ${lng.toFixed(5)}` : "Coordinates unavailable"}
        </span>
      </span>
    </a>
  );
}

/* ------------------------------------------------------------ collection */

export interface AttachmentsProps {
  attachments: Attachment[];
  outgoing?: boolean;
}

export function Attachments({ attachments, outgoing = false }: AttachmentsProps) {
  const [lightbox, setLightbox] = useState<number | null>(null);

  const images = useMemo(
    () => attachments.filter((item) => item.file_type === "image" || item.file_type === "animation"),
    [attachments],
  );
  const others = attachments.filter(
    (item) => item.file_type !== "image" && item.file_type !== "animation",
  );

  if (!attachments.length) return null;

  return (
    <div className="space-y-2">
      {images.length > 0 && (
        <div
          className={cn(
            "grid gap-1.5",
            images.length === 1 ? "grid-cols-1" : "grid-cols-2",
            "max-w-[320px]",
          )}
        >
          {images.map((attachment, index) => (
            <button
              key={attachment.id}
              type="button"
              onClick={() => setLightbox(index)}
              className="group relative overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800"
            >
              <img
                src={attachment.thumb_url ?? attachment.url ?? ""}
                alt={attachment.file_name ?? "Image"}
                loading="lazy"
                className={cn(
                  "w-full object-cover transition-transform group-hover:scale-[1.02]",
                  images.length === 1 ? "max-h-[280px]" : "h-[130px]",
                )}
              />
              {attachment.file_type === "animation" && (
                <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1 text-2xs font-semibold text-white">
                  GIF
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {others.map((attachment) => {
        switch (attachment.file_type) {
          case "voice":
          case "audio":
            return (
              <VoicePlayer
                key={attachment.id}
                attachment={attachment}
                outgoing={outgoing}
              />
            );
          case "video":
          case "video_note":
            return <VideoPlayer key={attachment.id} attachment={attachment} />;
          case "location":
            return <LocationCard key={attachment.id} attachment={attachment} />;
          default:
            return (
              <FileCard key={attachment.id} attachment={attachment} outgoing={outgoing} />
            );
        }
      })}

      {lightbox !== null && (
        <Lightbox
          items={images}
          index={lightbox}
          onIndexChange={setLightbox}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}

/** Sticker attachments render bare — no bubble, no border. */
export function StickerAttachment({ attachment }: { attachment: Attachment }) {
  return (
    <img
      src={attachment.url ?? attachment.thumb_url ?? ""}
      alt={(attachment.meta?.emoji as string) ?? "Sticker"}
      className="h-[140px] w-[140px] object-contain"
    />
  );
}

/** Compact preview strip for files staged in the composer. */
export function PendingAttachment({
  file,
  onRemove,
}: {
  file: File;
  onRemove: () => void;
}) {
  const isImage = file.type.startsWith("image/");
  const url = useMemo(() => (isImage ? URL.createObjectURL(file) : null), [file, isImage]);

  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);

  return (
    <div className="relative flex items-center gap-2 rounded-lg border border-line bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-800">
      {url ? (
        <img src={url} alt="" className="h-8 w-8 rounded object-cover" />
      ) : (
        <FileText className="h-4 w-4 text-ink-faint" />
      )}
      <span className="max-w-[140px] truncate text-xs text-ink-soft dark:text-slate-300">
        {file.name}
      </span>
      <span className="text-2xs text-ink-faint">{formatBytes(file.size)}</span>
      <IconButton label="Remove attachment" onClick={onRemove} className="h-5 w-5">
        <X className="h-3 w-3" />
      </IconButton>
    </div>
  );
}

export default Attachments;
