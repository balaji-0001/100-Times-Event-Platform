import { createRoot } from 'react-dom/client';

import App from './App';
import { ErrorBoundary } from '@/components/error-boundary';
import { setAuthTokenGetter, setBaseUrl } from '@workspace/api-client-react';

import './index.css';

// Browser requests need an absolute API origin while Vite is on a separate port.
setBaseUrl(import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000');
setAuthTokenGetter(() => localStorage.getItem('100-times-auth-token'));

createRoot(document.getElementById('root')!, {
  // Keeps caught errors off reportError(), which would raise the dev overlay.
  onCaughtError: (error, errorInfo) => {
    console.error(error, errorInfo.componentStack);
  },
}).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
