/**
 * Time contract utilities
 */

export interface FrameEntry {
  frame_index: number
  pts_us: number
  original_pts?: number
  time_base?: string
  keyframe?: boolean
}

export function computeDtSec(currPtsUs: number, prevPtsUs: number): number {
  return (currPtsUs - prevPtsUs) / 1e6
}

export function mapPreviewTimeToSourceFrame(previewTimeUs: number, sourceFrames: FrameEntry[]): number {
  // Binary search for nearest pts
  let left = 0
  let right = sourceFrames.length - 1
  let best = 0
  let bestDiff = Infinity
  while (left <= right) {
    const mid = Math.floor((left + right) / 2)
    const diff = Math.abs(sourceFrames[mid].pts_us - previewTimeUs)
    if (diff < bestDiff) {
      bestDiff = diff
      best = mid
    }
    if (sourceFrames[mid].pts_us < previewTimeUs) left = mid + 1
    else right = mid - 1
  }
  return best
}

export function formatTimeUs(us: number): string {
  const sec = us / 1e6
  const m = Math.floor(sec / 60)
  const s = (sec % 60).toFixed(3)
  return `${m}:${s.padStart(6,'0')}`
}
