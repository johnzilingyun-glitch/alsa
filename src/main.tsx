import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';
import './i18n';
import { useUIStore } from './stores/useUIStore';

(window as any).useUIStore = useUIStore;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary fallback="应用加载失败，请刷新页面重试。">
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
