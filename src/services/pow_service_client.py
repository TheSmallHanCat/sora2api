"""POW Service Client - External POW service integration"""
import json
from typing import Optional, Tuple
from curl_cffi.requests import AsyncSession

from ..core.config import config
from ..core.logger import debug_logger


class POWServiceClient:
    """Client for external POW service API"""

    async def get_sentinel_token(self) -> Optional[Tuple[str, str, str]]:
        """Get sentinel token from external POW service

        Returns:
            Tuple of (sentinel_token, device_id, user_agent) or None on failure
        """
        # Read configuration dynamically on each call
        server_url = config.pow_service_server_url
        api_key = config.pow_service_api_key
        proxy_enabled = config.pow_service_proxy_enabled
        proxy_url = config.pow_service_proxy_url if proxy_enabled else None

        if not server_url or not api_key:
            debug_logger.log_error(
                error_message="POW service not configured: missing server_url or api_key",
                status_code=0,
                response_text="Configuration error",
                source="POWServiceClient"
            )
            return None

        # Construct API endpoint
        api_url = f"{server_url.rstrip('/')}/api/pow/token"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

        try:
            debug_logger.log_info(f"[POW Service] Requesting token from {api_url}")

            async with AsyncSession(impersonate="chrome131") as session:
                response = await session.get(
                    api_url,
                    headers=headers,
                    proxy=proxy_url,
                    timeout=30
                )

                if response.status_code != 200:
                    error_msg = f"POW service request failed: {response.status_code}"
                    debug_logger.log_error(
                        error_message=error_msg,
                        status_code=response.status_code,
                        response_text=response.text,
                        source="POWServiceClient"
                    )
                    return None

                data = response.json()

                if not data.get("success"):
                    debug_logger.log_error(
                        error_message="POW service returned success=false",
                        status_code=response.status_code,
                        response_text=response.text,
                        source="POWServiceClient"
                    )
                    return None

                token = data.get("token")
                device_id = data.get("device_id")
                user_agent = data.get("user_agent")
                cached = data.get("cached", False)

                if not token:
                    debug_logger.log_error(
                        error_message="POW service returned empty token",
                        status_code=response.status_code,
                        response_text=response.text,
                        source="POWServiceClient"
                    )
                    return None

                # Parse token to extract device_id if not provided
                token_data = None
                if not device_id:
                    try:
                        token_data = json.loads(token)
                        device_id = token_data.get("id")
                    except:
                        pass

                # 记录详细的 token 信息
                cache_status = "cached" if cached else "fresh"
                debug_logger.log_info("=" * 100)
                debug_logger.log_info(f"[POW Service] Token obtained successfully ({cache_status})")
                debug_logger.log_info(f"[POW Service] Token length: {len(token)}")
                debug_logger.log_info(f"[POW Service] Device ID: {device_id}")
                debug_logger.log_info(f"[POW Service] User Agent: {user_agent}")

                # 解析并显示 token 结构
                if not token_data:
                    try:
                        token_data = json.loads(token)
                    except:
                        debug_logger.log_info(f"[POW Service] Token is not valid JSON")
                        token_data = None

                if token_data:
                    debug_logger.log_info(f"[POW Service] Token structure keys: {list(token_data.keys())}")
                    for key, value in token_data.items():
                        if isinstance(value, str) and len(value) > 100:
                            debug_logger.log_info(f"[POW Service] Token[{key}]: <string, length={len(value)}>")
                        else:
                            debug_logger.log_info(f"[POW Service] Token[{key}]: {value}")

                debug_logger.log_info("=" * 100)

                return token, device_id, user_agent

        except Exception as e:
            debug_logger.log_error(
                error_message=f"POW service request exception: {str(e)}",
                status_code=0,
                response_text=str(e),
                source="POWServiceClient"
            )
            return None


# Global instance
pow_service_client = POWServiceClient()
