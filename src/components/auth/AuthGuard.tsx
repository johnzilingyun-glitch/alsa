import React, { useState, useEffect } from 'react';
import { useAuthStore } from '../../stores/useAuthStore';
import { LoginPage } from './LoginPage';
import { RegisterPage } from './RegisterPage';

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { isAuthenticated, initFromStorage } = useAuthStore();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    initFromStorage();
    setInitialized(true);
  }, [initFromStorage]);

  if (!initialized) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-50">
        <div className="w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    if (mode === 'register') {
      return <RegisterPage onSwitchToLogin={() => setMode('login')} />;
    }
    return <LoginPage onSwitchToRegister={() => setMode('register')} />;
  }

  return <>{children}</>;
}
