/**
 * PANE 3 footer — the reply composer.
 *
 * Reply / Private note tabs, a lightweight formatting toolbar with undo-redo,
 * canned responses triggered by a leading `/`, emoji, file attachments (click,
 * drag & drop or paste), real voice recording via `MediaRecorder` and the
 * agent's signature.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import {
  Bold,
  Code,
  Italic,
  Link2,
  List,
  ListOrdered,
  Mic,
  Paperclip,
  PenLine,
  Redo2,
  Send,
  Smile,
  Square,
  Undo2,
  X,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { conversations as conversationsApi } from "@/lib/api";
import { formatDuration, truncate } from "@/lib/format";
import type { CannedResponse, Message } from "@/lib/types";
import { useAppData } from "@/store/app";
import { useAuth } from "@/store/auth";
import { Button, Dropdown, IconButton, Tooltip, useToast } from "@/components/ui";
import { PendingAttachment } from "./Attachments";
import { CannedResponsePicker } from "./CannedResponsePicker";
import { EmojiPicker } from "./EmojiPicker";

const PLACEHOLDER =
  "Shift + enter for new line. Start with '/' to select a Canned Response.";

/** Preferred recording formats, best first — the API treats ogg as a voice note. */
const AUDIO_FORMATS = [
  { mime: "audio/ogg;codecs=opus", extension: "ogg" },
  { mime: "audio/ogg", extension: "ogg" },
  { mime: "audio/webm;codecs=opus", extension: "webm" },
  { mime: "audio/webm", extension: "webm" },
];

export interface ComposerProps {
  conversationId: number;
  replyTo: Message | null;
  onClearReply: () => void;
  onSent: () => void;
  /**
   * Filled with a callback that appends text to the draft, so the sidebar's
   * macro list can insert a canned response into this composer.
   */
  insertRef?: React.MutableRefObject<((text: string) => void) | null>;
}

export function Composer({
  conversationId,
  replyTo,
  onClearReply,
  onSent,
  insertRef,
}: ComposerProps) {
  const { canned } = useAppData();
  const { user } = useAuth();
  const toast = useToast();

  const [isNote, setIsNote] = useState(false);
  const [value, setValue] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordedSeconds, setRecordedSeconds] = useState(0);

  const textarea = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const undoStack = useRef<string[]>([]);
  const redoStack = useRef<string[]>([]);
  const typingSentAt = useRef(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const recordTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  /* -------------------------------------------------------------- drafts */

  const setText = useCallback((next: string, remember = true) => {
    setValue((current) => {
      if (remember && current !== next) {
        undoStack.current.push(current);
        if (undoStack.current.length > 50) undoStack.current.shift();
        redoStack.current = [];
      }
      return next;
    });
  }, []);

  function undo() {
    const previous = undoStack.current.pop();
    if (previous === undefined) return;
    redoStack.current.push(value);
    setValue(previous);
  }

  function redo() {
    const next = redoStack.current.pop();
    if (next === undefined) return;
    undoStack.current.push(value);
    setValue(next);
  }

  // Expose an "insert text" handle to the rest of the screen.
  useEffect(() => {
    if (!insertRef) return;
    insertRef.current = (text: string) => {
      setValue((current) => {
        undoStack.current.push(current);
        return current.trim() ? `${current.replace(/\s+$/, "")}\n${text}` : text;
      });
      textarea.current?.focus();
    };
    return () => {
      insertRef.current = null;
    };
  }, [insertRef]);

  // Reset per conversation.
  useEffect(() => {
    setValue("");
    setFiles([]);
    setIsNote(false);
    undoStack.current = [];
    redoStack.current = [];
  }, [conversationId]);

  /* --------------------------------------------------------- canned menu */

  const cannedQuery = useMemo(() => {
    const match = /^\/(\S*)$/.exec(value);
    return match ? match[1]! : null;
  }, [value]);

  const insertCanned = useCallback(
    (item: CannedResponse) => {
      setText(item.content);
      textarea.current?.focus();
    },
    [setText],
  );

  /* ------------------------------------------------------------ toolbar */

  function surround(before: string, after = before) {
    const node = textarea.current;
    if (!node) return;
    const { selectionStart: start, selectionEnd: end } = node;
    const selected = value.slice(start, end) || "text";
    const next = `${value.slice(0, start)}${before}${selected}${after}${value.slice(end)}`;
    setText(next);
    requestAnimationFrame(() => {
      node.focus();
      node.setSelectionRange(start + before.length, start + before.length + selected.length);
    });
  }

  function prefixLines(prefix: (index: number) => string) {
    const node = textarea.current;
    if (!node) return;
    const { selectionStart: start, selectionEnd: end } = node;
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const block = value.slice(lineStart, end) || "";
    const updated = block
      .split("\n")
      .map((line, index) => `${prefix(index)}${line}`)
      .join("\n");
    setText(`${value.slice(0, lineStart)}${updated}${value.slice(end)}`);
    requestAnimationFrame(() => node.focus());
  }

  function insertLink() {
    const url = window.prompt("Link URL", "https://");
    if (!url) return;
    const node = textarea.current;
    const start = node?.selectionStart ?? value.length;
    const end = node?.selectionEnd ?? value.length;
    const text = value.slice(start, end) || url;
    setText(`${value.slice(0, start)}${text} (${url})${value.slice(end)}`);
  }

  function insertSignature() {
    const signature = user?.signature?.trim();
    if (!signature) {
      toast.toast({
        title: "No signature configured",
        description: "Add one from your profile settings.",
        tone: "warning",
      });
      return;
    }
    setText(value ? `${value.replace(/\s+$/, "")}\n\n${signature}` : signature);
    textarea.current?.focus();
  }

  function insertEmoji(emoji: string) {
    const node = textarea.current;
    const start = node?.selectionStart ?? value.length;
    setText(`${value.slice(0, start)}${emoji}${value.slice(start)}`);
    requestAnimationFrame(() => {
      node?.focus();
      node?.setSelectionRange(start + emoji.length, start + emoji.length);
    });
  }

  /* ---------------------------------------------------------- attachments */

  const addFiles = useCallback((incoming: FileList | File[] | null) => {
    if (!incoming) return;
    const list = Array.from(incoming).filter(Boolean);
    if (list.length) setFiles((current) => [...current, ...list]);
  }, []);

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer?.files ?? null);
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = Array.from(event.clipboardData?.files ?? []);
    if (pasted.length) {
      event.preventDefault();
      addFiles(pasted);
    }
  }

  /* -------------------------------------------------------------- typing */

  function notifyTyping() {
    const now = Date.now();
    if (now - typingSentAt.current < 4000) return;
    typingSentAt.current = now;
    void conversationsApi.typing(conversationId).catch(() => undefined);
  }

  /* ------------------------------------------------------------ recording */

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      toast.error("Recording unavailable", "This browser does not support microphone capture.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const format =
        AUDIO_FORMATS.find((candidate) => MediaRecorder.isTypeSupported(candidate.mime)) ??
        AUDIO_FORMATS[AUDIO_FORMATS.length - 1]!;
      const instance = new MediaRecorder(stream, { mimeType: format.mime });
      chunks.current = [];
      instance.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      instance.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks.current, { type: format.mime.split(";")[0] });
        if (blob.size > 0) {
          const file = new File([blob], `voice-message.${format.extension}`, {
            type: format.mime.split(";")[0],
          });
          void send({ voice: file });
        }
      };
      instance.start();
      recorder.current = instance;
      setRecording(true);
      setRecordedSeconds(0);
      recordTimer.current = setInterval(
        () => setRecordedSeconds((seconds) => seconds + 1),
        1000,
      );
    } catch (error) {
      toast.error("Microphone blocked", (error as Error).message);
    }
  }

  function stopRecording(discard = false) {
    const instance = recorder.current;
    if (recordTimer.current) clearInterval(recordTimer.current);
    recordTimer.current = null;
    setRecording(false);
    if (!instance) return;
    if (discard) instance.onstop = () => instance.stream.getTracks().forEach((t) => t.stop());
    instance.stop();
    recorder.current = null;
  }

  useEffect(
    () => () => {
      if (recordTimer.current) clearInterval(recordTimer.current);
      recorder.current?.stream.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  /* --------------------------------------------------------------- send */

  const send = useCallback(
    async ({ voice }: { voice?: File } = {}) => {
      const content = value.trim();
      const payloadFiles = voice ? [voice] : files;
      if (!content && payloadFiles.length === 0) return;

      setSending(true);
      try {
        await conversationsApi.send(conversationId, {
          content: voice ? undefined : content,
          private: isNote,
          reply_to_message_id: replyTo?.id ?? null,
          is_voice: Boolean(voice),
          files: payloadFiles,
        });
        if (!voice) {
          setValue("");
          setFiles([]);
          undoStack.current = [];
          redoStack.current = [];
        }
        onClearReply();
        onSent();
      } catch (error) {
        toast.error("Message not sent", (error as Error).message);
      } finally {
        setSending(false);
      }
    },
    [conversationId, files, isNote, onClearReply, onSent, replyTo, toast, value],
  );

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (cannedQuery !== null && ["ArrowUp", "ArrowDown", "Enter", "Tab"].includes(event.key)) {
      // The canned response picker owns these keys while it is open.
      return;
    }
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b") {
      event.preventDefault();
      surround("*");
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "i") {
      event.preventDefault();
      surround("_");
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
    }
  }

  const canSend = Boolean(value.trim() || files.length) && !sending;

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "relative border-t border-line px-4 pb-3 pt-2 transition-colors",
        isNote
          ? "border-amber-200 bg-note/60 dark:border-amber-800 dark:bg-amber-900/20"
          : "bg-white dark:border-slate-800 dark:bg-slate-900",
      )}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-2 z-20 flex items-center justify-center rounded-xl border-2 border-dashed border-primary bg-primary-50/80 text-sm font-medium text-primary dark:bg-primary-900/40">
          Drop files to attach
        </div>
      )}

      {/* Reply / note tabs */}
      <div className="flex items-center gap-1 pb-1.5">
        {[
          { key: false, label: "Reply" },
          { key: true, label: "Private Note" },
        ].map((tab) => (
          <button
            key={String(tab.key)}
            type="button"
            onClick={() => setIsNote(tab.key)}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              isNote === tab.key
                ? tab.key
                  ? "bg-amber-200 text-amber-900 dark:bg-amber-700 dark:text-amber-50"
                  : "bg-primary-50 text-primary dark:bg-primary-900/40 dark:text-primary-200"
                : "text-ink-muted hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800",
            )}
          >
            {tab.label}
          </button>
        ))}
        {isNote && (
          <span className="ml-1 text-2xs text-amber-700 dark:text-amber-300">
            Only your team can see private notes.
          </span>
        )}
      </div>

      {/* Reply target */}
      {replyTo && (
        <div className="mb-1.5 flex items-center gap-2 rounded-lg border-l-2 border-primary bg-surface-muted px-2 py-1 dark:bg-slate-800">
          <div className="min-w-0 flex-1">
            <p className="text-2xs font-medium text-primary">Replying to</p>
            <p className="truncate text-xs text-ink-muted dark:text-slate-400">
              {truncate(replyTo.content ?? "Attachment", 120)}
            </p>
          </div>
          <IconButton label="Cancel reply" onClick={onClearReply} className="h-6 w-6">
            <X className="h-3.5 w-3.5" />
          </IconButton>
        </div>
      )}

      <div
        className={cn(
          "relative rounded-xl border bg-white shadow-card focus-within:border-primary-300 dark:bg-slate-900",
          isNote
            ? "border-amber-300 bg-note dark:border-amber-700 dark:bg-amber-900/30"
            : "border-line dark:border-slate-700",
        )}
      >
        {/* Formatting toolbar */}
        <div className="flex flex-wrap items-center gap-0.5 border-b border-line px-1.5 py-1 dark:border-slate-800">
          <ToolbarButton label="Bold" onClick={() => surround("*")}>
            <Bold className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton label="Italic" onClick={() => surround("_")}>
            <Italic className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton label="Insert link" onClick={insertLink}>
            <Link2 className="h-3.5 w-3.5" />
          </ToolbarButton>
          <span className="mx-1 h-4 w-px bg-line dark:bg-slate-700" />
          <ToolbarButton label="Undo" onClick={undo}>
            <Undo2 className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton label="Redo" onClick={redo}>
            <Redo2 className="h-3.5 w-3.5" />
          </ToolbarButton>
          <span className="mx-1 h-4 w-px bg-line dark:bg-slate-700" />
          <ToolbarButton label="Bullet list" onClick={() => prefixLines(() => "• ")}>
            <List className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            label="Numbered list"
            onClick={() => prefixLines((index) => `${index + 1}. `)}
          >
            <ListOrdered className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton label="Code" onClick={() => surround("`")}>
            <Code className="h-3.5 w-3.5" />
          </ToolbarButton>
        </div>

        {/* Text area */}
        <textarea
          ref={textarea}
          value={value}
          rows={3}
          placeholder={PLACEHOLDER}
          onChange={(event) => {
            setText(event.target.value);
            notifyTyping();
          }}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          className={cn(
            "max-h-56 min-h-[76px] w-full resize-none bg-transparent px-3 py-2 text-sm leading-relaxed text-ink outline-none placeholder:text-ink-faint",
            "dark:text-slate-100",
          )}
        />

        {/* Staged attachments */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pb-2">
            {files.map((file, index) => (
              <PendingAttachment
                key={`${file.name}-${index}`}
                file={file}
                onRemove={() =>
                  setFiles((current) => current.filter((_, position) => position !== index))
                }
              />
            ))}
          </div>
        )}

        {/* Action bar */}
        <div className="flex items-center gap-1 border-t border-line px-2 py-1.5 dark:border-slate-800">
          <Dropdown
            above
            width="w-auto"
            panelClassName="p-0 border-0 shadow-none bg-transparent"
            trigger={({ toggle }) => (
              <ToolbarButton label="Emoji" onClick={toggle}>
                <Smile className="h-4 w-4" />
              </ToolbarButton>
            )}
          >
            {({ close }) => (
              <EmojiPicker
                onSelect={(emoji) => {
                  insertEmoji(emoji);
                  close();
                }}
              />
            )}
          </Dropdown>

          <ToolbarButton label="Attach files" onClick={() => fileInput.current?.click()}>
            <Paperclip className="h-4 w-4" />
          </ToolbarButton>
          <input
            ref={fileInput}
            type="file"
            multiple
            hidden
            onChange={(event) => {
              addFiles(event.target.files);
              event.target.value = "";
            }}
          />

          {recording ? (
            <div className="flex items-center gap-1.5 rounded-lg bg-red-50 px-2 py-1 dark:bg-red-900/30">
              <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
              <span className="text-2xs tabular-nums text-red-700 dark:text-red-300">
                {formatDuration(recordedSeconds)}
              </span>
              <Tooltip label="Send recording">
                <button
                  type="button"
                  onClick={() => stopRecording(false)}
                  aria-label="Send recording"
                  className="rounded p-0.5 text-red-700 hover:text-red-900 dark:text-red-300"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              </Tooltip>
              <Tooltip label="Discard">
                <button
                  type="button"
                  onClick={() => stopRecording(true)}
                  aria-label="Discard recording"
                  className="rounded p-0.5 text-red-700 hover:text-red-900 dark:text-red-300"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </Tooltip>
            </div>
          ) : (
            <ToolbarButton label="Record a voice message" onClick={() => void startRecording()}>
              <Mic className="h-4 w-4" />
            </ToolbarButton>
          )}

          <ToolbarButton label="Insert signature" onClick={insertSignature}>
            <PenLine className="h-4 w-4" />
          </ToolbarButton>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-2xs text-ink-faint sm:block">
              {isNote ? "Note" : "Reply"} · Enter to send
            </span>
            <Button
              variant="primary"
              size="sm"
              loading={sending}
              disabled={!canSend}
              onClick={() => void send()}
              rightIcon={<Send className="h-3.5 w-3.5" />}
            >
              Send
            </Button>
          </div>
        </div>

        {cannedQuery !== null && (
          <CannedResponsePicker
            query={cannedQuery}
            items={canned}
            onSelect={insertCanned}
            onClose={() => setText(value.replace(/^\//, ""))}
          />
        )}
      </div>
    </div>
  );
}

function ToolbarButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip label={label}>
      <button
        type="button"
        aria-label={label}
        onClick={onClick}
        className="flex h-7 w-7 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-slate-100 hover:text-ink dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        {children}
      </button>
    </Tooltip>
  );
}

export default Composer;
