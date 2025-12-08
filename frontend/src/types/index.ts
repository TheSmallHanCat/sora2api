export interface Token {
  id: number;
  email: string;
  token: string;
  st?: string | null;
  rt?: string | null;
  client_id?: string | null;
  is_active: boolean;
  expiry_time?: string | null;
  plan_type?: string | null;
  plan_title?: string | null;
  subscription_end?: string | null;
  sora2_supported?: boolean | null;
  sora2_invite_code?: string | null;
  sora2_total_count?: number;
  sora2_redeemed_count?: number;
  sora2_remaining_count?: number;
  image_enabled: boolean;
  video_enabled: boolean;
  image_count: number;
  video_count: number;
  error_count: number;
  image_concurrency?: number;
  video_concurrency?: number;
  remark?: string | null;
}

export interface Stats {
  total_tokens: number;
  active_tokens: number;
  today_images: number;
  total_images: number;
  today_videos: number;
  total_videos: number;
  today_errors: number;
  total_errors: number;
}

export interface Log {
  id: number;
  operation: string;
  token_email?: string | null;
  status_code: number;
  duration: number;
  created_at: string;
}

export interface AdminConfig {
  admin_username: string;
  api_key: string;
  error_ban_threshold: number;
  debug_enabled: boolean;
}

export interface ProxyConfig {
  proxy_enabled: boolean;
  proxy_url: string;
}

export interface WatermarkFreeConfig {
  watermark_free_enabled: boolean;
  parse_method: 'third_party' | 'custom';
  custom_parse_url?: string | null;
  custom_parse_token?: string | null;
}

export interface CacheConfig {
  enabled: boolean;
  timeout: number;
  base_url: string;
  effective_base_url: string;
}

export interface GenerationTimeoutConfig {
  image_timeout: number;
  video_timeout: number;
}

export interface TokenRefreshConfig {
  at_auto_refresh_enabled: boolean;
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  message?: string;
  detail?: string;
  data?: T;
}

export interface LoginResponse {
  success: boolean;
  token?: string;
  message?: string;
}

export interface TokenTestResponse {
  success: boolean;
  status: string;
  email?: string;
  sora2_supported?: boolean;
  sora2_total_count?: number;
  sora2_redeemed_count?: number;
  sora2_remaining_count?: number;
  message?: string;
}

export interface ConvertResponse {
  success: boolean;
  access_token?: string;
  refresh_token?: string;
  message?: string;
  detail?: string;
}

export interface ImportResponse {
  success: boolean;
  added?: number;
  updated?: number;
  message?: string;
  detail?: string;
}

export interface Sora2ActivateResponse {
  success: boolean;
  already_accepted?: boolean;
  invite_code?: string;
  message?: string;
}

export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
}

export type TabType = 'tokens' | 'settings' | 'logs';
