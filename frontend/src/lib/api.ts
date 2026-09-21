import axios from 'axios'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export const api = axios.create({
  baseURL: apiBase,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Add dev user header for local dev
api.interceptors.request.use((config) => {
  const devUserId = localStorage.getItem('dev_user_id') || '00000000-0000-0000-0000-000000000001'
  config.headers['X-Dev-User-Id'] = devUserId
  return config
})

export interface Project {
  id: string
  title: string
  description?: string
  status: string
  version: number
  created_at: string
}

export interface Video {
  id: string
  project_id: string
  original_filename: string
  size_bytes: number
  duration_us?: number
  width?: number
  height?: number
  preparation_status: string
  created_at: string
}

export async function createProject(title: string, idempotencyKey: string) {
  const res = await api.post('/projects', { title, idempotency_key: idempotencyKey })
  return res.data
}

export async function listProjects() {
  const res = await api.get('/projects')
  return res.data as Project[]
}

export async function createUploadSession(projectId: string, filename: string, sizeBytes: number, idempotencyKey: string) {
  const res = await api.post(`/projects/${projectId}/uploads`, {
    filename,
    size_bytes: sizeBytes,
    idempotency_key: idempotencyKey
  })
  return res.data
}

export async function completeUpload(uploadId: string) {
  const res = await api.post(`/uploads/${uploadId}/complete`, {})
  return res.data
}

export async function getVideo(videoId: string) {
  const res = await api.get(`/videos/${videoId}`)
  return res.data as Video
}

export async function getPlayback(videoId: string) {
  const res = await api.get(`/videos/${videoId}/playback`)
  return res.data
}

export async function getManifest(videoId: string) {
  const res = await api.get(`/videos/${videoId}/frame-manifest`)
  return res.data
}

export async function getExactFrame(videoId: string, frameIndex: number) {
  const res = await api.get(`/videos/${videoId}/frames/${frameIndex}`, { responseType: 'blob' })
  return res.data as Blob
}
