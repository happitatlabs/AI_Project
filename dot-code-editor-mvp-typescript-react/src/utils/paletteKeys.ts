import type { Palette, PaletteLimit, SpriteGrid } from "../types/sprite";

export const PALETTE_KEYS = "123456789abcdefghijklmnopqrstuvwxyz";

const DEFAULT_SLOT_COLORS = [
  "#111111",
  "#c58f63",
  "#8f5f3c",
  "#e88b8b",
  "#f6d365",
  "#5aa9e6",
  "#75c46b",
  "#7b5ce1",
  "#f27a54",
  "#4d908e",
  "#577590",
  "#f2cc8f",
  "#6d597a",
  "#b56576",
  "#355070",
  "#2a9d8f",
  "#f72585",
  "#7209b7",
  "#3a0ca3",
  "#4361ee",
  "#4cc9f0",
  "#80ed99",
  "#ffd166",
  "#ef476f",
  "#06d6a0",
  "#118ab2",
  "#073b4c",
  "#ff9f1c",
  "#cbf3f0",
  "#ffbf69",
  "#6a4c93",
  "#1982c4",
];

export function getPaletteColorKeys(limit: PaletteLimit): string[] {
  return Array.from(PALETTE_KEYS.slice(0, limit));
}

export function normalizePaletteForLimit(palette: Palette, limit: PaletteLimit): Palette {
  const nextPalette: Palette = { "0": "transparent" };

  getPaletteColorKeys(limit).forEach((key, index) => {
    nextPalette[key] = isHexColor(palette[key]) ? palette[key] : DEFAULT_SLOT_COLORS[index];
  });

  return nextPalette;
}

export function clampGridToPaletteLimit(grid: SpriteGrid, limit: PaletteLimit): SpriteGrid {
  const allowedKeys = new Set(["0", ...getPaletteColorKeys(limit)]);
  const fallbackKey = getPaletteColorKeys(limit).at(-1) ?? "0";

  return grid.map((row) =>
    Array.from(row)
      .map((key) => (allowedKeys.has(key) ? key : fallbackKey))
      .join(""),
  );
}

export function isHexColor(value: string | undefined): value is string {
  return /^#[0-9a-fA-F]{6}$/.test(value ?? "");
}
