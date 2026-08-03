import type { Palette, SpriteGrid } from "../types/sprite";

export function generateSpriteCode(spriteGrid: SpriteGrid): string {
  const rows = spriteGrid.map((row) => `  ${JSON.stringify(row)}`).join(",\n");
  return `export const sprite = [\n${rows},\n];`;
}

export function generatePaletteCode(palette: Palette): string {
  const rows = Object.entries(palette)
    .map(([key, value]) => `  ${JSON.stringify(key)}: ${JSON.stringify(value)}`)
    .join(",\n");

  return `export const palette = {\n${rows},\n};`;
}

export function generateTypeScriptCode(spriteGrid: SpriteGrid, palette: Palette): string {
  return `${generatePaletteCode(palette)}

${generateSpriteCode(spriteGrid)}

import { createElement } from "react";
import type { CSSProperties } from "react";

export type PixelSpriteProps = {
  sprite: string[];
  palette: Record<string, string>;
  pixelSize?: number;
  className?: string;
};

export function PixelSprite({
  sprite,
  palette,
  pixelSize = 12,
  className,
}: PixelSpriteProps) {
  const columns = sprite[0]?.length ?? 0;
  const containerStyle: CSSProperties = {
    display: "inline-grid",
    gridTemplateColumns: \`repeat(\${columns}, \${pixelSize}px)\`,
    gridAutoRows: \`\${pixelSize}px\`,
    imageRendering: "pixelated",
    lineHeight: 0,
  };

  return createElement(
    "div",
    { className, style: containerStyle, role: "img", "aria-label": "Pixel sprite" },
    sprite.flatMap((row, y) =>
      Array.from(row).map((key, x) => {
        const color = palette[key] ?? "transparent";
        const pixelStyle: CSSProperties = {
          width: pixelSize,
          height: pixelSize,
          display: "block",
          backgroundColor: color === "transparent" ? undefined : color,
        };

        return createElement("span", {
          key: \`\${y}-\${x}\`,
          style: pixelStyle,
        });
      }),
    ),
  );
}
`;
}
