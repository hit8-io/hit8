import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import Home2 from './pages/Home2'

export default function App() {
  return (
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/home2" element={<Home2 />} />
      </Routes>
    </BrowserRouter>
  )
}
