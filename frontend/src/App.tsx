import { Routes, Route } from 'react-router-dom'
import WelcomePage from '@/pages/WelcomePage'
import InicioPage from '@/pages/InicioPage'
import NotFoundPage from '@/pages/NotFoundPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<WelcomePage />} />
      <Route path="/inicio" element={<InicioPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

export default App
