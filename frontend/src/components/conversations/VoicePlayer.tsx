/**
 * Voice / audio message player: play-pause button, a seekable waveform and the
 * elapsed-of-total duration.
 *
 * The waveform is deterministic noise derived from the attachment id — real
 * peak data is not part of the payload, and a stable shape reads better than a
 * flat bar.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import type { Attachment } from "@/lib/types";

const BARS = 42;

function waveform(seed: number): number[] {
  const values: number[] = [];
  let state = seed || 1;
  for (let i = 0; i < BARS; i += 1) {
    state = (state * 1103515245 + 12345) % 2147483648;
    values.push(0.25 + (state / 2147483648) * 0.75);
  }
  return values;
}

export interface VoicePlayerProps {
  attachment: Attachment;
  outgoing?: boolean;
}

export function VoicePlayer({ attachment, outgoing = false }: VoicePlayerProps) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(
    Number(attachment.meta?.duration ?? attachment.meta?.duration_seconds ?? 0) || 0,
  );

  const bars = useMemo(() => waveform(attachment.id), [attachment.id]);
  const progress = duration > 0 ? Math.min(1, current / duration) : 0;

  useEffect(() => {
    const element = audio.current;
    if (!element) return;
    const onTime = () => setCurrent(element.currentTime);
    const onMeta = () => {
      if (Number.isFinite(element.duration)) setDuration(element.duration);
    };
    const onEnd = () => {
      setPlaying(false);
      setCurrent(0);
    };
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("loadedmetadata", onMeta);
    element.addEventListener("ended", onEnd);
    return () => {
      element.removeEventListener("timeupdate", onTime);
      element.removeEventListener("loadedmetadata", onMeta);
      element.removeEventListener("ended", onEnd);
    };
  }, []);

  function toggle() {
    const element = audio.current;
    if (!element) return;
    if (element.paused) {
      void element.play();
      setPlaying(true);
    } else {
      element.pause();
      setPlaying(false);
    }
  }

  function seek(event: React.MouseEvent<HTMLDivElement>) {
    const element = audio.current;
    if (!element || !duration) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    element.currentTime = ratio * duration;
    setCurrent(element.currentTime);
  }

  return (
    <div
      className={cn(
        "flex w-[260px] items-center gap-2.5 rounded-lg border p-2",
        outgoing
          ? "border-primary-200 bg-white/70 dark:border-slate-700 dark:bg-slate-800/70"
          : "border-line bg-surface-muted dark:border-slate-700 dark:bg-slate-800",
      )}
    >
      <audio ref={audio} src={attachment.url ?? undefined} preload="metadata" />
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? "Pause voice message" : "Play voice message"}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-white transition hover:bg-primary-600"
      >
        {playing ? (
          <Pause className="h-3.5 w-3.5 fill-current" />
        ) : (
          <Play className="ml-0.5 h-3.5 w-3.5 fill-current" />
        )}
      </button>

      <div
        role="slider"
        aria-label="Seek"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(current)}
        tabIndex={0}
        onClick={seek}
        className="flex h-8 min-w-0 flex-1 cursor-pointer items-center gap-[2px]"
      >
        {bars.map((height, index) => (
          <span
            key={index}
            className={cn(
              "flex-1 rounded-full transition-colors",
              index / BARS <= progress
                ? "bg-primary"
                : "bg-slate-300 dark:bg-slate-600",
            )}
            style={{ height: `${Math.round(height * 22)}px` }}
          />
        ))}
      </div>

      <span className="shrink-0 text-2xs tabular-nums text-ink-muted dark:text-slate-400">
        {formatDuration(playing || current ? current : duration)}
      </span>
    </div>
  );
}

export default VoicePlayer;
