"""Data models"""
from datetime import datetime
from typing import Optional, List, Union
from pydantic import BaseModel

class Token(BaseModel):
    """Token model"""
    id: Optional[int] = None
    token: str
    email: str
    name: Optional[str] = ""
    st: Optional[str] = None
    rt: Optional[str] = None
    client_id: Optional[str] = None
    remark: Optional[str] = None
    expiry_time: Optional[datetime] = None
    is_active: bool = True
    cooled_until: Optional[datetime] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    # Информация о подписке
    plan_type: Optional[str] = None  # Тип аккаунта, например chatgpt_team
    plan_title: Optional[str] = None  # Название тарифа, например ChatGPT Business
    subscription_end: Optional[datetime] = None  # Время истечения подписки
    # Информация о поддержке Sora2
    sora2_supported: Optional[bool] = None  # Поддерживается ли Sora2
    sora2_invite_code: Optional[str] = None  # Код приглашения Sora2
    sora2_redeemed_count: int = 0  # Количество использованных попыток Sora2
    sora2_total_count: int = 0  # Общее количество попыток Sora2
    # Оставшиеся попытки Sora2
    sora2_remaining_count: int = 0  # Количество оставшихся попыток Sora2
    sora2_cooldown_until: Optional[datetime] = None  # Время охлаждения Sora2
    # Переключатели функций
    image_enabled: bool = True  # Включена ли генерация изображений
    video_enabled: bool = True  # Включена ли генерация видео
    # Ограничение конкурентности
    image_concurrency: int = -1  # Ограничение конкурентности изображений, -1 = без ограничений
    video_concurrency: int = -1  # Ограничение конкурентности видео, -1 = без ограничений

class TokenStats(BaseModel):
    """Token statistics"""
    id: Optional[int] = None
    token_id: int
    image_count: int = 0
    video_count: int = 0
    error_count: int = 0  # Historical total errors (never reset)
    last_error_at: Optional[datetime] = None
    today_image_count: int = 0
    today_video_count: int = 0
    today_error_count: int = 0
    today_date: Optional[str] = None
    consecutive_error_count: int = 0  # Consecutive errors for auto-disable

class Task(BaseModel):
    """Task model"""
    id: Optional[int] = None
    task_id: str
    token_id: int
    model: str
    prompt: str
    status: str = "processing"  # processing/completed/failed
    progress: float = 0.0
    result_urls: Optional[str] = None  # JSON array
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class RequestLog(BaseModel):
    """Request log model"""
    id: Optional[int] = None
    token_id: Optional[int] = None
    operation: str
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    status_code: int
    duration: float
    created_at: Optional[datetime] = None

class AdminConfig(BaseModel):
    """Admin configuration"""
    id: int = 1
    admin_username: str  # Read from database, initialized from setting.toml on first startup
    admin_password: str  # Read from database, initialized from setting.toml on first startup
    error_ban_threshold: int = 3
    updated_at: Optional[datetime] = None

class ProxyConfig(BaseModel):
    """Proxy configuration"""
    id: int = 1
    proxy_enabled: bool  # Read from database, initialized from setting.toml on first startup
    proxy_url: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class WatermarkFreeConfig(BaseModel):
    """Watermark-free mode configuration"""
    id: int = 1
    watermark_free_enabled: bool  # Read from database, initialized from setting.toml on first startup
    parse_method: str  # Read from database, initialized from setting.toml on first startup
    custom_parse_url: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    custom_parse_token: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CacheConfig(BaseModel):
    """Cache configuration"""
    id: int = 1
    cache_enabled: bool  # Read from database, initialized from setting.toml on first startup
    cache_timeout: int  # Read from database, initialized from setting.toml on first startup
    cache_base_url: Optional[str] = None  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class GenerationConfig(BaseModel):
    """Generation timeout configuration"""
    id: int = 1
    image_timeout: int  # Read from database, initialized from setting.toml on first startup
    video_timeout: int  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TokenRefreshConfig(BaseModel):
    """Token refresh configuration"""
    id: int = 1
    at_auto_refresh_enabled: bool  # Read from database, initialized from setting.toml on first startup
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# API Request/Response models
class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[dict]]  # Support both string and array format (OpenAI multimodal)

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    image: Optional[str] = None
    video: Optional[str] = None  # Base64 encoded video file
    remix_target_id: Optional[str] = None  # Sora share link video ID for remix
    stream: bool = False
    max_tokens: Optional[int] = None

class ChatCompletionChoice(BaseModel):
    index: int
    message: Optional[dict] = None
    delta: Optional[dict] = None
    finish_reason: Optional[str] = None

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
