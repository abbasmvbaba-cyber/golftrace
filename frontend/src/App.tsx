import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useUIStore } from './stores/ui'
import ProjectList from './pages/ProjectList'
import ProjectDetail from './pages/ProjectDetail'
import EditorPage from './pages/EditorPage'
import { useEffect } from 'react'

const queryClient = new QueryClient()

function App() {
  const { lang, dir } = useUIStore()

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
  }, [lang, dir])

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen">
          <header className="bg-white shadow-sm border-b">
            <div className="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center">
              <h1 className="text-xl font-bold text-green-700">GolfTrace</h1>
              <LangSwitcher />
            </div>
          </header>
          <main className="max-w-7xl mx-auto p-4">
            <Routes>
              <Route path="/" element={<ProjectList />} />
              <Route path="/projects/:projectId" element={<ProjectDetail />} />
              <Route path="/projects/:projectId/videos/:videoId" element={<EditorPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function LangSwitcher() {
  const { lang, setLang } = useUIStore()
  return (
    <select
      value={lang}
      onChange={(e) => setLang(e.target.value as 'en' | 'fa')}
      className="border rounded px-2 py-1 text-sm"
    >
      <option value="en">English</option>
      <option value="fa">فارسی</option>
    </select>
  )
}

export default App
