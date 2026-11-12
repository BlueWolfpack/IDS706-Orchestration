import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

// No StrictMode: it remounts effects and would open a second SSE subscription.
createRoot(document.getElementById('root')!).render(<App />)
