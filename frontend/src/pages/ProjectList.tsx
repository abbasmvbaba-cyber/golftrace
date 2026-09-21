import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listProjects, createProject } from '../lib/api'
import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { v4 as uuidv4 } from '../utils/uuid'

interface LocalProject {
  id: string
  title: string
  created_at: string
}

export default function ProjectList() {
  const queryClient = useQueryClient()
  const { data: projects, isLoading, isError, error } = useQuery({ 
    queryKey: ['projects'], 
    queryFn: listProjects,
    retry: false,
  })
  const [title, setTitle] = useState('')
  const [localProjects, setLocalProjects] = useState<LocalProject[]>([])
  const [isDemoMode, setIsDemoMode] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem('golftrace_local_projects')
    if (stored) {
      try {
        setLocalProjects(JSON.parse(stored))
      } catch {}
    }
    // Check if backend is reachable
    if (isError) {
      setIsDemoMode(true)
    }
  }, [isError])

  const createMut = useMutation({
    mutationFn: async () => {
      if (isDemoMode || isError) {
        // Local demo mode
        const newProj: LocalProject = {
          id: uuidv4(),
          title: title || 'Untitled',
          created_at: new Date().toISOString()
        }
        const updated = [newProj, ...localProjects]
        setLocalProjects(updated)
        localStorage.setItem('golftrace_local_projects', JSON.stringify(updated))
        return newProj
      } else {
        return createProject(title || 'Untitled', uuidv4())
      }
    },
    onSuccess: () => {
      if (!isDemoMode && !isError) {
        queryClient.invalidateQueries({ queryKey: ['projects'] })
      }
      setTitle('')
    }
  })

  const displayProjects = isDemoMode || isError ? localProjects : projects

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Projects</h2>
      
      {(isDemoMode || isError) && (
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-4 text-sm">
          <p className="font-semibold text-yellow-800">حالت دمو - Demo Mode</p>
          <p className="text-yellow-700">
            بک‌اند وصل نیست (GitHub Pages فقط فرانت‌اند رو سرو می‌کنه). پروژه‌ها به صورت لوکال توی مرورگر ذخیره میشن.
            <br/>
            برای فول اپلیکیشن (آپلود ویدیو واقعی، ترک، اکسپورت MP4) باید بک‌اند رو لوکال با docker-compose اجرا کنی.
            <br/>
            <a href="https://github.com/abbasmvbaba-cyber/golftrace#quick-start-docker" className="text-blue-600 underline" target="_blank">دستورات توی README</a>
          </p>
          <Link to="/demo" className="inline-block mt-2 bg-blue-600 text-white px-3 py-1 rounded text-sm">
            باز کردن ادیتور دمو (بدون نیاز به بک‌اند) →
          </Link>
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded p-2 mb-4 text-xs text-red-700">
          Backend error: {(error as any)?.message || 'Failed to fetch'} - API: {(import.meta as any).env?.VITE_API_BASE_URL || 'not configured'}
        </div>
      )}

      <div className="flex gap-2 mb-6">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Project title"
          className="border rounded px-3 py-2 flex-1"
        />
        <button
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
          className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50"
        >
          Create
        </button>
      </div>

      {isLoading ? <p>Loading...</p> : (
        <div className="grid gap-3">
          {displayProjects?.map((p: any) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="border rounded p-4 bg-white hover:shadow">
              <div className="font-semibold">{p.title}</div>
              <div className="text-sm text-gray-500">{p.id} • {new Date(p.created_at).toLocaleString()}</div>
            </Link>
          ))}
          {(!displayProjects || displayProjects.length === 0) && <p className="text-gray-500">No projects yet - create one above or open demo editor</p>}
        </div>
      )}

      <div className="mt-8 border-t pt-4">
        <h3 className="font-semibold mb-2">Scientific Honesty</h3>
        <p className="text-sm text-gray-600">
          We estimate 2D trajectory in image coordinates only. No real-world carry distance, ball speed, spin, launch angle, or 3D flight claims from uncalibrated monocular footage.
          <br/>
          <span className="text-xs">ما فقط مسیر دوبعدی در مختصات تصویر را تخمین می‌زنیم.</span>
        </p>
      </div>
    </div>
  )
}
