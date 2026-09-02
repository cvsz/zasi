import { createRoot } from 'react-dom/client';
import App from './app.jsx?legacy';

const root = document.getElementById('root');
if (!root) {
    throw new Error('ZASI cockpit root element is missing');
}

createRoot(root).render(<App />);
