import { describe, it, expect } from 'vitest'
import { encodedToCanonical, canonicalToEncoded, canonicalToNormalized, normalizedToCanonical, canvasToCanonical, canonicalToCanvas } from './geometry'

describe('geometry', () => {
  it('rotation roundtrip', () => {
    const w=1920,h=1080
    const points = [{x:100,y:100},{x:0,y:0},{x:1919,y:1079}]
    for (const rot of [0,90,180,270]) {
      for (const pt of points) {
        const { point: canon } = encodedToCanonical(pt, rot, w, h)
        const back = canonicalToEncoded(canon, rot, w, h)
        expect(Math.abs(back.x-pt.x)).toBeLessThan(1e-5)
        expect(Math.abs(back.y-pt.y)).toBeLessThan(1e-5)
      }
    }
  })

  it('normalized roundtrip', () => {
    const pt = {x:960,y:540}
    const npt = canonicalToNormalized(pt, 1920,1080)
    const back = normalizedToCanonical(npt, 1920,1080)
    expect(Math.abs(back.x-pt.x)).toBeLessThan(1e-5)
  })

  it('canvas roundtrip', () => {
    const canvasW=800,canvasH=600,videoW=1920,videoH=1080
    const canon = {x:960,y:540}
    const canvasPt = canonicalToCanvas(canon, canvasW, canvasH, videoW, videoH)
    const back = canvasToCanonical(canvasPt, canvasW, canvasH, videoW, videoH)
    expect(Math.abs(back.x-canon.x)).toBeLessThan(0.01)
  })
})
