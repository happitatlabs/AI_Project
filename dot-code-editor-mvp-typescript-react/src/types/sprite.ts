export type GridSize = 16 | 24 | 32 | 48 | 64;

export type PaletteLimit = 4 | 8 | 16 | 32;

export type ColorKey = string;

export type Palette = Record<ColorKey, string>;

export type SpriteGrid = string[];

export type ToolMode = "paint" | "erase" | "eyedropper";

export type ShiftDirection = "up" | "down" | "left" | "right";

export type TransparencyMode = "alpha-only" | "none" | "corner-color" | "manual-color";

export type RgbColor = {
  r: number;
  g: number;
  b: number;
};

export type TransparencyOptions = {
  mode: TransparencyMode;
  tolerance: number;
  backgroundColor?: RgbColor | null;
};

export type SampledPixel = RgbColor | null;

export type PixelGridResult = {
  spriteGrid: SpriteGrid;
  palette: Palette;
};
