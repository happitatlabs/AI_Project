import { useMemo, useState } from "react";
import type { Palette, SpriteGrid } from "../types/sprite";
import { generatePaletteCode, generateSpriteCode, generateTypeScriptCode } from "../utils/spriteExport";

type CodeExportPanelProps = {
  spriteGrid: SpriteGrid;
  palette: Palette;
};

type CopyState = "idle" | "copied" | "failed";

export function CodeExportPanel({ spriteGrid, palette }: CodeExportPanelProps) {
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const tsCode = useMemo(() => generateTypeScriptCode(spriteGrid, palette), [spriteGrid, palette]);
  const spriteCode = useMemo(() => generateSpriteCode(spriteGrid), [spriteGrid]);
  const paletteCode = useMemo(() => generatePaletteCode(palette), [palette]);

  async function copyText(text: string) {
    try {
      await writeClipboardText(text);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }

    window.setTimeout(() => setCopyState("idle"), 1400);
  }

  function downloadTsFile() {
    const blob = new Blob([tsCode], { type: "text/typescript;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pixel-sprite.ts";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="panelSection codeSection" aria-labelledby="code-title">
      <div className="sectionHeader">
        <h2 id="code-title">Export</h2>
        <span className="sectionMeta">{spriteGrid.length} rows</span>
      </div>

      <textarea className="codeOutput" value={tsCode} readOnly spellCheck={false} />

      <div className="exportActions">
        <button type="button" onClick={() => copyText(tsCode)}>
          Copy TS Code
        </button>
        <button type="button" onClick={() => copyText(spriteCode)}>
          Copy Sprite Only
        </button>
        <button type="button" onClick={() => copyText(paletteCode)}>
          Copy Palette Only
        </button>
        <button type="button" onClick={downloadTsFile}>
          Download .ts
        </button>
      </div>

      <p className={`copyStatus ${copyState}`}>{getCopyMessage(copyState)}</p>
    </section>
  );
}

async function writeClipboardText(text: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      copyTextWithFallback(text);
      return;
    }
  }

  copyTextWithFallback(text);
}

function copyTextWithFallback(text: string) {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  textArea.style.top = "0";
  document.body.appendChild(textArea);
  textArea.select();

  const copied = document.execCommand("copy");
  document.body.removeChild(textArea);

  if (!copied) {
    throw new Error("Copy command failed.");
  }
}

function getCopyMessage(copyState: CopyState): string {
  if (copyState === "copied") {
    return "Copied.";
  }

  if (copyState === "failed") {
    return "Clipboard permission denied.";
  }

  return "Ready to export.";
}
