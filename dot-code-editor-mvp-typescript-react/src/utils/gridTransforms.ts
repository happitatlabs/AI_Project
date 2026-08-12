import type { ColorKey, ShiftDirection, SpriteGrid } from "../types/sprite";

export function createBlankGrid(size: number, fill: ColorKey = "0"): SpriteGrid {
  return Array.from({ length: size }, () => fill.repeat(size));
}

export function setGridCell(
  grid: SpriteGrid,
  rowIndex: number,
  columnIndex: number,
  value: ColorKey,
): SpriteGrid {
  return grid.map((row, currentRow) => {
    if (currentRow !== rowIndex) {
      return row;
    }

    return `${row.slice(0, columnIndex)}${value}${row.slice(columnIndex + 1)}`;
  });
}

export function flipGridHorizontal(grid: SpriteGrid): SpriteGrid {
  return grid.map((row) => Array.from(row).reverse().join(""));
}

export function flipGridVertical(grid: SpriteGrid): SpriteGrid {
  return [...grid].reverse();
}

export function shiftGrid(grid: SpriteGrid, direction: ShiftDirection): SpriteGrid {
  const size = grid.length;
  const next = createBlankGrid(size);

  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) {
      const sourceRow = getSourceRow(row, direction);
      const sourceColumn = getSourceColumn(column, direction);

      if (sourceRow >= 0 && sourceRow < size && sourceColumn >= 0 && sourceColumn < size) {
        next[row] =
          next[row].slice(0, column) +
          grid[sourceRow][sourceColumn] +
          next[row].slice(column + 1);
      }
    }
  }

  return next;
}

function getSourceRow(row: number, direction: ShiftDirection): number {
  if (direction === "up") {
    return row + 1;
  }

  if (direction === "down") {
    return row - 1;
  }

  return row;
}

function getSourceColumn(column: number, direction: ShiftDirection): number {
  if (direction === "left") {
    return column + 1;
  }

  if (direction === "right") {
    return column - 1;
  }

  return column;
}
