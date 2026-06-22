import React, { useState } from 'react';
import { useAuthStore } from '../../stores/useAuthStore';
import { LogIn, Eye, EyeOff, Loader2 } from 'lucide-react';

interface LoginPageProps {
  onSwitchToRegister: () => void;
}

export function LoginPage({ onSwitchToRegister }: LoginPageProps) {
  const { login, isLoading } = useAuthStore();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      await login(username, password);
    } catch (err: any) {
      setError(err.message || 'Login failed');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50">
      <div className="w-full max-w-md px-6">
        <div className="bg-white rounded-2xl shadow-xl border border-zinc-200 p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-indigo-600 text-white mb-4">
              <LogIn size={24} />
            </div>
            <h1 className="text-2xl font-bold text-zinc-900">Welcome Back</h1>
            <p className="text-sm text-zinc-500 mt-2">Sign in to your ALSA account</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-xl px-4 py-3">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-semibold text-zinc-700 mb-1.5">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full h-12 px-4 rounded-xl border border-zinc-200 bg-white text-sm font-medium text-zinc-900 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40"
                placeholder="Enter your username"
                autoFocus
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-zinc-700 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full h-12 px-4 pr-12 rounded-xl border border-zinc-200 bg-white text-sm font-medium text-zinc-900 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40"
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600 transition-colors"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading || !username || !password}
              className="w-full h-12 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-zinc-500">
              Don't have an account?{' '}
              <button
                onClick={onSwitchToRegister}
                className="text-indigo-600 font-semibold hover:text-indigo-700 transition-colors"
              >
                Sign Up
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
