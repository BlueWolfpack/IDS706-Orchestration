import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { GuidePage } from './pages/GuidePage'
import { ControlCenterPage } from './pages/ControlCenterPage'
import { ProjectDetailPage } from './pages/ProjectDetailPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SetupPage } from './pages/SetupPage'
import { SolutionLoopPage } from './pages/SolutionLoopPage'
import { LabLoopPage } from './pages/LabLoopPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/guide" replace />} />
        <Route path="/guide" element={<GuidePage />} />
        <Route path="/lab-loop" element={<LabLoopPage />} />
        <Route path="/solution-loop" element={<SolutionLoopPage />} />
        <Route path="/advanced" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/projects/:projectId/new" element={<SetupPage />} />
        <Route path="/session/:sessionId" element={<ControlCenterPage />} />
        <Route path="*" element={<Navigate to="/guide" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
