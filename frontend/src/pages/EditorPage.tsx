import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useEffect, useRef, useState, useCallback } from 'react'
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
  const [isDemoMode, setIsDemoMode] = useState(false)
  const demoFrames = 60
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

  useEffect(() => {
    if (!videoId || window.location.pathname.includes('/demo')) {
      setIsDemoMode(true)
    }
  }, [videoId])

  const { data: video, isError: videoError } = useQuery({
    queryKey: ['video', videoId],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}`)
      return res.data
    },
    refetchInterval: 3000,
    enabled: !!videoId && !isDemoMode,
    retry: false
  })

  useEffect(() => {
    if (videoError) setIsDemoMode(true)
  }, [videoError])

  const { data: manifest } = useQuery({
    queryKey: ['manifest', videoId],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}/frame-manifest`)
      return res.data
    },
    enabled: !!videoId && video?.preparation_status === 'ready' && !isDemoMode,
    retry: false
  })

  const { data: playback } = useQuery({
    queryKey: ['playback', videoId],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}/playback`)
      return res.data
    },
    enabled: !!videoId && video?.preparation_status === 'ready' && !isDemoMode,
    retry: false
  })

  const { data: exactFrameBlob } = useQuery({
    queryKey: ['exactFrame', videoId, frameIndex],
    queryFn: async () => {
      const res = await api.get(`/videos/${videoId}/frames/${frameIndex}`, { responseType: 'blob' })
      return res.data as Blob
    },
    enabled: !!videoId && video?.preparation_status === 'ready' && !isDemoMode,
    retry: false
  })

  // Demo mode canvas
  useEffect(() => {
    if (!isDemoMode || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const width = 640
    const height = 360
    canvas.width = width
    canvas.height = height
    ctx.fillStyle = '#1a5c1a'
    ctx.fillRect(0,0,width,height)
    ctx.strokeStyle = '#0f3d0f'
    ctx.lineWidth = 1
    for (let gx=0; gx<width; gx+=50) {
      ctx.beginPath()
      ctx.moveTo(gx,0)
      ctx.lineTo(gx,height)
      ctx.stroke()
    }
    const t = frameIndex / demoFrames
    const x = 100 + t * (width - 200)
    const y = 100 + 4*150*t*(1-t)
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(200,200,8,0,Math.PI*2)
    ctx.fill()
    ctx.beginPath()
    ctx.arc(400,100,6,0,Math.PI*2)
    ctx.fill()
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(x,y,6,0,Math.PI*2)
    ctx.fill()
    ctx.strokeStyle = '#000'
    ctx.lineWidth = 1
    ctx.stroke()
    const currentAnn = annotations.find(a => a.frame_index === frameIndex)
    if (currentAnn && currentAnn.visibility === 'visible' && currentAnn.x_norm != null && currentAnn.y_norm != null) {
      const ax = currentAnn.x_norm * width
      const ay = currentAnn.y_norm * height
      ctx.beginPath()
      ctx.arc(ax,ay,8,0,Math.PI*2)
      ctx.fillStyle = '#00FF00'
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 2
      ctx.stroke()
    }
    const trail = track.filter((p:any) => p.frame_index <= frameIndex && p.x_norm != null && p.visibility === 'visible')
    if (trail.length > 1) {
      ctx.beginPath()
      ctx.strokeStyle = style.color
      ctx.lineWidth = style.stroke_width_norm * height * 2
      // @ts-ignore
      ctx.globalAlpha = style.opacity
      for (let i=1;i<trail.length;i++) {
        const p0 = trail[i-1]
        const p1 = trail[i]
        const x0 = p0.x_norm * width
        const y0 = p0.y_norm * height
        const x1 = p1.x_norm * width
        const y1 = p1.y_norm * height
        if (p1.provenance !== 'detected' && p1.provenance !== 'manual' && style.inferred_style === 'dashed' && i%2===0) continue
        ctx.moveTo(x0,y0)
        ctx.lineTo(x1,y1)
      }
      ctx.stroke()
      ctx.globalAlpha = 1.0
    }
    if (trail.length > 0) {
      const last = trail[trail.length-1]
      if (last) {
        const hx = last.x_norm * width
        const hy = last.y_norm * height
        if (style.head_marker === 'circle') {
          ctx.beginPath()
          ctx.arc(hx,hy,8,0,Math.PI*2)
          ctx.fillStyle = style.color
          ctx.fill()
          ctx.strokeStyle = '#fff'
          ctx.lineWidth = 1
          ctx.stroke()
        }
      }
    }
    ctx.font = '12px sans-serif'
    ctx.fillStyle = 'rgba(255,255,255,0.7)'
    ctx.fillText('GolfTrace Demo - Synthetic Fixture', 10, height-10)
  }, [isDemoMode, frameIndex, annotations, track, style, demoFrames])

  useEffect(() => {
    if (isDemoMode) return
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
      const currentAnn = annotations.find(a => a.frame_index === frameIndex)
      if (currentAnn && currentAnn.visibility === 'visible' && currentAnn.x_norm != null && currentAnn.y_norm != null) {
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
  }, [exactFrameBlob, annotations, frameIndex, track, style, isDemoMode])

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const canvasX = e.clientX - rect.left
    const canvasY = e.clientY - rect.top
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
    if (!videoId || isDemoMode) return null
    const interval = analysisInterval || { start_frame: 0, end_frame: Math.min(1799, (manifest?.frame_count||100)-1) }
    const res = await api.post(`/videos/${videoId}/annotation-sets`, {
      analysis_interval: interval,
      annotations,
      idempotency_key: uuidv4()
    })
    return res.data
  }

  const handleRequestTracking = async () => {
    if (isDemoMode) {
      // Demo tracking: simple interpolation between manual anchors
      const visible = annotations.filter(a=>a.visibility==='visible' && a.x_norm!=null).sort((a,b)=>a.frame_index-b.frame_index)
      if (visible.length < 2) {
        alert('حداقل ۲ انکر دستی بذار')
        return
      }
      const points: any[] = []
      for (let i=0;i<demoFrames;i++) {
        const prev = visible.filter(v=>v.frame_index <= i).pop()
        const next = visible.filter(v=>v.frame_index >= i)[0]
        if (prev && next && prev.frame_index !== next.frame_index) {
          const t = (i - prev.frame_index) / (next.frame_index - prev.frame_index)
          points.push({
            frame_index: i,
            pts_us: i*33333,
            x_norm: (prev.x_norm! + t * (next.x_norm! - prev.x_norm!)),
            y_norm: (prev.y_norm! + t * (next.y_norm! - prev.y_norm!)),
            provenance: i===prev.frame_index || i===next.frame_index ? 'manual' : 'interpolated',
            visibility: 'visible'
          })
        } else if (prev) {
          points.push({
            frame_index: i,
            pts_us: i*33333,
            x_norm: prev.x_norm,
            y_norm: prev.y_norm,
            provenance: 'manual',
            visibility: 'visible'
          })
        }
      }
      setTrack(points)
      return
    }
    const annSet = await handleCreateAnnotationSet()
    if (!annSet) return
    const res = await api.post(`/videos/${videoId}/analyses`, {
      annotation_set_id: annSet.id,
      engine: 'classical',
      engine_config: { max_gap_ms: 100 },
      idempotency_key: uuidv4()
    })
    const analysisId = res.data.id
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
    if (isDemoMode) {
      const points = annotations.filter(a=>a.visibility==='visible').map(a=> ({
        frame_index: a.frame_index,
        pts_us: a.frame_index*33333,
        x_norm: a.x_norm,
        y_norm: a.y_norm,
        provenance: 'manual',
        visibility: 'visible'
      }))
      setTrack(points)
      return
    }
    const annSet = await handleCreateAnnotationSet()
    if (!annSet || !videoId) return
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
    if (isDemoMode) {
      alert('حالت دمو: اکسپورت MP4 فقط وقتی بک‌اند لوکال با docker-compose بالا باشه کار می‌کنه. توی دمو ترک رو می‌بینی ولی دانلود MP4 نیاز به بک‌اند داره. دستورات توی README هست.')
      return
    }
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

  if (!isDemoMode && !video) return <div>Loading video... اگر بک‌اند وصل نیست، <a href="/golftrace/demo" className="text-blue-600 underline">ادیتور دمو رو باز کن</a></div>
  if (!isDemoMode && video && video.preparation_status !== 'ready') {
    return <div>Preparing video: {video.preparation_status} {video.preparation_error && <span className="text-red-600">{video.preparation_error}</span>}</div>
  }

  const totalFrames = isDemoMode ? demoFrames : (manifest?.frame_count || 100)

  return (
    <div className="flex flex-col gap-4">
      {isDemoMode && (
        <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
          <p className="font-bold text-blue-800">حالت دمو - بدون نیاز به بک‌اند</p>
          <p className="text-blue-700">این یه فیچر مصنوعی هست (زمین سبز + توپ سفید). روی کانواس کلیک کن تا انکر دستی بذاری، بعد Generate Manual Path یا Request Assisted Tracking (interpolation) بزن. برای آپلود ویدیوی واقعی و اکسپورت MP4 باید بک‌اند رو لوکال اجرا کنی.</p>
        </div>
      )}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold">Editor: {isDemoMode ? 'Demo Synthetic Fixture' : video?.original_filename}</h2>
        <div className="text-sm">Frame {frameIndex} / {totalFrames}</div>
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
              max={totalFrames-1}
              value={frameIndex}
              onChange={(e) => setFrameIndex(parseInt(e.target.value))}
              className="flex-1"
            />
            <button onClick={() => setFrameIndex(f => Math.min(totalFrames-1, f+1))} className="px-3 py-1 border rounded">Next</button>
          </div>

          <div className="mt-2 flex gap-2">
            <button onClick={handleMarkNotVisible} className="px-3 py-1 bg-yellow-500 text-white rounded text-sm">Mark Not Visible</button>
            <button onClick={handleMarkOutOfFrame} className="px-3 py-1 bg-gray-600 text-white rounded text-sm">Mark Out of Frame</button>
            <button onClick={() => setAnnotations(prev => prev.filter(a=>a.frame_index!==frameIndex))} className="px-3 py-1 bg-red-500 text-white rounded text-sm">Delete Anchor</button>
          </div>

          {playback && !isDemoMode && (
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
