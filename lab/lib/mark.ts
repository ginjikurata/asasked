// The AsAsked mark on a 6×4 grid: a cart's path in ink, ending in one red pixel.
// Used by the header, the favicon (app/icon.svg), the Apple icon and the share image.
export const MARK_PATH = [
  [0, 0], [0, 1], [0, 2], [1, 2], [2, 2], [3, 2], [3, 1], [4, 1],
] as const;
export const MARK_END = [5, 0] as const;
