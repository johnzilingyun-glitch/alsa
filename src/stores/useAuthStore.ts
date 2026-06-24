import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface AuthUser {
  user_id: string;
  username: string;
  display_name: string;
  role: 'admin' | 'researcher' | 'viewer';
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
  initFromStorage: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,

      login: async (username: string, password: string) => {
        set({ isLoading: true });
        try {
          const formData = new URLSearchParams();
          formData.append('username', username);
          formData.append('password', password);

          const res = await fetch('/api/auth/token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData.toString(),
          });

          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            const msg = typeof data.detail === 'string'
              ? data.detail
              : Array.isArray(data.detail)
                ? data.detail.map((d: any) => d.msg || d).join('; ')
                : data.detail || 'Login failed';
            throw new Error(msg);
          }

          const data = await res.json();
          const { access_token, user } = data;

          localStorage.setItem('auth_token', access_token);
          set({
            token: access_token,
            user: user,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      register: async (username: string, password: string, displayName?: string) => {
        set({ isLoading: true });
        try {
          const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              username,
              password,
              display_name: displayName || username,
            }),
          });

          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            const msg = typeof data.detail === 'string'
              ? data.detail
              : Array.isArray(data.detail)
                ? data.detail.map((d: any) => d.msg || d).join('; ')
                : data.detail || 'Registration failed';
            throw new Error(msg);
          }

          await get().login(username, password);
        } catch (error) {
          set({ isLoading: false });
          throw error;
        }
      },

      logout: () => {
        localStorage.removeItem('auth_token');
        set({
          user: null,
          token: null,
          isAuthenticated: false,
        });
      },

      fetchMe: async () => {
        const token = get().token || localStorage.getItem('auth_token');
        if (!token) return;

        try {
          const res = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${token}` },
          });

          if (res.ok) {
            const user = await res.json();
            set({ user, token, isAuthenticated: true });
          } else {
            localStorage.removeItem('auth_token');
            set({ user: null, token: null, isAuthenticated: false });
          }
        } catch {
          console.warn('[useAuthStore] fetchMe network error, keeping existing state:');
        }
      },

      initFromStorage: () => {
        const token = localStorage.getItem('auth_token');
        if (token) {
          set({ token, isAuthenticated: true });
          get().fetchMe();
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token, user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
);

// Utility: attach auth header to fetch calls
export function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem('auth_token');
  const headers = new Headers(options.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  return fetch(url, { ...options, headers });
}
