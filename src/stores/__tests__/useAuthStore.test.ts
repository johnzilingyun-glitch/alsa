import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore, authFetch } from '../useAuthStore';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: () => { store = {}; },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
    useAuthStore.setState({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  describe('initial state', () => {
    it('should start unauthenticated', () => {
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
      expect(state.user).toBeNull();
      expect(state.token).toBeNull();
      expect(state.isLoading).toBe(false);
    });
  });

  describe('logout', () => {
    it('should clear user, token, and auth status', () => {
      useAuthStore.setState({
        user: { user_id: '1', username: 'test', display_name: 'Test', role: 'admin' },
        token: 'test-token',
        isAuthenticated: true,
      });

      useAuthStore.getState().logout();

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.token).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });

    it('should remove token from localStorage', () => {
      useAuthStore.setState({ token: 'test-token' });
      useAuthStore.getState().logout();
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('auth_token');
    });
  });

  describe('initFromStorage', () => {
    it('should set authenticated when token exists in storage', () => {
      localStorageMock.getItem.mockReturnValue('stored-token');
      // Mock fetch for fetchMe
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ user_id: '1', username: 'user', display_name: 'User', role: 'viewer' }),
      });

      useAuthStore.getState().initFromStorage();
      const state = useAuthStore.getState();
      expect(state.token).toBe('stored-token');
      expect(state.isAuthenticated).toBe(true);
    });

    it('should not authenticate when no token in storage', () => {
      localStorageMock.getItem.mockReturnValue(null as unknown as string);
      useAuthStore.getState().initFromStorage();
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('login', () => {
    it('should set loading during login attempt', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          access_token: 'new-token',
          user: { user_id: '1', username: 'test', display_name: 'Test', role: 'admin' },
        }),
      });

      const loginPromise = useAuthStore.getState().login('test', 'password');
      // isLoading should have been set
      await loginPromise;

      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.token).toBe('new-token');
      expect(state.user?.username).toBe('test');
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('auth_token');
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/auth/token',
        expect.objectContaining({ credentials: 'include' }),
      );
    });

    it('should throw on failed login', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ detail: 'Invalid credentials' }),
      });

      await expect(useAuthStore.getState().login('bad', 'password')).rejects.toThrow('Invalid credentials');
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('should handle array detail errors', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ detail: [{ msg: 'field required' }] }),
      });

      await expect(useAuthStore.getState().login('bad', 'pw')).rejects.toThrow('field required');
    });
  });

  describe('fetchMe', () => {
    it('should clear auth on 401 response', async () => {
      useAuthStore.setState({ token: 'expired-token', isAuthenticated: true });
      localStorageMock.getItem.mockReturnValue('expired-token');
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 });

      await useAuthStore.getState().fetchMe();
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
      expect(useAuthStore.getState().user).toBeNull();
    });

    it('should request current user with cookie credentials when no legacy token exists', async () => {
      useAuthStore.setState({ token: null });
      localStorageMock.getItem.mockReturnValue(null as unknown as string);
      const fetchSpy = vi.fn().mockResolvedValue({ ok: false, status: 401 });
      global.fetch = fetchSpy;

      await useAuthStore.getState().fetchMe();
      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/auth/me',
        expect.objectContaining({ credentials: 'include' }),
      );
    });
  });
});

describe('authFetch', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it('should attach legacy Authorization header and include credentials when token exists', async () => {
    localStorageMock.getItem.mockReturnValue('my-token');
    global.fetch = vi.fn().mockResolvedValue({ ok: true });

    await authFetch('/api/test');

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );

    const callArgs = (global.fetch as any).mock.calls[0];
    const headers = callArgs[1].headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer my-token');
    expect(callArgs[1].credentials).toBe('include');
  });

  it('should include credentials and omit Authorization when no token exists', async () => {
    localStorageMock.getItem.mockReturnValue(null as unknown as string);
    global.fetch = vi.fn().mockResolvedValue({ ok: true });

    await authFetch('/api/test');

    const callArgs = (global.fetch as any).mock.calls[0];
    const headers = callArgs[1].headers as Headers;
    expect(headers.get('Authorization')).toBeNull();
    expect(callArgs[1].credentials).toBe('include');
  });
});
