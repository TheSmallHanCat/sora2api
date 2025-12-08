import type {
  Token,
  Stats,
  Log,
  AdminConfig,
  ProxyConfig,
  WatermarkFreeConfig,
  CacheConfig,
  GenerationTimeoutConfig,
  TokenRefreshConfig,
  LoginResponse,
  TokenTestResponse,
  ConvertResponse,
  ImportResponse,
  Sora2ActivateResponse,
  ApiResponse,
} from '../types';

const getToken = (): string | null => localStorage.getItem('adminToken');

const setToken = (token: string): void => localStorage.setItem('adminToken', token);

const removeToken = (): void => localStorage.removeItem('adminToken');

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function apiRequest<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    removeToken();
    window.location.href = '/login';
    throw new ApiError('Unauthorized', 401);
  }

  const data = await response.json();

  if (!response.ok && response.status !== 409) {
    throw new ApiError(data.message || data.detail || 'Request failed', response.status);
  }

  return data;
}

export const api = {
  // Auth
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json();
    if (data.success && data.token) {
      setToken(data.token);
    }
    return data;
  },

  logout: (): void => {
    removeToken();
    window.location.href = '/login';
  },

  checkAuth: async (): Promise<boolean> => {
    const token = getToken();
    if (!token) return false;
    try {
      await apiRequest<Stats>('/api/stats');
      return true;
    } catch {
      return false;
    }
  },

  getToken,
  removeToken,

  // Stats
  getStats: (): Promise<Stats> => apiRequest<Stats>('/api/stats'),

  // Tokens
  getTokens: (): Promise<Token[]> => apiRequest<Token[]>('/api/tokens'),

  addToken: (data: {
    token: string;
    st?: string | null;
    rt?: string | null;
    client_id?: string | null;
    remark?: string | null;
    image_enabled: boolean;
    video_enabled: boolean;
    image_concurrency: number;
    video_concurrency: number;
  }): Promise<ApiResponse & { status?: number }> =>
    fetch('/api/tokens', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getToken()}`,
      },
      body: JSON.stringify(data),
    }).then(async (r) => {
      const json = await r.json();
      return { ...json, status: r.status };
    }),

  updateToken: (
    id: number,
    data: {
      token: string;
      st?: string | null;
      rt?: string | null;
      client_id?: string | null;
      remark?: string | null;
      image_enabled: boolean;
      video_enabled: boolean;
      image_concurrency?: number | null;
      video_concurrency?: number | null;
    }
  ): Promise<ApiResponse> =>
    apiRequest<ApiResponse>(`/api/tokens/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteToken: (id: number): Promise<ApiResponse> =>
    apiRequest<ApiResponse>(`/api/tokens/${id}`, { method: 'DELETE' }),

  testToken: (id: number): Promise<TokenTestResponse> =>
    apiRequest<TokenTestResponse>(`/api/tokens/${id}/test`, { method: 'POST' }),

  enableToken: (id: number): Promise<ApiResponse> =>
    apiRequest<ApiResponse>(`/api/tokens/${id}/enable`, { method: 'POST' }),

  disableToken: (id: number): Promise<ApiResponse> =>
    apiRequest<ApiResponse>(`/api/tokens/${id}/disable`, { method: 'POST' }),

  convertST2AT: (st: string): Promise<ConvertResponse> =>
    apiRequest<ConvertResponse>('/api/tokens/st2at', {
      method: 'POST',
      body: JSON.stringify({ st }),
    }),

  convertRT2AT: (rt: string): Promise<ConvertResponse> =>
    apiRequest<ConvertResponse>('/api/tokens/rt2at', {
      method: 'POST',
      body: JSON.stringify({ rt }),
    }),

  importTokens: (tokens: unknown[]): Promise<ImportResponse> =>
    apiRequest<ImportResponse>('/api/tokens/import', {
      method: 'POST',
      body: JSON.stringify({ tokens }),
    }),

  activateSora2: (tokenId: number, inviteCode: string): Promise<Sora2ActivateResponse> =>
    apiRequest<Sora2ActivateResponse>(
      `/api/tokens/${tokenId}/sora2/activate?invite_code=${inviteCode}`,
      { method: 'POST' }
    ),

  // Admin Config
  getAdminConfig: (): Promise<AdminConfig> =>
    apiRequest<AdminConfig>('/api/admin/config'),

  saveAdminConfig: (data: { error_ban_threshold: number }): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/admin/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePassword: (data: {
    username?: string;
    old_password: string;
    new_password: string;
  }): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/admin/password', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateApiKey: (newApiKey: string): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/admin/apikey', {
      method: 'POST',
      body: JSON.stringify({ new_api_key: newApiKey }),
    }),

  toggleDebug: (enabled: boolean): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/admin/debug', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),

  // Proxy Config
  getProxyConfig: (): Promise<ProxyConfig> =>
    apiRequest<ProxyConfig>('/api/proxy/config'),

  saveProxyConfig: (data: ProxyConfig): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/proxy/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Watermark Free Config
  getWatermarkFreeConfig: (): Promise<WatermarkFreeConfig> =>
    apiRequest<WatermarkFreeConfig>('/api/watermark-free/config'),

  saveWatermarkFreeConfig: (data: WatermarkFreeConfig): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/watermark-free/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Cache Config
  getCacheConfig: (): Promise<{ success: boolean; config: CacheConfig }> =>
    apiRequest<{ success: boolean; config: CacheConfig }>('/api/cache/config'),

  saveCacheEnabled: (enabled: boolean): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/cache/enabled', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),

  saveCacheTimeout: (timeout: number): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/cache/config', {
      method: 'POST',
      body: JSON.stringify({ timeout }),
    }),

  saveCacheBaseUrl: (baseUrl: string): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/cache/base-url', {
      method: 'POST',
      body: JSON.stringify({ base_url: baseUrl }),
    }),

  // Generation Timeout Config
  getGenerationTimeout: (): Promise<{ success: boolean; config: GenerationTimeoutConfig }> =>
    apiRequest<{ success: boolean; config: GenerationTimeoutConfig }>('/api/generation/timeout'),

  saveGenerationTimeout: (data: GenerationTimeoutConfig): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/generation/timeout', {
      method: 'POST',
      body: JSON.stringify({
        image_timeout: data.image_timeout,
        video_timeout: data.video_timeout,
      }),
    }),

  // Token Refresh Config
  getTokenRefreshConfig: (): Promise<{ success: boolean; config: TokenRefreshConfig }> =>
    apiRequest<{ success: boolean; config: TokenRefreshConfig }>('/api/token-refresh/config'),

  toggleTokenRefresh: (enabled: boolean): Promise<ApiResponse> =>
    apiRequest<ApiResponse>('/api/token-refresh/enabled', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),

  // Logs
  getLogs: (limit: number = 100): Promise<Log[]> =>
    apiRequest<Log[]>(`/api/logs?limit=${limit}`),
};

export { ApiError };
