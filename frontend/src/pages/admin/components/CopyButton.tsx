/** Copy-to-clipboard control that flips to a check mark for a moment. */
import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/cn";
import { IconButton, Tooltip } from "@/components/ui";

export interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

/** Write `text` to the clipboard, falling back to a hidden textarea. */
export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    /* clipboard API unavailable (insecure origin) — fall through */
  }
  const node = document.createElement("textarea");
  node.value = text;
  node.setAttribute("readonly", "");
  node.style.position = "fixed";
  node.style.opacity = "0";
  document.body.appendChild(node);
  node.select();
  document.execCommand("copy");
  document.body.removeChild(node);
}

export function CopyButton({ value, label = "Copy", className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  async function onCopy() {
    await copyText(value);
    setCopied(true);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <Tooltip label={copied ? "Copied" : label}>
      <IconButton label={label} onClick={onCopy} className={cn(className)}>
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-600" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </IconButton>
    </Tooltip>
  );
}

export default CopyButton;
