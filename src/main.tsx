import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './index.css';
import './i18n';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary fallback="应用加载失败，请刷新页面重试。">
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
