import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/index.css'
import App from './App.tsx'

try {
  const saved = localStorage.getItem('agent-chat:theme')
  document.documentElement.setAttribute('data-theme', saved === 'light' ? 'light' : 'dark')
} catch {
  document.documentElement.setAttribute('data-theme', 'dark')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
