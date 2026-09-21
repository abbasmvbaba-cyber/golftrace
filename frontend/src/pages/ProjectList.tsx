import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listProjects, createProject } from '../lib/api'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { v4 as uuidv4 } from '../utils/uuid'

export default function ProjectList() {
  const queryClient = useQueryClient()
  const { data: projects, isLoading } = useQuery({ queryKey: ['projects'], queryFn: listProjects })
  const [title, setTitle] = useState('')

  const createMut = useMutation({
    mutationFn: () => createProject(title || 'Untitled', uuidv4()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setTitle('')
    }
  })

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Projects</h2>
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
          {projects?.map((p) => (
            <Link key={p.id} to={`/projects/${p.id}`} className="border rounded p-4 bg-white hover:shadow">
              <div className="font-semibold">{p.title}</div>
              <div className="text-sm text-gray-500">{p.id} • {new Date(p.created_at).toLocaleString()}</div>
            </Link>
          ))}
          {projects?.length === 0 && <p className="text-gray-500">No projects yet</p>}
        </div>
      )}
    </div>
  )
}
