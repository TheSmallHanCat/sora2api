"""Admin routes - Management endpoints"""
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import secrets
from pydantic import BaseModel
from apscheduler.triggers.cron import CronTrigger
from ..core.auth import AuthManager
from ..core.config import config
from ..services.token_manager import TokenManager
from ..services.proxy_manager import ProxyManager
from ..services.concurrency_manager import ConcurrencyManager
from ..core.database import Database
from ..core.models import Token, AdminConfig, ProxyConfig

router = APIRouter()

# Dependency injection
token_manager: TokenManager = None
proxy_manager: ProxyManager = None
db: Database = None
generation_handler = None
concurrency_manager: ConcurrencyManager = None
scheduler = None

# Store active admin tokens (in production, use Redis or database)
active_admin_tokens = set()

def set_dependencies(tm: TokenManager, pm: ProxyManager, database: Database, gh=None, cm: ConcurrencyManager = None, sched=None):
    """Set dependencies"""
    global token_manager, proxy_manager, db, generation_handler, concurrency_manager, scheduler
    token_manager = tm
    proxy_manager = pm
    db = database
    generation_handler = gh
    concurrency_manager = cm
    scheduler = sched

def verify_admin_token(authorization: str = Header(None)):
    """Verify admin token from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # Support both "Bearer token" and "token" formats
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if token not in active_admin_tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return token

# Request/Response models
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: Optional[str] = None

class AddTokenRequest(BaseModel):
    token: str  # Access Token (AT)
    st: Optional[str] = None  # Session Token (optional, for storage)
    rt: Optional[str] = None  # Refresh Token (optional, for storage)
    client_id: Optional[str] = None  # Client ID (optional)
    proxy_url: Optional[str] = None  # Proxy URL (optional)
    remark: Optional[str] = None
    image_enabled: bool = True  # Enable image generation
    video_enabled: bool = True  # Enable video generation
    image_concurrency: int = 1  # Image concurrency limit (default: 1)
    video_concurrency: int = 3  # Video concurrency limit (default: 3)

class ST2ATRequest(BaseModel):
    st: str  # Session Token

class RT2ATRequest(BaseModel):
    rt: str  # Refresh Token
    client_id: Optional[str] = None  # Client ID (optional)

class UpdateTokenStatusRequest(BaseModel):
    is_active: bool

class UpdateTokenRequest(BaseModel):
    token: Optional[str] = None  # Access Token
    st: Optional[str] = None
    rt: Optional[str] = None
    client_id: Optional[str] = None  # Client ID
    proxy_url: Optional[str] = None  # Proxy URL
    remark: Optional[str] = None
    image_enabled: Optional[bool] = None  # Enable image generation
    video_enabled: Optional[bool] = None  # Enable video generation
    image_concurrency: Optional[int] = None  # Image concurrency limit
    video_concurrency: Optional[int] = None  # Video concurrency limit

class ImportTokenItem(BaseModel):
    email: str  # Email (primary key, required)
    access_token: Optional[str] = None  # Access Token (AT, optional for st/rt modes)
    session_token: Optional[str] = None  # Session Token (ST)
    refresh_token: Optional[str] = None  # Refresh Token (RT)
    client_id: Optional[str] = None  # Client ID (optional, for compatibility)
    proxy_url: Optional[str] = None  # Proxy URL (optional, for compatibility)
    remark: Optional[str] = None  # Remark (optional, for compatibility)
    is_active: bool = True  # Active status
    image_enabled: bool = True  # Enable image generation
    video_enabled: bool = True  # Enable video generation
    image_concurrency: int = -1  # Image concurrency limit
    video_concurrency: int = -1  # Video concurrency limit

class ImportTokensRequest(BaseModel):
    tokens: List[ImportTokenItem]
    mode: str = "at"  # Import mode: offline/at/st/rt

class UpdateAdminConfigRequest(BaseModel):
    error_ban_threshold: int

class UpdateProxyConfigRequest(BaseModel):
    proxy_enabled: bool
    proxy_url: Optional[str] = None

class UpdateAdminPasswordRequest(BaseModel):
    old_password: str
    new_password: str
    username: Optional[str] = None  # Optional: new username

class UpdateAPIKeyRequest(BaseModel):
    new_api_key: str

class UpdateDebugConfigRequest(BaseModel):
    enabled: bool

class UpdateCacheTimeoutRequest(BaseModel):
    timeout: int  # Cache timeout in seconds

class UpdateCacheBaseUrlRequest(BaseModel):
    base_url: str  # Cache base URL (e.g., https://yourdomain.com)

class UpdateGenerationTimeoutRequest(BaseModel):
    image_timeout: Optional[int] = None  # Image generation timeout in seconds
    video_timeout: Optional[int] = None  # Video generation timeout in seconds

class UpdateWatermarkFreeConfigRequest(BaseModel):
    watermark_free_enabled: bool
    parse_method: Optional[str] = "third_party"  # "third_party" or "custom"
    custom_parse_url: Optional[str] = None
    custom_parse_token: Optional[str] = None

class BatchDisableRequest(BaseModel):
    token_ids: List[int]

class BatchUpdateProxyRequest(BaseModel):
    token_ids: List[int]
    proxy_url: Optional[str] = None

# Auth endpoints
@router.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Admin login"""
    if AuthManager.verify_admin(request.username, request.password):
        # Generate simple token
        token = f"admin-{secrets.token_urlsafe(32)}"
        # Store token in active tokens
        active_admin_tokens.add(token)
        return LoginResponse(success=True, token=token, message="Login successful")
    else:
        return LoginResponse(success=False, message="Invalid credentials")

@router.post("/api/logout")
async def logout(token: str = Depends(verify_admin_token)):
    """Admin logout"""
    # Remove token from active tokens
    active_admin_tokens.discard(token)
    return {"success": True, "message": "Logged out successfully"}

# Token management endpoints
@router.get("/api/tokens")
async def get_tokens(token: str = Depends(verify_admin_token)) -> List[dict]:
    """Get all tokens with statistics"""
    tokens = await token_manager.get_all_tokens()
    result = []

    for token in tokens:
        stats = await db.get_token_stats(token.id)
        result.append({
            "id": token.id,
            "token": token.token,  # 完整的Access Token
            "st": token.st,  # 完整的Session Token
            "rt": token.rt,  # 完整的Refresh Token
            "client_id": token.client_id,  # Client ID
            "proxy_url": token.proxy_url,  # Proxy URL
            "email": token.email,
            "name": token.name,
            "remark": token.remark,
            "expiry_time": token.expiry_time.isoformat() if token.expiry_time else None,
            "is_active": token.is_active,
            "cooled_until": token.cooled_until.isoformat() if token.cooled_until else None,
            "created_at": token.created_at.isoformat() if token.created_at else None,
            "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
            "use_count": token.use_count,
            "image_count": stats.image_count if stats else 0,
            "video_count": stats.video_count if stats else 0,
            "error_count": stats.error_count if stats else 0,
            # 订阅信息
            "plan_type": token.plan_type,
            "plan_title": token.plan_title,
            "subscription_end": token.subscription_end.isoformat() if token.subscription_end else None,
            # Sora2信息
            "sora2_supported": token.sora2_supported,
            "sora2_invite_code": token.sora2_invite_code,
            "sora2_redeemed_count": token.sora2_redeemed_count,
            "sora2_total_count": token.sora2_total_count,
            "sora2_remaining_count": token.sora2_remaining_count,
            "sora2_cooldown_until": token.sora2_cooldown_until.isoformat() if token.sora2_cooldown_until else None,
            # 功能开关
            "image_enabled": token.image_enabled,
            "video_enabled": token.video_enabled,
            # 并发限制
            "image_concurrency": token.image_concurrency,
            "video_concurrency": token.video_concurrency
        })

    return result

@router.post("/api/tokens")
async def add_token(request: AddTokenRequest, token: str = Depends(verify_admin_token)):
    """Add a new Access Token"""
    try:
        new_token = await token_manager.add_token(
            token_value=request.token,
            st=request.st,
            rt=request.rt,
            client_id=request.client_id,
            proxy_url=request.proxy_url,
            remark=request.remark,
            update_if_exists=False,
            image_enabled=request.image_enabled,
            video_enabled=request.video_enabled,
            image_concurrency=request.image_concurrency,
            video_concurrency=request.video_concurrency
        )
        # Initialize concurrency counters for the new token
        if concurrency_manager:
            await concurrency_manager.reset_token(
                new_token.id,
                image_concurrency=request.image_concurrency,
                video_concurrency=request.video_concurrency
            )
        return {"success": True, "message": "Token 添加成功", "token_id": new_token.id}
    except ValueError as e:
        # Token already exists
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"添加 Token 失败: {str(e)}")

@router.post("/api/tokens/st2at")
async def st_to_at(request: ST2ATRequest, token: str = Depends(verify_admin_token)):
    """Convert Session Token to Access Token (only convert, not add to database)"""
    try:
        result = await token_manager.st_to_at(request.st)
        return {
            "success": True,
            "message": "ST converted to AT successfully",
            "access_token": result["access_token"],
            "email": result.get("email"),
            "expires": result.get("expires")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tokens/rt2at")
async def rt_to_at(request: RT2ATRequest, token: str = Depends(verify_admin_token)):
    """Convert Refresh Token to Access Token (only convert, not add to database)"""
    try:
        result = await token_manager.rt_to_at(request.rt, client_id=request.client_id)
        return {
            "success": True,
            "message": "RT converted to AT successfully",
            "access_token": result["access_token"],
            "refresh_token": result.get("refresh_token"),
            "expires_in": result.get("expires_in")
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/api/tokens/{token_id}/status")
async def update_token_status(
    token_id: int,
    request: UpdateTokenStatusRequest,
    token: str = Depends(verify_admin_token)
):
    """Update token status"""
    try:
        await token_manager.update_token_status(token_id, request.is_active)

        # Reset error count when enabling token
        if request.is_active:
            await token_manager.record_success(token_id)

        return {"success": True, "message": "Token status updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tokens/{token_id}/enable")
async def enable_token(token_id: int, token: str = Depends(verify_admin_token)):
    """Enable a token and reset error count"""
    try:
        await token_manager.enable_token(token_id)
        return {"success": True, "message": "Token enabled", "is_active": 1, "error_count": 0}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tokens/{token_id}/disable")
async def disable_token(token_id: int, token: str = Depends(verify_admin_token)):
    """Disable a token"""
    try:
        await token_manager.disable_token(token_id)
        return {"success": True, "message": "Token disabled", "is_active": 0}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tokens/{token_id}/test")
async def test_token(token_id: int, token: str = Depends(verify_admin_token)):
    """Test if a token is valid"""
    try:
        result = await token_manager.test_token(token_id)
        response = {
            "success": True,
            "status": "success" if result["valid"] else "failed",
            "message": result["message"],
            "email": result.get("email"),
            "username": result.get("username")
        }

        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/api/tokens/{token_id}")
async def delete_token(token_id: int, token: str = Depends(verify_admin_token)):
    """Delete a token"""
    try:
        await token_manager.delete_token(token_id)
        return {"success": True, "message": "Token deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/tokens/batch/test-update")
async def batch_test_update(request: BatchDisableRequest = None, token: str = Depends(verify_admin_token)):
    """Test and update selected tokens or all tokens by fetching their status from upstream"""
    try:
        if request and request.token_ids:
            # Test only selected tokens
            tokens = []
            for token_id in request.token_ids:
                token_obj = await db.get_token(token_id)
                if token_obj:
                    tokens.append(token_obj)
        else:
            # Test all tokens (backward compatibility)
            tokens = await db.get_all_tokens()

        success_count = 0
        failed_count = 0
        results = []

        for token_obj in tokens:
            try:
                # Test token and update account info (same as single test)
                result = await token_manager.test_token(token_obj.id)
                if result.get("valid"):
                    success_count += 1
                    results.append({"id": token_obj.id, "email": token_obj.email, "status": "success"})
                else:
                    failed_count += 1
                    results.append({"id": token_obj.id, "email": token_obj.email, "status": "failed", "message": result.get("message")})
            except Exception as e:
                failed_count += 1
                results.append({"id": token_obj.id, "email": token_obj.email, "status": "error", "message": str(e)})

        return {
            "success": True,
            "message": f"测试完成：成功 {success_count} 个，失败 {failed_count} 个",
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tokens/batch/enable-all")
async def batch_enable_all(request: BatchDisableRequest = None, token: str = Depends(verify_admin_token)):
    """Enable selected tokens or all disabled tokens"""
    try:
        if request and request.token_ids:
            # Enable only selected tokens
            enabled_count = 0
            for token_id in request.token_ids:
                await token_manager.enable_token(token_id)
                enabled_count += 1
        else:
            # Enable all disabled tokens (backward compatibility)
            tokens = await db.get_all_tokens()
            enabled_count = 0
            for token_obj in tokens:
                if not token_obj.is_active:
                    await token_manager.enable_token(token_obj.id)
                    enabled_count += 1

        return {
            "success": True,
            "message": f"已启用 {enabled_count} 个Token",
            "enabled_count": enabled_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tokens/batch/delete-disabled")
async def batch_delete_disabled(request: BatchDisableRequest = None, token: str = Depends(verify_admin_token)):
    """Delete selected tokens or all disabled tokens"""
    try:
        if request and request.token_ids:
            # Delete only selected tokens
            deleted_count = 0
            for token_id in request.token_ids:
                await token_manager.delete_token(token_id)
                deleted_count += 1
        else:
            # Delete all disabled tokens (backward compatibility)
            tokens = await db.get_all_tokens()
            deleted_count = 0
            for token_obj in tokens:
                if not token_obj.is_active:
                    await token_manager.delete_token(token_obj.id)
                    deleted_count += 1

        return {
            "success": True,
            "message": f"已删除 {deleted_count} 个Token",
            "deleted_count": deleted_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tokens/batch/disable-selected")
async def batch_disable_selected(request: BatchDisableRequest, token: str = Depends(verify_admin_token)):
    """Disable selected tokens"""
    try:
        disabled_count = 0
        for token_id in request.token_ids:
            await token_manager.disable_token(token_id)
            disabled_count += 1

        return {
            "success": True,
            "message": f"已禁用 {disabled_count} 个Token",
            "disabled_count": disabled_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tokens/batch/update-proxy")
async def batch_update_proxy(request: BatchUpdateProxyRequest, token: str = Depends(verify_admin_token)):
    """Batch update proxy for selected tokens"""
    try:
        updated_count = 0
        for token_id in request.token_ids:
            await token_manager.update_token(
                token_id=token_id,
                proxy_url=request.proxy_url
            )
            updated_count += 1

        return {
            "success": True,
            "message": f"已更新 {updated_count} 个Token的代理",
            "updated_count": updated_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tokens/import")
async def import_tokens(request: ImportTokensRequest, token: str = Depends(verify_admin_token)):
    """Import tokens with different modes: offline/at/st/rt"""
    mode = request.mode  # offline/at/st/rt
    added_count = 0
    updated_count = 0
    failed_count = 0
    results = []

    for import_item in request.tokens:
        try:
            # Step 1: Get or convert access_token based on mode
            access_token = None
            skip_status = False

            if mode == "offline":
                # Offline mode: use provided AT, skip status update
                if not import_item.access_token:
                    raise ValueError("离线导入模式需要提供 access_token")
                access_token = import_item.access_token
                skip_status = True

            elif mode == "at":
                # AT mode: use provided AT, update status (current logic)
                if not import_item.access_token:
                    raise ValueError("AT导入模式需要提供 access_token")
                access_token = import_item.access_token
                skip_status = False

            elif mode == "st":
                # ST mode: convert ST to AT, update status
                if not import_item.session_token:
                    raise ValueError("ST导入模式需要提供 session_token")
                # Convert ST to AT
                st_result = await token_manager.st_to_at(
                    import_item.session_token,
                    proxy_url=import_item.proxy_url
                )
                access_token = st_result["access_token"]
                # Update email if API returned it
                if "email" in st_result and st_result["email"]:
                    import_item.email = st_result["email"]
                skip_status = False

            elif mode == "rt":
                # RT mode: convert RT to AT, update status
                if not import_item.refresh_token:
                    raise ValueError("RT导入模式需要提供 refresh_token")
                # Convert RT to AT
                rt_result = await token_manager.rt_to_at(
                    import_item.refresh_token,
                    client_id=import_item.client_id,
                    proxy_url=import_item.proxy_url
                )
                access_token = rt_result["access_token"]
                # Update RT if API returned new one
                if "refresh_token" in rt_result and rt_result["refresh_token"]:
                    import_item.refresh_token = rt_result["refresh_token"]
                # Update email if API returned it
                if "email" in rt_result and rt_result["email"]:
                    import_item.email = rt_result["email"]
                skip_status = False
            else:
                raise ValueError(f"不支持的导入模式: {mode}")

            # Step 2: Check if token with this email already exists
            existing_token = await db.get_token_by_email(import_item.email)

            if existing_token:
                # Update existing token
                await token_manager.update_token(
                    token_id=existing_token.id,
                    token=access_token,
                    st=import_item.session_token,
                    rt=import_item.refresh_token,
                    client_id=import_item.client_id,
                    proxy_url=import_item.proxy_url,
                    remark=import_item.remark,
                    image_enabled=import_item.image_enabled,
                    video_enabled=import_item.video_enabled,
                    image_concurrency=import_item.image_concurrency,
                    video_concurrency=import_item.video_concurrency,
                    skip_status_update=skip_status
                )
                # Update active status
                await token_manager.update_token_status(existing_token.id, import_item.is_active)
                # Reset concurrency counters
                if concurrency_manager:
                    await concurrency_manager.reset_token(
                        existing_token.id,
                        image_concurrency=import_item.image_concurrency,
                        video_concurrency=import_item.video_concurrency
                    )
                updated_count += 1
                results.append({
                    "email": import_item.email,
                    "status": "updated",
                    "success": True
                })
            else:
                # Add new token
                new_token = await token_manager.add_token(
                    token_value=access_token,
                    st=import_item.session_token,
                    rt=import_item.refresh_token,
                    client_id=import_item.client_id,
                    proxy_url=import_item.proxy_url,
                    remark=import_item.remark,
                    update_if_exists=False,
                    image_enabled=import_item.image_enabled,
                    video_enabled=import_item.video_enabled,
                    image_concurrency=import_item.image_concurrency,
                    video_concurrency=import_item.video_concurrency,
                    skip_status_update=skip_status,
                    email=import_item.email  # Pass email for offline mode
                )
                # Set active status
                if not import_item.is_active:
                    await token_manager.disable_token(new_token.id)
                # Initialize concurrency counters
                if concurrency_manager:
                    await concurrency_manager.reset_token(
                        new_token.id,
                        image_concurrency=import_item.image_concurrency,
                        video_concurrency=import_item.video_concurrency
                    )
                added_count += 1
                results.append({
                    "email": import_item.email,
                    "status": "added",
                    "success": True
                })
        except Exception as e:
            failed_count += 1
            results.append({
                "email": import_item.email,
                "status": "failed",
                "success": False,
                "error": str(e)
            })

    return {
        "success": True,
        "message": f"Import completed ({mode} mode): {added_count} added, {updated_count} updated, {failed_count} failed",
        "added": added_count,
        "updated": updated_count,
        "failed": failed_count,
        "results": results
    }

@router.put("/api/tokens/{token_id}")
async def update_token(
    token_id: int,
    request: UpdateTokenRequest,
    token: str = Depends(verify_admin_token)
):
    """Update token (AT, ST, RT, proxy_url, remark, image_enabled, video_enabled, concurrency limits)"""
    try:
        await token_manager.update_token(
            token_id=token_id,
            token=request.token,
            st=request.st,
            rt=request.rt,
            client_id=request.client_id,
            proxy_url=request.proxy_url,
            remark=request.remark,
            image_enabled=request.image_enabled,
            video_enabled=request.video_enabled,
            image_concurrency=request.image_concurrency,
            video_concurrency=request.video_concurrency
        )
        # Reset concurrency counters if they were updated
        if concurrency_manager and (request.image_concurrency is not None or request.video_concurrency is not None):
            await concurrency_manager.reset_token(
                token_id,
                image_concurrency=request.image_concurrency if request.image_concurrency is not None else -1,
                video_concurrency=request.video_concurrency if request.video_concurrency is not None else -1
            )
        return {"success": True, "message": "Token updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Admin config endpoints
@router.get("/api/admin/config")
async def get_admin_config(token: str = Depends(verify_admin_token)) -> dict:
    """Get admin configuration"""
    admin_config = await db.get_admin_config()
    return {
        "error_ban_threshold": admin_config.error_ban_threshold,
        "api_key": config.api_key,
        "admin_username": config.admin_username,
        "debug_enabled": config.debug_enabled
    }

@router.post("/api/admin/config")
async def update_admin_config(
    request: UpdateAdminConfigRequest,
    token: str = Depends(verify_admin_token)
):
    """Update admin configuration"""
    try:
        # Get current admin config to preserve username and password
        current_config = await db.get_admin_config()

        # Update only the error_ban_threshold, preserve username and password
        current_config.error_ban_threshold = request.error_ban_threshold

        await db.update_admin_config(current_config)
        return {"success": True, "message": "Configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/admin/password")
async def update_admin_password(
    request: UpdateAdminPasswordRequest,
    token: str = Depends(verify_admin_token)
):
    """Update admin password and/or username"""
    try:
        # Verify old password
        if not AuthManager.verify_admin(config.admin_username, request.old_password):
            raise HTTPException(status_code=400, detail="Old password is incorrect")

        # Get current admin config from database
        admin_config = await db.get_admin_config()

        # Update password in database
        admin_config.admin_password = request.new_password

        # Update username if provided
        if request.username:
            admin_config.admin_username = request.username

        # Update in database
        await db.update_admin_config(admin_config)

        # Update in-memory config
        config.set_admin_password_from_db(request.new_password)
        if request.username:
            config.set_admin_username_from_db(request.username)

        # Invalidate all admin tokens (force re-login)
        active_admin_tokens.clear()

        return {"success": True, "message": "Password updated successfully. Please login again."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update password: {str(e)}")

@router.post("/api/admin/apikey")
async def update_api_key(
    request: UpdateAPIKeyRequest,
    token: str = Depends(verify_admin_token)
):
    """Update API key"""
    try:
        # Get current admin config from database
        admin_config = await db.get_admin_config()

        # Update api_key in database
        admin_config.api_key = request.new_api_key
        await db.update_admin_config(admin_config)

        # Update in-memory config
        config.api_key = request.new_api_key

        return {"success": True, "message": "API key updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update API key: {str(e)}")

@router.post("/api/admin/debug")
async def update_debug_config(
    request: UpdateDebugConfigRequest,
    token: str = Depends(verify_admin_token)
):
    """Update debug configuration"""
    try:
        # Update in-memory config
        config.set_debug_enabled(request.enabled)

        status = "enabled" if request.enabled else "disabled"
        return {"success": True, "message": f"Debug mode {status}", "enabled": request.enabled}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update debug config: {str(e)}")

# Proxy config endpoints
@router.get("/api/proxy/config")
async def get_proxy_config(token: str = Depends(verify_admin_token)) -> dict:
    """Get proxy configuration"""
    config = await proxy_manager.get_proxy_config()
    return {
        "proxy_enabled": config.proxy_enabled,
        "proxy_url": config.proxy_url
    }

@router.post("/api/proxy/config")
async def update_proxy_config(
    request: UpdateProxyConfigRequest,
    token: str = Depends(verify_admin_token)
):
    """Update proxy configuration"""
    try:
        await proxy_manager.update_proxy_config(request.proxy_enabled, request.proxy_url)
        return {"success": True, "message": "Proxy configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Watermark-free config endpoints
@router.get("/api/watermark-free/config")
async def get_watermark_free_config(token: str = Depends(verify_admin_token)) -> dict:
    """Get watermark-free mode configuration"""
    config_obj = await db.get_watermark_free_config()
    return {
        "watermark_free_enabled": config_obj.watermark_free_enabled,
        "parse_method": config_obj.parse_method,
        "custom_parse_url": config_obj.custom_parse_url,
        "custom_parse_token": config_obj.custom_parse_token
    }

@router.post("/api/watermark-free/config")
async def update_watermark_free_config(
    request: UpdateWatermarkFreeConfigRequest,
    token: str = Depends(verify_admin_token)
):
    """Update watermark-free mode configuration"""
    try:
        await db.update_watermark_free_config(
            request.watermark_free_enabled,
            request.parse_method,
            request.custom_parse_url,
            request.custom_parse_token
        )

        # Update in-memory config
        from ..core.config import config
        config.set_watermark_free_enabled(request.watermark_free_enabled)

        return {"success": True, "message": "Watermark-free mode configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Statistics endpoints
@router.get("/api/stats")
async def get_stats(token: str = Depends(verify_admin_token)):
    """Get system statistics"""
    tokens = await token_manager.get_all_tokens()
    active_tokens = await token_manager.get_active_tokens()

    total_images = 0
    total_videos = 0
    total_errors = 0
    today_images = 0
    today_videos = 0
    today_errors = 0

    for token in tokens:
        stats = await db.get_token_stats(token.id)
        if stats:
            total_images += stats.image_count
            total_videos += stats.video_count
            total_errors += stats.error_count
            today_images += stats.today_image_count
            today_videos += stats.today_video_count
            today_errors += stats.today_error_count

    return {
        "total_tokens": len(tokens),
        "active_tokens": len(active_tokens),
        "total_images": total_images,
        "total_videos": total_videos,
        "today_images": today_images,
        "today_videos": today_videos,
        "total_errors": total_errors,
        "today_errors": today_errors
    }

# Logs endpoints
@router.get("/api/logs")
async def get_logs(limit: int = 100, token: str = Depends(verify_admin_token)):
    """Get recent logs with token email and task progress"""
    logs = await db.get_recent_logs(limit)
    result = []
    for log in logs:
        log_data = {
            "id": log.get("id"),
            "token_id": log.get("token_id"),
            "token_email": log.get("token_email"),
            "token_username": log.get("token_username"),
            "operation": log.get("operation"),
            "status_code": log.get("status_code"),
            "duration": log.get("duration"),
            "created_at": log.get("created_at"),
            "request_body": log.get("request_body"),
            "response_body": log.get("response_body"),
            "task_id": log.get("task_id")
        }

        # If task_id exists and status is in-progress, get task progress
        if log.get("task_id") and log.get("status_code") == -1:
            task = await db.get_task(log.get("task_id"))
            if task:
                log_data["progress"] = task.progress
                log_data["task_status"] = task.status

        result.append(log_data)

    return result

@router.delete("/api/logs")
async def clear_logs(token: str = Depends(verify_admin_token)):
    """Clear all logs"""
    try:
        await db.clear_all_logs()
        return {"success": True, "message": "所有日志已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Cache config endpoints
@router.post("/api/cache/config")
async def update_cache_timeout(
    request: UpdateCacheTimeoutRequest,
    token: str = Depends(verify_admin_token)
):
    """Update cache timeout"""
    try:
        # Allow -1 for never delete, otherwise must be between 60-86400
        if request.timeout != -1:
            if request.timeout < 60:
                raise HTTPException(status_code=400, detail="Cache timeout must be at least 60 seconds or -1 for never delete")

            if request.timeout > 86400:
                raise HTTPException(status_code=400, detail="Cache timeout cannot exceed 24 hours (86400 seconds)")

        # Update in-memory config
        config.set_cache_timeout(request.timeout)

        # Update database
        await db.update_cache_config(timeout=request.timeout)

        # Update file cache timeout
        if generation_handler:
            generation_handler.file_cache.set_timeout(request.timeout)

        timeout_msg = "never delete" if request.timeout == -1 else f"{request.timeout} seconds"
        return {
            "success": True,
            "message": f"Cache timeout updated to {timeout_msg}",
            "timeout": request.timeout
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cache timeout: {str(e)}")

@router.post("/api/cache/base-url")
async def update_cache_base_url(
    request: UpdateCacheBaseUrlRequest,
    token: str = Depends(verify_admin_token)
):
    """Update cache base URL"""
    try:
        # Validate base URL format (optional, can be empty)
        base_url = request.base_url.strip()
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise HTTPException(
                status_code=400,
                detail="Base URL must start with http:// or https://"
            )

        # Remove trailing slash
        if base_url:
            base_url = base_url.rstrip('/')

        # Update in-memory config
        config.set_cache_base_url(base_url)

        # Update database
        await db.update_cache_config(base_url=base_url)

        return {
            "success": True,
            "message": f"Cache base URL updated to: {base_url or 'server address'}",
            "base_url": base_url
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cache base URL: {str(e)}")

@router.get("/api/cache/config")
async def get_cache_config(token: str = Depends(verify_admin_token)):
    """Get cache configuration"""
    return {
        "success": True,
        "config": {
            "enabled": config.cache_enabled,
            "timeout": config.cache_timeout,
            "base_url": config.cache_base_url,  # 返回实际配置的值，可能为空字符串
            "effective_base_url": config.cache_base_url or f"http://{config.server_host}:{config.server_port}"  # 实际生效的值
        }
    }

@router.post("/api/cache/enabled")
async def update_cache_enabled(
    request: dict,
    token: str = Depends(verify_admin_token)
):
    """Update cache enabled status"""
    try:
        enabled = request.get("enabled", True)

        # Update in-memory config
        config.set_cache_enabled(enabled)

        # Update database
        await db.update_cache_config(enabled=enabled)

        return {
            "success": True,
            "message": f"Cache {'enabled' if enabled else 'disabled'} successfully",
            "enabled": enabled
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cache enabled status: {str(e)}")

# Generation timeout config endpoints
@router.get("/api/generation/timeout")
async def get_generation_timeout(token: str = Depends(verify_admin_token)):
    """Get generation timeout configuration"""
    return {
        "success": True,
        "config": {
            "image_timeout": config.image_timeout,
            "video_timeout": config.video_timeout
        }
    }

@router.post("/api/generation/timeout")
async def update_generation_timeout(
    request: UpdateGenerationTimeoutRequest,
    token: str = Depends(verify_admin_token)
):
    """Update generation timeout configuration"""
    try:
        # Validate timeouts
        if request.image_timeout is not None:
            if request.image_timeout < 60:
                raise HTTPException(status_code=400, detail="Image timeout must be at least 60 seconds")
            if request.image_timeout > 3600:
                raise HTTPException(status_code=400, detail="Image timeout cannot exceed 1 hour (3600 seconds)")

        if request.video_timeout is not None:
            if request.video_timeout < 60:
                raise HTTPException(status_code=400, detail="Video timeout must be at least 60 seconds")
            if request.video_timeout > 7200:
                raise HTTPException(status_code=400, detail="Video timeout cannot exceed 2 hours (7200 seconds)")

        # Update in-memory config
        if request.image_timeout is not None:
            config.set_image_timeout(request.image_timeout)
        if request.video_timeout is not None:
            config.set_video_timeout(request.video_timeout)

        # Update database
        await db.update_generation_config(
            image_timeout=request.image_timeout,
            video_timeout=request.video_timeout
        )

        # Update TokenLock timeout if image timeout was changed
        if request.image_timeout is not None and generation_handler:
            generation_handler.load_balancer.token_lock.set_lock_timeout(config.image_timeout)

        return {
            "success": True,
            "message": "Generation timeout configuration updated",
            "config": {
                "image_timeout": config.image_timeout,
                "video_timeout": config.video_timeout
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update generation timeout: {str(e)}")

# AT auto refresh config endpoints
@router.get("/api/token-refresh/config")
async def get_at_auto_refresh_config(token: str = Depends(verify_admin_token)):
    """Get AT auto refresh configuration"""
    return {
        "success": True,
        "config": {
            "at_auto_refresh_enabled": config.at_auto_refresh_enabled
        }
    }

@router.post("/api/token-refresh/enabled")
async def update_at_auto_refresh_enabled(
    request: dict,
    token: str = Depends(verify_admin_token)
):
    """Update AT auto refresh enabled status"""
    try:
        enabled = request.get("enabled", False)

        # Update in-memory config
        config.set_at_auto_refresh_enabled(enabled)

        # Update database
        await db.update_token_refresh_config(enabled)

        # Dynamically start or stop scheduler
        if scheduler:
            if enabled:
                # Start scheduler if not already running
                if not scheduler.running:
                    scheduler.add_job(
                        token_manager.batch_refresh_all_tokens,
                        CronTrigger(hour=0, minute=0),
                        id='batch_refresh_tokens',
                        name='Batch refresh all tokens',
                        replace_existing=True
                    )
                    scheduler.start()
            else:
                # Stop scheduler if running
                if scheduler.running:
                    scheduler.remove_job('batch_refresh_tokens')

        return {
            "success": True,
            "message": f"AT auto refresh {'enabled' if enabled else 'disabled'} successfully",
            "enabled": enabled
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update AT auto refresh enabled status: {str(e)}")

# Task management endpoints
@router.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, token: str = Depends(verify_admin_token)):
    """Cancel a running task"""
    try:
        # Get task from database
        task = await db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # Check if task is still processing
        if task.status not in ["processing"]:
            return {"success": False, "message": f"任务状态为 {task.status},无法取消"}

        # Update task status to failed
        await db.update_task(task_id, "failed", 0, error_message="用户手动取消任务")

        # Update request log if exists
        logs = await db.get_recent_logs(limit=1000)
        for log in logs:
            if log.get("task_id") == task_id and log.get("status_code") == -1:
                import time
                duration = time.time() - (log.get("created_at").timestamp() if log.get("created_at") else time.time())
                await db.update_request_log(
                    log.get("id"),
                    response_body='{"error": "用户手动取消任务"}',
                    status_code=499,
                    duration=duration
                )
                break

        return {"success": True, "message": "任务已取消"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")

# Debug logs download endpoint
@router.get("/api/admin/logs/download")
async def download_debug_logs(token: str = Depends(verify_admin_token)):
    """Download debug logs file (logs.txt)"""
    log_file = Path("logs.txt")

    if not log_file.exists():
        raise HTTPException(status_code=404, detail="日志文件不存在")

    return FileResponse(
        path=str(log_file),
        filename="logs.txt",
        media_type="text/plain"
    )
