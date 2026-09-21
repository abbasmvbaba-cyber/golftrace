import { useParams } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useEffect, useRef, useState, useCallback } from 'react'
import { canvasToCanonical, canonicalToCanvas } from '../utils/geometry'
import { v4 as uuidv4 } from '../utils/uuid'

interface Annotation {
  frame_index: number
  x_norm?: number | null
  y_norm?: number | null
  visibility: 'visible' | 'not_visible' | 'out_of_frame'
}

export default function EditorPage() {
  const { projectId, videoId } = useParams()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [frameIndex, setFrameIndex] = useState(0)
  const [annotations, setAnnotations] = useState<Annotation[]>([])
  const [analysisInterval, setAnalysisInterval] = useState<{ start_frame: number; end_frame: number } | null>(null)
  const [track, setTrack] = useState<any[]>([])
  const [style, setStyle] = useState({
    color: '#FF0000',
    stroke_width_norm: 0.005,
    glow: false,
    opacity: 1.0,
    trail_duration_ms: 2000,
    fade: true,
    head_marker: 'circle',
    progressive_reveal: true,
    inferred_style: 'dashed',
    audio_preserve: true
  })

  const { data: video } = useQuery({
    queryKey: ['video', videoId],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}`)
      return res.data
    },
    refetchInterval: 3000
  })

  const { data: manifest } = useQuery({
    queryKey: ['manifest', videoId],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}/frame-manifest`)
      return res.data
    },
    enabled: video?.preparation_status === 'ready'
  })

  const { data: playback } = useQuery({
    queryKey: ['playback', videoId],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}/playback`)
      return res.data
    },
    enabled: video?.preparation_status === 'ready'
  })

  // Exact frame image
  const { data: exactFrameBlob } = useQuery({
    queryKey: ['exactFrame', videoId, frameIndex],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}/frames/${frameIndex}`, { responseType: 'blob' })
      return res.data as Blob
    },
    enabled: !!videoId && video?.preparation_status === 'ready'
  })

  // Draw canvas
  useEffect(() => {
    if (!canvasRef.current || !exactFrameBlob) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const img = new Image()
    img.onload = () => {
      canvas.width = img.width
      canvas.height = img.height
      ctx.clearRect(0,0,canvas.width,canvas.height)
      ctx.drawImage(img,0,0)
      // Draw annotations and track
      const currentAnn = annotations.find(a => a.frame_index === frameIndex)
      if (currentAnn && currentAnn.visibility === 'visible' && currentAnn.x_norm != null) {
        const x = currentAnn.x_norm * canvas.width
        const y = currentAnn.y_norm * canvas.height
        ctx.beginPath()
        ctx.arc(x,y,8,0,Math.PI*2)
        ctx.fillStyle = '#00FF00'
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 2
        ctx.stroke()
      }
      // Draw track points up to current frame
      const trail = track.filter((p:any) => p.frame_index <= frameIndex && p.x_norm != null && p.visibility === 'visible')
      if (trail.length > 1) {
        ctx.beginPath()
        ctx.strokeStyle = style.color
        ctx.lineWidth = style.stroke_width_norm * canvas.height
        ctx.globalAlpha = style.opacity
        for (let i=1;i<trail.length;i++) {
          const p0 = trail[i-1]
          const p1 = trail[i]
          const x0 = p0.x_norm * canvas.width
          const y0 = p0.y_norm * canvas.height
          const x1 = p1.x_norm * canvas.width
          const y1 = p1.y_norm * canvas.height
          if (p1.provenance !== 'detected' && p1.provenance !== 'manual' && style.inferred_style === 'dashed' && i%2===0) continue
          ctx.moveTo(x0,y0)
          ctx.lineTo(x1,y1)
        }
        ctx.stroke()
        ctx.globalAlpha = 1.0
      }
    }
    img.src = URL.createObjectURL(exactFrameBlob)
  }, [exactFrameBlob, annotations, frameIndex, track, style])

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const canvasX = e.clientX - rect.left
    const canvasY = e.clientY - rect.top
    // Map to canonical normalized
    // canvas element size vs actual canvas resolution
    const scaleX = canvasRef.current.width / rect.width
    const scaleY = canvasRef.current.height / rect.height
    const actualX = canvasX * scaleX
    const actualY = canvasY * scaleY
    const x_norm = actualX / canvasRef.current.width
    const y_norm = actualY / canvasRef.current.height

    setAnnotations(prev => {
      const filtered = prev.filter(a => a.frame_index !== frameIndex)
      return [...filtered, { frame_index: frameIndex, x_norm, y_norm, visibility: 'visible' as const }]
    })
  }, [frameIndex])

  const handleMarkNotVisible = () => {
    setAnnotations(prev => {
      const filtered = prev.filter(a => a.frame_index !== frameIndex)
      return [...filtered, { frame_index: frameIndex, visibility: 'not_visible' as const }]
    })
  }

  const handleMarkOutOfFrame = () => {
    setAnnotations(prev => {
      const filtered = prev.filter(a => a.frame_index !== frameIndex)
      return [...filtered, { frame_index: frameIndex, visibility: 'out_of_frame' as const }]
    })
  }

  const handleCreateAnnotationSet = async () => {
    if (!videoId) return
    const interval = analysisInterval || { start_frame: 0, end_frame: Math.min(1799, (manifest?.frame_count||100)-1) }
    const res = await api.post(`/videos/${videoId}/annotation-sets`, {
      analysis_interval: interval,
      annotations,
      idempotency_key: uuidv4()
    })
    return res.data
  }

  const handleRequestTracking = async () => {
    const annSet = await handleCreateAnnotationSet()
    if (!annSet) return
    const res = await api.post(`/videos/${videoId}/analyses`, {
      annotation_set_id: annSet.id,
      engine: 'classical',
      engine_config: { max_gap_ms: 100 },
      idempotency_key: uuidv4()
    })
    const analysisId = res.data.id
    // Poll analysis
    const poll = setInterval(async () => {
      const aRes = await api.get(`/analyses/${analysisId}`)
      if (aRes.data.status === 'succeeded' && aRes.data.track_version_id) {
        clearInterval(poll)
        const tRes = await api.get(`/tracks/${aRes.data.track_version_id}`)
        setTrack(tRes.data.points)
      } else if (aRes.data.status === 'failed') {
        clearInterval(poll)
        alert('Tracking failed: ' + aRes.data.error)
      }
    }, 2000)
  }

  const handleManualTrack = async () => {
    const annSet = await handleCreateAnnotationSet()
    if (!annSet || !videoId) return
    // For manual workflow, we call a special endpoint? We use track creation via service directly?
    // For MVP, we create manual track via backend service: we need an endpoint to create manual track from annotation set
    // We'll implement via POST /videos/{video_id}/tracks/manual
    // For now, we simulate by creating track version via same as annotation set and then fetching
    // Actually we have endpoint POST /tracks/{id}/revisions for manual, but we need initial manual track
    // We'll call backend endpoint that we haven't defined: we will create via direct API that creates manual track
    // Workaround: use analysis with classical but with only manual anchors and gap policy will produce manual+interpolated
    // For pure manual, we can call our tracking service's create_manual_track via a new endpoint we will add later
    // For now, we just set track to annotations converted
    const points = annotations.filter(a=>a.visibility==='visible').map(a=> ({
      frame_index: a.frame_index,
      pts_us: a.frame_index*33333,
      x_norm: a.x_norm,
      y_norm: a.y_norm,
      provenance: 'manual',
      visibility: 'visible'
    }))
    setTrack(points)
  }

  const handleExport = async () => {
    if (track.length === 0) {
      alert('No track to export')
      return
    }
    // Need track_version_id - we have track from analysis or manual
    // For manual, we need to create track version first via backend
    // For simplicity, we will create a track version via API if not exists
    // We will first create annotation set and then create manual track via backend endpoint we need to add: POST /videos/{videoId}/tracks
    // For MVP, we assume we have track_version_id from last analysis
    // Let's fetch latest track versions
    const res = await api.get(`/videos/${videoId}/tracks`)
    const latest = res.data[0]
    if (!latest) {
      alert('No track version found, please run tracking first')
      return
    }
    const renderRes = await api.post(`/tracks/${latest.id}/renders`, {
      style: { ...style, export: { width: 1280, height: 720, fps: 30 } },
      idempotency_key: uuidv4()
    })
    const renderId = renderRes.data.id
    const poll = setInterval(async () => {
      const rRes = await api.get(`/renders/${renderId}`)
      if (rRes.data.status === 'succeeded') {
        clearInterval(poll)
        const dlRes = await api.get(`/renders/${renderId}/download`)
        window.open(dlRes.data.url, '_blank')
      } else if (rRes.data.status === 'failed') {
        clearInterval(poll)
        alert('Render failed')
      }
    }, 2000)
  }

  if (!video) return <div>Loading video...</div>
  if (video.preparation_status !== 'ready') {
    return <div>Preparing video: {video.preparation_status} {video.preparation_error && <span className="text-red-600">{video.preparation_error}</span>}</div>
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">Editor: {video.original_filename}</h2>
        <div className="text-sm">Frame {frameIndex} / {manifest?.frame_count || '?'}</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <div className="border bg-black rounded overflow-hidden">
            <canvas ref={canvasRef} onClick={handleCanvasClick} className="w-full cursor-crosshair" />
          </div>

          <div className="mt-2 flex gap-2 items-center">
            <button onClick={() => setFrameIndex(f => Math.max(0, f-1))} className="px-3 py-1 border rounded">Prev</button>
            <input
              type="range"
              min={0}
              max={(manifest?.frame_count||100)-1}
              value={frameIndex}
              onChange={(e) => setFrameIndex(parseInt(e.target.value))}
              className="flex-1"
            />
            <button onClick={() => setFrameIndex(f => Math.min((manifest?.frame_count||100)-1, f+1))} className="px-3 py-1 border rounded">Next</button>
          </div>

          <div className="mt-2 flex gap-2">
            <button onClick={handleMarkNotVisible} className="px-3 py-1 bg-yellow-500 text-white rounded text-sm">Mark Not Visible</button>
            <button onClick={handleMarkOutOfFrame} className="px-3 py-1 bg-gray-600 text-white rounded text-sm">Mark Out of Frame</button>
            <button onClick={() => setAnnotations(prev => prev.filter(a=>a.frame_index!==frameIndex))} className="px-3 py-1 bg-red-500 text-white rounded text-sm">Delete Anchor</button>
          </div>

          {playback && (
            <div className="mt-4">
              <h4 className="font-semibold">Preview Video</h4>
              <video ref={videoRef} src={playback.url} controls className="w-full mt-2" />
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div className="border rounded p-3 bg-white">
            <h4 className="font-semibold mb-2">Analysis Interval</h4>
            <div className="flex gap-2">
              <input
                type="number"
                placeholder="Start frame"
                value={analysisInterval?.start_frame ?? ''}
                onChange={(e) => setAnalysisInterval(prev => ({ start_frame: parseInt(e.target.value)||0, end_frame: prev?.end_frame||100 }))}
                className="border rounded px-2 py-1 w-1/2"
              />
              <input
                type="number"
                placeholder="End frame"
                value={analysisInterval?.end_frame ?? ''}
                onChange={(e) => setAnalysisInterval(prev => ({ start_frame: prev?.start_frame||0, end_frame: parseInt(e.target.value)||100 }))}
                className="border rounded px-2 py-1 w-1/2"
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">Max 15s, 1800 frames. Default 0-1799.</p>
          </div>

          <div className="border rounded p-3 bg-white">
            <h4 className="font-semibold mb-2">Annotations ({annotations.length})</h4>
            <div className="max-h-40 overflow-y-auto text-xs">
              {annotations.sort((a,b)=>a.frame_index-b.frame_index).map(a=>(
                <div key={a.frame_index} className="flex justify-between">
                  <span>Frame {a.frame_index}</span>
                  <span>{a.visibility} {a.x_norm?.toFixed(3)},{a.y_norm?.toFixed(3)}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 flex gap-2">
              <button onClick={handleManualTrack} className="px-3 py-1 bg-blue-600 text-white rounded text-sm">Generate Manual Path</button>
              <button onClick={handleRequestTracking} className="px-3 py-1 bg-green-600 text-white rounded text-sm">Request Assisted Tracking</button>
            </div>
          </div>

          <div className="border rounded p-3 bg-white">
            <h4 className="font-semibold mb-2">Tracer Style</h4>
            <div className="space-y-2 text-sm">
              <label className="flex justify-between">Color <input type="color" value={style.color} onChange={(e)=>setStyle(s=>({...s,color:e.target.value}))} /></label>
              <label className="flex justify-between">Stroke <input type="range" min={0.001} max={0.02} step={0.001} value={style.stroke_width_norm} onChange={(e)=>setStyle(s=>({...s,stroke_width_norm:parseFloat(e.target.value)}))} /></label>
              <label className="flex justify-between">Trail ms <input type="number" value={style.trail_duration_ms} onChange={(e)=>setStyle(s=>({...s,trail_duration_ms:parseInt(e.target.value)}))} className="border rounded w-20 px-1" /></label>
              <label className="flex justify-between">Glow <input type="checkbox" checked={style.glow} onChange={(e)=>setStyle(s=>({...s,glow:e.target.checked}))} /></label>
              <label className="flex justify-between">Fade <input type="checkbox" checked={style.fade} onChange={(e)=>setStyle(s=>({...s,fade:e.target.checked}))} /></label>
              <label className="flex justify-between">Head <select value={style.head_marker} onChange={(e)=>setStyle(s=>({...s,head_marker:e.target.value}))} className="border rounded"><option value="none">none</option><option value="circle">circle</option><option value="dot">dot</option></select></label>
            </div>
          </div>

          <div className="border rounded p-3 bg-white">
            <h4 className="font-semibold mb-2">Track ({track.length} points)</h4>
            <div className="text-xs">
              <div>Detected: {track.filter((p:any)=>p.provenance==='detected').length}</div>
              <div>Manual: {track.filter((p:any)=>p.provenance==='manual').length}</div>
              <div>Interpolated: {track.filter((p:any)=>p.provenance==='interpolated').length}</div>
              <div>Missing: {track.filter((p:any)=>p.x_norm==null).length}</div>
            </div>
            <button onClick={handleExport} className="mt-2 w-full bg-purple-600 text-white py-2 rounded">Export MP4</button>
          </div>
        </div>
      </div>
    </div>
  )
}
