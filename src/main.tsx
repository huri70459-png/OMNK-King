import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app'
import { NotebookApp } from './notebook/NotebookApp'
import './index.css'
import './refinement.css'

function Root() {
  return window.location.hash === '#notebook' ? <NotebookApp /> : <App />
}

createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>)
