/**
 * Centralized geometry utilities - mirrored from backend/app/core/geometry.py
 * All coordinate transforms tested for round-trip.
 */

export type Point = { x: number; y: number }

export function encodedToCanonical(pt: Point, rotation: number, srcW: number, srcH: number): { point: Point; size: { w: number; h: number } } {
  const r = ((rotation % 360) + 360) % 360
  if (r === 0) return { point: { x: pt.x, y: pt.y }, size: { w: srcW, h: srcH } }
  if (r === 90) return { point: { x: pt.y, y: srcW - pt.x }, size: { w: srcH, h: srcW } }
  if (r === 180) return { point: { x: srcW - pt.x, y: srcH - pt.y }, size: { w: srcW, h: srcH } }
  if (r === 270) return { point: { x: srcH - pt.y, y: pt.x }, size: { w: srcH, h: srcW } }
  throw new Error(`Unsupported rotation ${rotation}`)
}

export function canonicalToEncoded(pt: Point, rotation: number, srcW: number, srcH: number): Point {
  const r = ((rotation % 360) + 360) % 360
  if (r === 0) return { x: pt.x, y: pt.y }
  if (r === 90) return { x: srcW - pt.y, y: pt.x }
  if (r === 180) return { x: srcW - pt.x, y: srcH - pt.y }
  if (r === 270) return { x: pt.y, y: srcH - pt.x }
  throw new Error(`Unsupported rotation ${rotation}`)
}

export function canonicalToNormalized(pt: Point, canonW: number, canonH: number): Point {
  return { x: pt.x / canonW, y: pt.y / canonH }
}

export function normalizedToCanonical(npt: Point, canonW: number, canonH: number): Point {
  return { x: npt.x * canonW, y: npt.y * canonH }
}

export function canonicalToAnalysis(
  pt: Point,
  canonW: number,
  canonH: number,
  analysisW: number,
  analysisH: number,
  keepAspect = true
): { point: Point; meta: any } {
  if (!keepAspect) {
    const sx = analysisW / canonW
    const sy = analysisH / canonH
    return { point: { x: pt.x * sx, y: pt.y * sy }, meta: { scaleX: sx, scaleY: sy, offsetX: 0, offsetY: 0, letterboxed: false } }
  } else {
    const scale = Math.min(analysisW / canonW, analysisH / canonH)
    const displayedW = canonW * scale
    const displayedH = canonH * scale
    const offsetX = (analysisW - displayedW) / 2
    const offsetY = (analysisH - displayedH) / 2
    return {
      point: { x: pt.x * scale + offsetX, y: pt.y * scale + offsetY },
      meta: { scale, offsetX, offsetY, displayedW, displayedH, letterboxed: true }
    }
  }
}

export function analysisToCanonical(
  pt: Point,
  canonW: number,
  canonH: number,
  analysisW: number,
  analysisH: number,
  keepAspect = true,
  meta?: any
): Point {
  if (!keepAspect) {
    const sx = analysisW / canonW
    const sy = analysisH / canonH
    return { x: pt.x / sx, y: pt.y / sy }
  } else {
    const scale = meta?.scale ?? Math.min(analysisW / canonW, analysisH / canonH)
    const offsetX = meta?.offsetX ?? (analysisW - canonW * scale) / 2
    const offsetY = meta?.offsetY ?? (analysisH - canonH * scale) / 2
    return { x: (pt.x - offsetX) / scale, y: (pt.y - offsetY) / scale }
  }
}

export function canvasToCanonical(
  canvasPt: Point,
  canvasW: number,
  canvasH: number,
  videoCanonW: number,
  videoCanonH: number
): Point {
  const scale = Math.min(canvasW / videoCanonW, canvasH / videoCanonH)
  const displayedW = videoCanonW * scale
  const displayedH = videoCanonH * scale
  const offsetX = (canvasW - displayedW) / 2
  const offsetY = (canvasH - displayedH) / 2
  return { x: (canvasPt.x - offsetX) / scale, y: (canvasPt.y - offsetY) / scale }
}

export function canonicalToCanvas(
  canonPt: Point,
  canvasW: number,
  canvasH: number,
  videoCanonW: number,
  videoCanonH: number
): Point {
  const scale = Math.min(canvasW / videoCanonW, canvasH / videoCanonH)
  const displayedW = videoCanonW * scale
  const displayedH = videoCanonH * scale
  const offsetX = (canvasW - displayedW) / 2
  const offsetY = (canvasH - displayedH) / 2
  return { x: canonPt.x * scale + offsetX, y: canonPt.y * scale + offsetY }
}

export function transformPoint(pt: Point, matrix: number[][]): Point {
  const x = pt.x, y = pt.y
  const resX = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]
  const resY = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]
  const w = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
  if (Math.abs(w) < 1e-9) return { x: resX, y: resY }
  return { x: resX / w, y: resY / w }
}

// Test helpers
export function isInsideVideo(pt: Point, videoW: number, videoH: number): boolean {
  return pt.x >= 0 && pt.x <= videoW && pt.y >= 0 && pt.y <= videoH
}
