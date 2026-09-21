import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useState } from 'react'
import { v4 as uuidv4 } from '../utils/uuid'

export default function ProjectDetail() {
  const { projectId } = useParams()
  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: async () => {
      const res = await api.get(`/projects/${projectId}`)
      return res.data
    }
  })

  const { data: videos, refetch } = useQuery({
    queryKey: ['videos', projectId],
    queryFn: async () => {
      // List videos via project? For MVP we list via backend? We'll need endpoint to list videos per project - not yet defined, so we store locally
      // For now return empty and rely on upload flow
      return []
    }
  })

  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !projectId) return
    setUploading(true)
    try {
      const idempotencyKey = uuidv4()
      const res = await api.post(`/projects/${projectId}/uploads`, {
        filename: file.name,
        size_bytes: file.size,
        idempotency_key: idempotencyKey
      })
      const { upload_id, upload_url } = res.data

      // Direct upload via PUT or POST depending on backend
      if (upload_url.includes('/direct-upload')) {
        // Use direct upload endpoint
        await api.post(`/uploads/${upload_id}/direct-upload`, file, {
          headers: { 'Content-Type': 'application/octet-stream' },
          onUploadProgress: (ev) => {
            if (ev.total) setProgress(Math.round(ev.loaded / ev.total * 100))
          }
        })
      } else {
        // S3 presigned PUT
        await fetch(upload_url, { method: 'PUT', body: file })
      }

      const completeRes = await api.post(`/uploads/${upload_id}/complete`, {})
      const { video_id } = completeRes.data
      // Navigate to editor
      window.location.href = `/projects/${projectId}/videos/${video_id}`
    } catch (err) {
      console.error(err)
      alert('Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <Link to="/" className="text-sm text-blue-600 hover:underline">← Back to projects</Link>
      <h2 className="text-2xl font-bold mt-2">{project?.title}</h2>
      <p className="text-gray-500 text-sm">{project?.id}</p>

      <div className="mt-6 border rounded p-4 bg-white">
        <h3 className="font-semibold mb-2">Upload Video</h3>
        <p className="text-sm text-gray-600 mb-2">Max 500 MiB, 60s, 3840x2160, up to 120 FPS</p>
        <input type="file" accept="video/*" onChange={handleUpload} disabled={uploading} />
        {uploading && <div className="mt-2 text-sm">Uploading {progress}%</div>}
      </div>

      <div className="mt-6">
        <h3 className="font-semibold">Videos</h3>
        <p className="text-sm text-gray-500">After upload, you will be redirected to editor. For existing videos, use direct link.</p>
      </div>
    </div>
  )
}
