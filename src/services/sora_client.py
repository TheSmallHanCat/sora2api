"""Sora API client module"""
import asyncio
import base64
import hashlib
import json
import io
import time
import random
import string
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from uuid import uuid4
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
from curl_cffi.requests import AsyncSession
from curl_cffi import CurlMime
from .proxy_manager import ProxyManager
from .pow_service_client import pow_service_client
from ..core.config import config
from ..core.logger import debug_logger

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Global browser instance for reuse (lightweight Playwright approach)
_browser = None
_playwright = None
_current_proxy = None

# Sentinel token cache
_cached_sentinel_token = None
_cached_device_id = None


async def _get_browser(proxy_url: str = None):
    """Get or create browser instance (reuses existing browser)"""
    global _browser, _playwright, _current_proxy
    
    # If proxy changed, restart browser
    if _browser is not None and _current_proxy != proxy_url:
        await _browser.close()
        _browser = None
    
    if _browser is None:
        _playwright = await async_playwright().start()
        launch_args = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--disable-background-networking',
                '--disable-software-rasterizer',
            ]
        }
        if proxy_url:
            launch_args['proxy'] = {'server': proxy_url}
        _browser = await _playwright.chromium.launch(**launch_args)
        _current_proxy = proxy_url
    return _browser


async def _close_browser():
    """Close browser instance"""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None


async def _fetch_oai_did(proxy_url: str = None, max_retries: int = 3) -> str:
    """Fetch oai-did using curl_cffi (lightweight approach)
    
    Raises:
        Exception: If 403 or 429 response received
    """
    debug_logger.log_info(f"[Sentinel] Fetching oai-did...")
    
    for attempt in range(max_retries):
        try:
            async with AsyncSession(impersonate="chrome120") as session:
                response = await session.get(
                    "https://chatgpt.com/",
                    proxy=proxy_url,
                    timeout=30,
                    allow_redirects=True
                )
                
                # Check for 403/429 errors - don't retry, just fail
                if response.status_code == 403:
                    raise Exception("403 Forbidden - Access denied when fetching oai-did")
                if response.status_code == 429:
                    raise Exception("429 Too Many Requests - Rate limited when fetching oai-did")
                
                oai_did = response.cookies.get("oai-did")
                if oai_did:
                    debug_logger.log_info(f"[Sentinel] oai-did: {oai_did}")
                    return oai_did
                
                set_cookie = response.headers.get("set-cookie", "")
                match = re.search(r'oai-did=([a-f0-9-]{36})', set_cookie)
                if match:
                    oai_did = match.group(1)
                    debug_logger.log_info(f"[Sentinel] oai-did: {oai_did}")
                    return oai_did
                    
        except Exception as e:
            error_str = str(e)
            # Re-raise 403/429 errors immediately
            if "403" in error_str or "429" in error_str:
                raise
            debug_logger.log_info(f"[Sentinel] oai-did fetch failed: {e}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(2)
    
    return None


async def _generate_sentinel_token_lightweight(proxy_url: str = None, device_id: str = None) -> str:
    """Generate sentinel token using lightweight Playwright approach
    
    Uses route interception and SDK injection for minimal resource usage.
    Reuses browser instance across calls.
    
    Args:
        proxy_url: Optional proxy URL
        device_id: Optional pre-fetched oai-did
        
    Returns:
        Sentinel token string or None on failure
        
    Raises:
        Exception: If 403/429 when fetching oai-did
    """
    global _cached_device_id
    
    if not PLAYWRIGHT_AVAILABLE:
        debug_logger.log_info("[Sentinel] Playwright not available")
        return None
    
    # Get oai-did
    if not device_id:
        device_id = await _fetch_oai_did(proxy_url)
    
    if not device_id:
        debug_logger.log_info("[Sentinel] Failed to get oai-did")
        return None
    
    _cached_device_id = device_id
    
    debug_logger.log_info(f"[Sentinel] Starting browser...")
    browser = await _get_browser(proxy_url)
    
    context = await browser.new_context(
        viewport={'width': 800, 'height': 600},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        bypass_csp=True
    )
    
    # Set cookie
    await context.add_cookies([{
        'name': 'oai-did',
        'value': device_id,
        'domain': 'sora.chatgpt.com',
        'path': '/'
    }])
    
    page = await context.new_page()
    
    # Route interception - inject SDK
    inject_html = '''<!DOCTYPE html><html><head><script src="https://chatgpt.com/backend-api/sentinel/sdk.js"></script></head><body></body></html>'''
    
    async def handle_route(route):
        url = route.request.url
        if "__sentinel__" in url:
            await route.fulfill(status=200, content_type="text/html", body=inject_html)
        elif "/sentinel/" in url or "chatgpt.com" in url:
            await route.continue_()
        else:
            await route.abort()
    
    await page.route("**/*", handle_route)
    
    debug_logger.log_info(f"[Sentinel] Loading SDK...")
    
    try:
        # Load SDK via hack (must be under sora.chatgpt.com domain)
        await page.goto("https://sora.chatgpt.com/__sentinel__", wait_until="load", timeout=30000)
        
        # Wait for SDK to load
        await page.wait_for_function("typeof SentinelSDK !== 'undefined' && typeof SentinelSDK.token === 'function'", timeout=15000)
        
        debug_logger.log_info(f"[Sentinel] Getting token...")
        
        # Call SDK
        token = await page.evaluate(f'''
            async () => {{
                try {{
                    return await SentinelSDK.token('sora_2_create_task', '{device_id}');
                }} catch (e) {{
                    return 'ERROR: ' + e.message;
                }}
            }}
        ''')
        
        if token and not token.startswith('ERROR'):
            debug_logger.log_info(f"[Sentinel] Token obtained successfully")
            return token
        else:
            debug_logger.log_info(f"[Sentinel] Token error: {token}")
            return None
            
    except Exception as e:
        debug_logger.log_info(f"[Sentinel] Error: {e}")
        return None
    finally:
        await context.close()


async def _get_cached_sentinel_token(proxy_url: str = None, force_refresh: bool = False) -> str:
    """Get sentinel token with caching support

    Args:
        proxy_url: Optional proxy URL
        force_refresh: Force refresh token (e.g., after 400 error)

    Returns:
        Sentinel token string or None

    Raises:
        Exception: If 403/429 when fetching oai-did
    """
    global _cached_sentinel_token

    # Check if external POW service is configured
    if config.pow_service_mode == "external":
        debug_logger.log_info("[POW] Using external POW service (cached sentinel)")
        from .pow_service_client import pow_service_client
        result = await pow_service_client.get_sentinel_token()

        if result:
            sentinel_token, device_id, service_user_agent = result
            debug_logger.log_info("[POW] External service returned sentinel token successfully")
            return sentinel_token
        else:
            # Fallback to local mode if external service fails
            debug_logger.log_info("[POW] External service failed, falling back to local mode")

    # Local mode (original logic)
    # Return cached token if available and not forcing refresh
    if _cached_sentinel_token and not force_refresh:
        debug_logger.log_info("[Sentinel] Using cached token")
        return _cached_sentinel_token

    # Generate new token
    debug_logger.log_info("[Sentinel] Generating new token...")
    token = await _generate_sentinel_token_lightweight(proxy_url)

    if token:
        _cached_sentinel_token = token
        debug_logger.log_info("[Sentinel] Token cached successfully")

    return token


def _invalidate_sentinel_cache():
    """Invalidate cached sentinel token (call after 400 error)"""
    global _cached_sentinel_token
    _cached_sentinel_token = None
    debug_logger.log_info("[Sentinel] Cache invalidated")


# PoW related constants
POW_MAX_ITERATION = 500000
POW_CORES = [4, 8, 12, 16, 24, 32]

POW_SCREEN_SIZES = [1266, 1536, 1920, 2560, 3000, 3072, 3120, 3840]
POW_SCRIPTS = [
    "https://sora-cdn.oaistatic.com/_next/static/chunks/polyfills-42372ed130431b0a.js",
    "https://sora-cdn.oaistatic.com/_next/static/chunks/6974-eaafbe7db9c73c96.js",
    "https://sora-cdn.oaistatic.com/_next/static/chunks/main-app-5f0c58611778fb36.js",
    "https://chatgpt.com/backend-api/sentinel/sdk.js",
]
POW_NAVIGATOR_KEYS = [
    "mimeTypes−[object MimeTypeArray]",
    "userAgentData−[object NavigatorUAData]",
    "scheduling−[object Scheduling]",
    "keyboard−[object Keyboard]",
    "webkitPersistentStorage−[object DeprecatedStorageQuota]",
    "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
    "storage−[object StorageManager]",
    "locks−[object LockManager]",
    "appCodeName−Mozilla",
    "permissions−[object Permissions]",
    "webdriver−false",
    "vendor−Google Inc.",
    "mediaDevices−[object MediaDevices]",
    "cookieEnabled−true",
    "product−Gecko",
    "productSub−20030107",
    "hardwareConcurrency−32",
    "onLine−true",
]
POW_DOCUMENT_KEYS = [
    "__reactContainer$3k0e9yog4o3",
    "__reactContainer$ft149nhgior",
    "__reactResources$9nnifsagitb",
    "_reactListeningou2wvttp2d9",
    "_reactListeningu9qurgpwsme",
    "_reactListeningo743lnnpvdg",
    "location",
    "body",
]
POW_WINDOW_KEYS = [
    "getSelection",
    "btoa",
    "__next_s",
    "crossOriginIsolated",
    "print",
    "0", "window", "self", "document", "name", "location",
    "navigator", "screen", "innerWidth", "innerHeight",
    "localStorage", "sessionStorage", "crypto", "performance",
]
POW_LANGUAGES = [
    ("zh-CN", "zh-CN,zh"),
    ("en-US", "en-US,en"),
    ("ja-JP", "ja-JP,ja,en"),
    ("ko-KR", "ko-KR,ko,en"),
]

# User-Agent pools
DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

MOBILE_USER_AGENTS = [
    "Sora/1.2026.007 (Android 15; 24122RKC7C; build 2600700)",
    "Sora/1.2026.007 (Android 14; SM-G998B; build 2600700)",
    "Sora/1.2026.007 (Android 15; Pixel 8 Pro; build 2600700)",
    "Sora/1.2026.007 (Android 14; Pixel 7; build 2600700)",
    "Sora/1.2026.007 (Android 15; 2211133C; build 2600700)",
    "Sora/1.2026.007 (Android 14; SM-S918B; build 2600700)",
    "Sora/1.2026.007 (Android 15; OnePlus 12; build 2600700)",
]

class SoraClient:
    """Sora API client with proxy support"""

    CHATGPT_BASE_URL = "https://chatgpt.com"
    SENTINEL_FLOW = "sora_2_create_task__auto"

    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.base_url = config.sora_base_url
        self.timeout = config.sora_timeout

    @staticmethod
    def _get_pow_parse_time() -> str:
        """Generate time string for PoW (local timezone)"""
        now = datetime.now()
        
        # Get local timezone offset (seconds)
        if time.daylight and time.localtime().tm_isdst > 0:
            utc_offset_seconds = -time.altzone
        else:
            utc_offset_seconds = -time.timezone
        
        # Format as +0800 or -0500
        offset_hours = utc_offset_seconds // 3600
        offset_minutes = abs(utc_offset_seconds % 3600) // 60
        offset_sign = '+' if offset_hours >= 0 else '-'
        offset_str = f"{offset_sign}{abs(offset_hours):02d}{offset_minutes:02d}"
        
        # Get timezone name
        tz_name = time.tzname[1] if time.daylight and time.localtime().tm_isdst > 0 else time.tzname[0]
        
        return now.strftime("%a %b %d %Y %H:%M:%S") + f" GMT{offset_str} ({tz_name})"

    @staticmethod
    def _get_pow_config(user_agent: str) -> list:
        """Generate PoW config array with browser fingerprint"""
        lang = random.choice(POW_LANGUAGES)
        perf_time = random.uniform(10000, 100000)
        return [
            random.choice(POW_SCREEN_SIZES),  # [0] screen size
            SoraClient._get_pow_parse_time(),  # [1] time string (local timezone)
            random.choice([4294967296, 4294705152, 2147483648]),  # [2] jsHeapSizeLimit
            0,  # [3] iteration count (dynamic)
            user_agent,  # [4] UA
            random.choice(POW_SCRIPTS) if POW_SCRIPTS else "",  # [5] sora cdn script
            None,  # [6] must be null
            lang[0],  # [7] language
            lang[1],  # [8] languages
            random.randint(2, 10),  # [9] random initial value for dynamic calc
            random.choice(POW_NAVIGATOR_KEYS),  # [10] navigator key
            random.choice(POW_DOCUMENT_KEYS),  # [11] document key
            random.choice(POW_WINDOW_KEYS),  # [12] window key
            perf_time,  # [13] perf time (random)
            str(uuid4()),  # [14] UUID
            "",  # [15] empty
            random.choice(POW_CORES),  # [16] cores
            time.time() * 1000 - perf_time,  # [17] time origin
        ]

    @staticmethod
    def _solve_pow(seed: str, difficulty: str, config_list: list) -> Tuple[str, bool]:
        """Execute PoW calculation using SHA3-512 hash collision"""
        diff_len = len(difficulty) // 2
        seed_encoded = seed.encode()
        target_diff = bytes.fromhex(difficulty)

        static_part1 = (json.dumps(config_list[:3], separators=(',', ':'), ensure_ascii=False)[:-1] + ',').encode()
        static_part2 = (',' + json.dumps(config_list[4:9], separators=(',', ':'), ensure_ascii=False)[1:-1] + ',').encode()
        static_part3 = (',' + json.dumps(config_list[10:], separators=(',', ':'), ensure_ascii=False)[1:]).encode()
        initial_j = config_list[9]
        
        for i in range(POW_MAX_ITERATION):
            dynamic_i = str(i).encode()

            dynamic_j = str(initial_j + (i + 29) // 30).encode()

            final_json = static_part1 + dynamic_i + static_part2 + dynamic_j + static_part3
            b64_encoded = base64.b64encode(final_json)

            hash_value = hashlib.sha3_512(seed_encoded + b64_encoded).digest()

            if hash_value[:diff_len] <= target_diff:
                return b64_encoded.decode(), True

        error_token = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + base64.b64encode(f'"{seed}"'.encode()).decode()
        return error_token, False

    @staticmethod
    def _get_pow_token(user_agent: str) -> str:
        """Generate initial PoW token"""
        config_list = SoraClient._get_pow_config(user_agent)
        seed = format(random.random())
        difficulty = "0fffff"
        solution, _ = SoraClient._solve_pow(seed, difficulty, config_list)
        return "gAAAAAC" + solution

    @staticmethod
    def _build_sentinel_token(
        flow: str,
        req_id: str,
        pow_token: str,
        resp: Dict[str, Any],
        user_agent: str,
    ) -> str:
        """Build openai-sentinel-token from PoW response"""
        final_pow_token = pow_token

        # Check if PoW is required
        proofofwork = resp.get("proofofwork", {})
        if proofofwork.get("required"):
            seed = proofofwork.get("seed", "")
            difficulty = proofofwork.get("difficulty", "")
            if seed and difficulty:
                config_list = SoraClient._get_pow_config(user_agent)
                solution, success = SoraClient._solve_pow(seed, difficulty, config_list)
                final_pow_token = "gAAAAAB" + solution
                if not success:
                    debug_logger.log_info("[Warning] PoW calculation failed, using error token")

        if not final_pow_token.endswith("~S"):
            final_pow_token = final_pow_token + "~S"

        token_payload = {
            "p": final_pow_token,
            "t": resp.get("turnstile", {}).get("dx", ""),
            "c": resp.get("token", ""),
            "id": req_id,
            "flow": flow,
        }
        return json.dumps(token_payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _post_json_sync(url: str, headers: dict, payload: dict, timeout: int, proxy: Optional[str]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")

        try:
            if proxy:
                opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
                resp = opener.open(req, timeout=timeout)
            else:
                resp = urlopen(req, timeout=timeout)

            resp_text = resp.read().decode("utf-8")
            if resp.status not in (200, 201):
                raise Exception(f"Request failed: {resp.status} {resp_text}")
            return json.loads(resp_text)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise Exception(f"HTTP Error: {exc.code} {body}") from exc
        except URLError as exc:
            raise Exception(f"URL Error: {exc}") from exc

    async def _get_sentinel_token_via_browser(self, proxy_url: Optional[str] = None) -> Optional[str]:
        if not PLAYWRIGHT_AVAILABLE:
            debug_logger.log_info("[Warning] Playwright not available, cannot use browser fallback")
            return None
        
        try:
            async with async_playwright() as p:
                launch_args = {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                }
                
                if proxy_url:
                    launch_args["proxy"] = {"server": proxy_url}
                
                browser = await p.chromium.launch(**launch_args)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
                
                page = await context.new_page()
                
                debug_logger.log_info(f"[Browser] Navigating to sora.chatgpt.com...")
                await page.goto("https://sora.chatgpt.com", wait_until="domcontentloaded", timeout=90000)
                
                cookies = await context.cookies()
                device_id = None
                for cookie in cookies:
                    if cookie.get("name") == "oai-did":
                        device_id = cookie.get("value")
                        break
                
                if not device_id:
                    device_id = str(uuid4())
                    debug_logger.log_info(f"[Browser] No oai-did cookie, generated: {device_id}")
                else:
                    debug_logger.log_info(f"[Browser] Got oai-did from cookie: {device_id}")
                
                debug_logger.log_info(f"[Browser] Waiting for SentinelSDK...")
                for _ in range(120):
                    try:
                        sdk_ready = await page.evaluate("() => typeof window.SentinelSDK !== 'undefined'")
                        if sdk_ready:
                            break
                    except:
                        pass
                    await asyncio.sleep(0.5)
                else:
                    debug_logger.log_info("[Browser] SentinelSDK load timeout")
                    await browser.close()
                    return None
                
                debug_logger.log_info(f"[Browser] SentinelSDK ready, getting token...")
                
                # 尝试获取 token，最多重试 3 次
                for attempt in range(3):
                    debug_logger.log_info(f"[Browser] Getting token, attempt {attempt + 1}/3...")
                    
                    try:
                        token = await page.evaluate(
                            "(deviceId) => window.SentinelSDK.token('sora_2_create_task__auto', deviceId)",
                            device_id
                        )
                        
                        if token:
                            debug_logger.log_info(f"[Browser] Token obtained successfully")
                            await browser.close()
                            
                            if isinstance(token, str):
                                token_data = json.loads(token)
                            else:
                                token_data = token
                            
                            if "id" not in token_data or not token_data.get("id"):
                                token_data["id"] = device_id
                            
                            return json.dumps(token_data, ensure_ascii=False, separators=(",", ":"))
                        else:
                            debug_logger.log_info(f"[Browser] Token is empty")
                            
                    except Exception as e:
                        debug_logger.log_info(f"[Browser] Token exception: {str(e)}")
                    
                    if attempt < 2:
                        await asyncio.sleep(2)
                
                await browser.close()
                return None
                
        except Exception as e:
            debug_logger.log_error(
                error_message=f"Browser sentinel token failed: {str(e)}",
                status_code=0,
                response_text=str(e),
                source="Server"
            )
            return None

    async def _nf_create_urllib(self, token: str, payload: dict, sentinel_token: str,
                                proxy_url: Optional[str], token_id: Optional[int] = None,
                                user_agent: Optional[str] = None) -> Dict[str, Any]:
        """Make nf/create request

        Returns:
            Response dict on success

        Raises:
            Exception: With error info, including '400' in message for sentinel token errors
        """
        url = f"{self.base_url}/nf/create"
        if not user_agent:
            user_agent = random.choice(DESKTOP_USER_AGENTS)

        import json as json_mod
        sentinel_data = json_mod.loads(sentinel_token)
        device_id = sentinel_data.get("id", str(uuid4()))

        headers = {
            "Authorization": f"Bearer {token}",
            "openai-sentinel-token": sentinel_token,  # 使用小写，与成功的 curl 请求一致
            "Content-Type": "application/json",
            "User-Agent": user_agent,
            "oai-language": "en-US",  # 使用小写
            "oai-device-id": device_id,  # 使用小写
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Origin": "https://sora.chatgpt.com",
            "Referer": "https://sora.chatgpt.com/explore",
            "Sec-Ch-Ua": '"Not(A:Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Priority": "u=1, i",
        }

        # 添加 Cookie 头（关键修复）
        if token_id:
            try:
                from src.core.database import Database
                db = Database()
                token_obj = await db.get_token(token_id)
                if token_obj and token_obj.st:
                    # 添加 session token cookie
                    headers["Cookie"] = f"__Secure-next-auth.session-token={token_obj.st}"
                    debug_logger.log_info(f"[nf/create] Added session token cookie (length: {len(token_obj.st)})")
                else:
                    debug_logger.log_warning("[nf/create] No session token (st) found for this token")
            except Exception as e:
                debug_logger.log_warning(f"[nf/create] Failed to get session token: {e}")

        # 记录详细的 Sentinel Token 信息
        debug_logger.log_info(f"[nf/create] Preparing request to {url}")
        debug_logger.log_info(f"[nf/create] Device ID: {device_id}")

        # Sentinel Token 前100字符和后50字符
        if len(sentinel_token) > 150:
            debug_logger.log_info(f"[nf/create] Sentinel Token (first 100 chars): {sentinel_token[:100]}...")
            debug_logger.log_info(f"[nf/create] Sentinel Token (last 50 chars): ...{sentinel_token[-50:]}")
        else:
            debug_logger.log_info(f"[nf/create] Sentinel Token: {sentinel_token}")

        debug_logger.log_info(f"[nf/create] Sentinel Token length: {len(sentinel_token)}")

        # Sentinel Token 结构信息
        debug_logger.log_info(f"[nf/create] Sentinel Token structure:")
        if "p" in sentinel_data:
            debug_logger.log_info(f"  - p (POW) length: {len(sentinel_data['p'])}")
        if "t" in sentinel_data:
            debug_logger.log_info(f"  - t (Turnstile) length: {len(sentinel_data['t'])}")
        if "c" in sentinel_data:
            debug_logger.log_info(f"  - c (Challenge) length: {len(sentinel_data['c'])}")
        if "id" in sentinel_data:
            debug_logger.log_info(f"  - id: {sentinel_data['id']}")
        if "flow" in sentinel_data:
            debug_logger.log_info(f"  - flow: {sentinel_data['flow']}")

        # 使用 log_request 方法记录完整的请求详情
        debug_logger.log_request(
            method="POST",
            url=url,
            headers=headers,
            body=payload,
            proxy=proxy_url,
            source="Server"
        )

        try:
            result = await asyncio.to_thread(
                self._post_json_sync, url, headers, payload, 30, proxy_url
            )
            debug_logger.log_info(f"[nf/create] Request succeeded, task_id: {result.get('id', 'N/A')}")
            return result
        except Exception as e:
            error_str = str(e)
            debug_logger.log_error(
                error_message=f"nf/create request failed: {error_str}",
                status_code=0,
                response_text=error_str,
                source="Server"
            )
            raise

    @staticmethod
    def _post_text_sync(url: str, headers: dict, body: str, timeout: int, proxy: Optional[str]) -> Dict[str, Any]:
        data = body.encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")

        try:
            if proxy:
                opener = build_opener(ProxyHandler({"http": proxy, "https": proxy}))
                resp = opener.open(req, timeout=timeout)
            else:
                resp = urlopen(req, timeout=timeout)

            resp_text = resp.read().decode("utf-8")
            if resp.status not in (200, 201):
                raise Exception(f"Request failed: {resp.status} {resp_text}")
            return json.loads(resp_text)
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="ignore")
            raise Exception(f"HTTP Error: {exc.code} {body_text}") from exc
        except URLError as exc:
            raise Exception(f"URL Error: {exc}") from exc

    async def _generate_sentinel_token(self, token: Optional[str] = None, user_agent: Optional[str] = None) -> Tuple[str, str]:
        """Generate openai-sentinel-token by calling /backend-api/sentinel/req and solving PoW

        Supports two modes:
        - external: Get complete sentinel token from external POW service
        - local: Generate POW locally and call sentinel/req endpoint
        """
        # Check if external POW service is configured
        if config.pow_service_mode == "external":
            debug_logger.log_info("[Sentinel] Using external POW service...")
            result = await pow_service_client.get_sentinel_token()

            if result:
                sentinel_token, device_id, service_user_agent = result
                # Use service user agent if provided, otherwise use default
                final_user_agent = service_user_agent if service_user_agent else (
                    user_agent if user_agent else
                    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
                )

                debug_logger.log_info(f"[Sentinel] Got token from external service")
                debug_logger.log_info(f"[Sentinel] Token cached successfully (external)")
                return sentinel_token, final_user_agent
            else:
                # Fallback to local mode if external service fails
                debug_logger.log_info("[Sentinel] External service failed, falling back to local mode")

        # Local mode (original logic)
        debug_logger.log_info("[POW] Using local POW generation")
        req_id = str(uuid4())
        if not user_agent:
            user_agent = "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"

        pow_token = self._get_pow_token(user_agent)

        init_payload = {
            "p": pow_token,
            "id": req_id,
            "flow": "sora_init"
        }
        ua_with_pow = f"{user_agent} {json.dumps(init_payload, separators=(',', ':'))}"

        proxy_url = await self.proxy_manager.get_proxy_url()

        # Request sentinel/req endpoint
        url = f"{self.CHATGPT_BASE_URL}/backend-api/sentinel/req"
        request_payload = {
            "p": pow_token,
            "id": req_id,
            "flow": "sora_init"
        }
        request_body = json.dumps(request_payload, separators=(',', ':'))

        headers = {
            "Accept": "*/*",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/backend-api/sentinel/frame.html",
            "User-Agent": ua_with_pow,
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
        }

        try:
            async with AsyncSession(impersonate="chrome131") as session:
                response = await session.post(
                    url,
                    headers=headers,
                    data=request_body,
                    proxy=proxy_url,
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception(f"Sentinel request failed: {response.status_code} {response.text}")
                resp = response.json()

            debug_logger.log_info(f"Sentinel response: turnstile.dx={bool(resp.get('turnstile', {}).get('dx'))}, token={bool(resp.get('token'))}, pow_required={resp.get('proofofwork', {}).get('required')}")
        except Exception as e:
            debug_logger.log_error(
                error_message=f"Sentinel request failed: {str(e)}",
                status_code=0,
                response_text=str(e),
                source="Server"
            )
            raise

        # Build final sentinel token
        sentinel_token = self._build_sentinel_token(
            self.SENTINEL_FLOW, req_id, pow_token, resp, user_agent
        )

        # Log final token for debugging
        parsed = json.loads(sentinel_token)
        debug_logger.log_info(f"Final sentinel: p_prefix={parsed['p'][:10]}, p_suffix={parsed['p'][-5:]}, t_len={len(parsed['t'])}, c_len={len(parsed['c'])}, flow={parsed['flow']}")

        return sentinel_token, user_agent

    @staticmethod
    def is_storyboard_prompt(prompt: str) -> bool:
        """检测提示词是否为分镜模式格式

        格式: [time]prompt 或 [time]prompt\n[time]prompt
        例如: [5.0s]猫猫从飞机上跳伞 [5.0s]猫猫降落

        Args:
            prompt: 用户输入的提示词

        Returns:
            True if prompt matches storyboard format
        """
        if not prompt:
            return False
        # 匹配格式: [数字s] 或 [数字.数字s]
        pattern = r'\[\d+(?:\.\d+)?s\]'
        matches = re.findall(pattern, prompt)
        # 至少包含一个时间标记才认为是分镜模式
        return len(matches) >= 1

    @staticmethod
    def format_storyboard_prompt(prompt: str) -> str:
        """将分镜格式提示词转换为API所需格式

        输入: 猫猫的奇妙冒险\n[5.0s]猫猫从飞机上跳伞 [5.0s]猫猫降落
        输出: current timeline:\nShot 1:...\n\ninstructions:\n猫猫的奇妙冒险

        Args:
            prompt: 原始分镜格式提示词

        Returns:
            格式化后的API提示词
        """
        # 匹配 [时间]内容 的模式
        pattern = r'\[(\d+(?:\.\d+)?)s\]\s*([^\[]+)'
        matches = re.findall(pattern, prompt)

        if not matches:
            return prompt

        # 提取总述(第一个[时间]之前的内容)
        first_bracket_pos = prompt.find('[')
        instructions = ""
        if first_bracket_pos > 0:
            instructions = prompt[:first_bracket_pos].strip()

        # 格式化分镜
        formatted_shots = []
        for idx, (duration, scene) in enumerate(matches, 1):
            scene = scene.strip()
            shot = f"Shot {idx}:\nduration: {duration}sec\nScene: {scene}"
            formatted_shots.append(shot)

        timeline = "\n\n".join(formatted_shots)

        # 如果有总述,添加instructions部分
        if instructions:
            return f"current timeline:\n{timeline}\n\ninstructions:\n{instructions}"
        else:
            return timeline

    async def _make_request(self, method: str, endpoint: str, token: str,
                           json_data: Optional[Dict] = None,
                           multipart: Optional[Dict] = None,
                           add_sentinel_token: bool = False,
                           token_id: Optional[int] = None) -> Dict[str, Any]:
        """Make HTTP request with proxy support

        Args:
            method: HTTP method (GET/POST)
            endpoint: API endpoint
            token: Access token
            json_data: JSON request body
            multipart: Multipart form data (for file uploads)
            add_sentinel_token: Whether to add openai-sentinel-token header (only for generation requests)
            token_id: Token ID for getting token-specific proxy (optional)
        """
        proxy_url = await self.proxy_manager.get_proxy_url(token_id)

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent" : "Sora/1.2026.007 (Android 15; 24122RKC7C; build 2600700)"
        }

        # 只在生成请求时添加 sentinel token
        if add_sentinel_token:
            sentinel_token, ua = await self._generate_sentinel_token(token)
            headers["openai-sentinel-token"] = sentinel_token
            headers["User-Agent"] = ua

        if not multipart:
            headers["Content-Type"] = "application/json"

        async with AsyncSession() as session:
            url = f"{self.base_url}{endpoint}"

            kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "impersonate": "chrome"  # 自动生成 User-Agent 和浏览器指纹
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            if json_data:
                kwargs["json"] = json_data

            if multipart:
                kwargs["multipart"] = multipart

            # Log request
            debug_logger.log_request(
                method=method,
                url=url,
                headers=headers,
                body=json_data,
                files=multipart,
                proxy=proxy_url,
                source="Server"
            )

            # Record start time
            start_time = time.time()

            # Make request
            if method == "GET":
                response = await session.get(url, **kwargs)
            elif method == "POST":
                response = await session.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Parse response
            try:
                response_json = response.json()
            except:
                response_json = None

            # Log response
            debug_logger.log_response(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response_json if response_json else response.text,
                duration_ms=duration_ms,
                source="Server"
            )

            # Check status
            if response.status_code not in [200, 201]:
                # Parse error response
                error_data = None
                try:
                    error_data = response.json()
                except:
                    pass

                # Check for unsupported_country_code error
                if error_data and isinstance(error_data, dict):
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == "unsupported_country_code":
                        # Create structured error with full error data
                        import json
                        error_msg = json.dumps(error_data)
                        debug_logger.log_error(
                            error_message=f"Unsupported country: {error_msg}",
                            status_code=response.status_code,
                            response_text=error_msg,
                            source="Server"
                        )
                        # Raise exception with structured error data
                        raise Exception(error_msg)

                # Generic error handling
                error_msg = f"API request failed: {response.status_code} - {response.text}"
                debug_logger.log_error(
                    error_message=error_msg,
                    status_code=response.status_code,
                    response_text=response.text,
                    source="Server"
                )
                raise Exception(error_msg)

            return response_json if response_json else response.json()
    
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information"""
        return await self._make_request("GET", "/me", token)
    
    async def upload_image(self, image_data: bytes, token: str, filename: str = "image.png") -> str:
        """Upload image and return media_id

        使用 CurlMime 对象上传文件（curl_cffi 的正确方式）
        参考：https://curl-cffi.readthedocs.io/en/latest/quick_start.html#uploads
        """
        # 检测图片类型
        mime_type = "image/png"
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            mime_type = "image/jpeg"
        elif filename.lower().endswith('.webp'):
            mime_type = "image/webp"

        # 创建 CurlMime 对象
        mp = CurlMime()

        # 添加文件部分
        mp.addpart(
            name="file",
            content_type=mime_type,
            filename=filename,
            data=image_data
        )

        # 添加文件名字段
        mp.addpart(
            name="file_name",
            data=filename.encode('utf-8')
        )

        result = await self._make_request("POST", "/uploads", token, multipart=mp)
        return result["id"]
    
    async def generate_image(self, prompt: str, token: str, width: int = 360,
                            height: int = 360, media_id: Optional[str] = None, token_id: Optional[int] = None) -> str:
        """Generate image (text-to-image or image-to-image)"""
        operation = "remix" if media_id else "simple_compose"

        inpaint_items = []
        if media_id:
            inpaint_items = [{
                "type": "image",
                "frame_index": 0,
                "upload_media_id": media_id
            }]

        json_data = {
            "type": "image_gen",
            "operation": operation,
            "prompt": prompt,
            "width": width,
            "height": height,
            "n_variants": 1,
            "n_frames": 1,
            "inpaint_items": inpaint_items
        }

        # 生成请求需要添加 sentinel token
        result = await self._make_request("POST", "/video_gen", token, json_data=json_data, add_sentinel_token=True, token_id=token_id)
        return result["id"]
    
    async def generate_video(self, prompt: str, token: str, orientation: str = "landscape",
                            media_id: Optional[str] = None, n_frames: int = 450, style_id: Optional[str] = None,
                            model: str = "sy_8", size: str = "small", token_id: Optional[int] = None) -> str:
        """Generate video (text-to-video or image-to-video)

        Args:
            prompt: Video generation prompt
            token: Access token
            orientation: Video orientation (landscape/portrait)
            media_id: Optional image media_id for image-to-video
            n_frames: Number of frames (300/450/750)
            style_id: Optional style ID
            model: Model to use (sy_8 for standard, sy_ore for pro)
            size: Video size (small for standard, large for HD)
            token_id: Token ID for getting token-specific proxy (optional)
        """
        inpaint_items = []
        if media_id:
            inpaint_items = [{
                "kind": "upload",
                "upload_id": media_id
            }]

        json_data = {
            "kind": "video",
            "prompt": prompt,
            "orientation": orientation,
            "size": size,
            "n_frames": n_frames,
            "model": model,
            "inpaint_items": inpaint_items,
            "style_id": style_id
        }

        proxy_url = await self.proxy_manager.get_proxy_url(token_id)

        # Get POW proxy from configuration (unified with pow_service config)
        pow_proxy_url = None
        if config.pow_service_proxy_enabled:
            pow_proxy_url = config.pow_service_proxy_url or None

        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

        # Try to get cached sentinel token first (using lightweight Playwright approach)
        try:
            sentinel_token = await _get_cached_sentinel_token(pow_proxy_url, force_refresh=False)
        except Exception as e:
            # 403/429 errors from oai-did fetch - don't retry, just fail
            error_str = str(e)
            if "403" in error_str or "429" in error_str:
                debug_logger.log_error(
                    error_message=f"Failed to get sentinel token: {error_str}",
                    status_code=403 if "403" in error_str else 429,
                    response_text=error_str,
                    source="Server"
                )
                raise
            sentinel_token = None

        if not sentinel_token:
            # Fallback to manual POW if lightweight approach fails
            debug_logger.log_info("[Warning] Lightweight sentinel token failed, falling back to manual POW")
            sentinel_token, user_agent = await self._generate_sentinel_token(token)

        # First attempt with cached/generated token
        try:
            result = await self._nf_create_urllib(token, json_data, sentinel_token, proxy_url, token_id, user_agent)
            return result["id"]
        except Exception as e:
            error_str = str(e)
            
            # Check if it's a 400 error (sentinel token invalid)
            if "400" in error_str or "sentinel" in error_str.lower() or "invalid" in error_str.lower():
                debug_logger.log_info("[Sentinel] Got 400 error, refreshing token and retrying...")
                
                # Invalidate cache and get fresh token
                _invalidate_sentinel_cache()
                
                try:
                    sentinel_token = await _get_cached_sentinel_token(pow_proxy_url, force_refresh=True)
                except Exception as refresh_e:
                    # 403/429 errors - don't continue
                    error_str = str(refresh_e)
                    if "403" in error_str or "429" in error_str:
                        raise refresh_e
                    sentinel_token = None
                
                if not sentinel_token:
                    # Fallback to manual POW
                    debug_logger.log_info("[Warning] Refresh failed, falling back to manual POW")
                    sentinel_token, user_agent = await self._generate_sentinel_token(token)
                
                # Retry with fresh token
                result = await self._nf_create_urllib(token, json_data, sentinel_token, proxy_url, token_id, user_agent)
                return result["id"]
            
            # For other errors, just re-raise
            raise
    
    async def get_image_tasks(self, token: str, limit: int = 20, token_id: Optional[int] = None) -> Dict[str, Any]:
        """Get recent image generation tasks"""
        return await self._make_request("GET", f"/v2/recent_tasks?limit={limit}", token, token_id=token_id)

    async def get_video_drafts(self, token: str, limit: int = 15, token_id: Optional[int] = None) -> Dict[str, Any]:
        """Get recent video drafts"""
        return await self._make_request("GET", f"/project_y/profile/drafts?limit={limit}", token, token_id=token_id)

    async def get_pending_tasks(self, token: str, token_id: Optional[int] = None) -> list:
        """Get pending video generation tasks

        Returns:
            List of pending tasks with progress information
        """
        result = await self._make_request("GET", "/nf/pending/v2", token, token_id=token_id)
        # The API returns a list directly
        return result if isinstance(result, list) else []

    async def post_video_for_watermark_free(self, generation_id: str, prompt: str, token: str) -> str:
        """Post video to get watermark-free version

        Args:
            generation_id: The generation ID (e.g., gen_01k9btrqrnen792yvt703dp0tq)
            prompt: The original generation prompt
            token: Access token

        Returns:
            Post ID (e.g., s_690ce161c2488191a3476e9969911522)
        """
        json_data = {
            "attachments_to_create": [
                {
                    "generation_id": generation_id,
                    "kind": "sora"
                }
            ],
            "post_text": ""
        }

        # 发布请求需要添加 sentinel token
        result = await self._make_request("POST", "/project_y/post", token, json_data=json_data, add_sentinel_token=True)

        # 返回 post.id
        return result.get("post", {}).get("id", "")

    async def delete_post(self, post_id: str, token: str) -> bool:
        """Delete a published post

        Args:
            post_id: The post ID (e.g., s_690ce161c2488191a3476e9969911522)
            token: Access token

        Returns:
            True if deletion was successful
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        async with AsyncSession() as session:
            url = f"{self.base_url}/project_y/post/{post_id}"

            kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "impersonate": "chrome"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            # Log request
            debug_logger.log_request(
                method="DELETE",
                url=url,
                headers=headers,
                body=None,
                files=None,
                proxy=proxy_url
            )

            # Record start time
            start_time = time.time()

            # Make DELETE request
            response = await session.delete(url, **kwargs)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            debug_logger.log_response(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.text if response.text else "No content",
                duration_ms=duration_ms,
                source="Server"
            )

            # Check status (DELETE typically returns 204 No Content or 200 OK)
            if response.status_code not in [200, 204]:
                error_msg = f"Delete post failed: {response.status_code} - {response.text}"
                debug_logger.log_error(
                    error_message=error_msg,
                    status_code=response.status_code,
                    response_text=response.text,
                    source="Server"
                )
                raise Exception(error_msg)

            return True

    async def get_watermark_free_url_custom(self, parse_url: str, parse_token: str, post_id: str) -> str:
        """Get watermark-free video URL from custom parse server

        Args:
            parse_url: Custom parse server URL (e.g., http://example.com)
            parse_token: Access token for custom parse server
            post_id: Post ID to parse (e.g., s_690c0f574c3881918c3bc5b682a7e9fd)

        Returns:
            Download link from custom parse server

        Raises:
            Exception: If parse fails or token is invalid
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        # Construct the share URL
        share_url = f"https://sora.chatgpt.com/p/{post_id}"

        # Prepare request
        json_data = {
            "url": share_url,
            "token": parse_token
        }

        kwargs = {
            "json": json_data,
            "timeout": 30,
            "impersonate": "chrome"
        }

        if proxy_url:
            kwargs["proxy"] = proxy_url

        try:
            async with AsyncSession() as session:
                # Record start time
                start_time = time.time()

                # Make POST request to custom parse server
                response = await session.post(f"{parse_url}/get-sora-link", **kwargs)

                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Log response
                debug_logger.log_response(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    body=response.text if response.text else "No content",
                    duration_ms=duration_ms,
                    source="Server"
                )

                # Check status
                if response.status_code != 200:
                    error_msg = f"Custom parse failed: {response.status_code} - {response.text}"
                    debug_logger.log_error(
                        error_message=error_msg,
                        status_code=response.status_code,
                        response_text=response.text,
                        source="Server"
                    )
                    raise Exception(error_msg)

                # Parse response
                result = response.json()

                # Check for error in response
                if "error" in result:
                    error_msg = f"Custom parse error: {result['error']}"
                    debug_logger.log_error(
                        error_message=error_msg,
                        status_code=401,
                        response_text=str(result),
                        source="Server"
                    )
                    raise Exception(error_msg)

                # Extract download link
                download_link = result.get("download_link")
                if not download_link:
                    raise Exception("No download_link in custom parse response")

                debug_logger.log_info(f"Custom parse successful: {download_link}")
                return download_link

        except Exception as e:
            debug_logger.log_error(
                error_message=f"Custom parse request failed: {str(e)}",
                status_code=500,
                response_text=str(e),
                source="Server"
            )
            raise

    # ==================== Character Creation Methods ====================

    async def upload_character_video(self, video_data: bytes, token: str) -> str:
        """Upload character video and return cameo_id

        Args:
            video_data: Video file bytes
            token: Access token

        Returns:
            cameo_id
        """
        mp = CurlMime()
        mp.addpart(
            name="file",
            content_type="video/mp4",
            filename="video.mp4",
            data=video_data
        )
        mp.addpart(
            name="timestamps",
            data=b"0,3"
        )

        result = await self._make_request("POST", "/characters/upload", token, multipart=mp)
        return result.get("id")

    async def get_cameo_status(self, cameo_id: str, token: str) -> Dict[str, Any]:
        """Get character (cameo) processing status

        Args:
            cameo_id: The cameo ID returned from upload_character_video
            token: Access token

        Returns:
            Dictionary with status, display_name_hint, username_hint, profile_asset_url, instruction_set_hint
        """
        return await self._make_request("GET", f"/project_y/cameos/in_progress/{cameo_id}", token)

    async def download_character_image(self, image_url: str) -> bytes:
        """Download character image from URL

        Args:
            image_url: The profile_asset_url from cameo status

        Returns:
            Image file bytes
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        kwargs = {
            "timeout": self.timeout,
            "impersonate": "chrome"
        }

        if proxy_url:
            kwargs["proxy"] = proxy_url

        async with AsyncSession() as session:
            response = await session.get(image_url, **kwargs)
            if response.status_code != 200:
                raise Exception(f"Failed to download image: {response.status_code}")
            return response.content

    async def finalize_character(self, cameo_id: str, username: str, display_name: str,
                                profile_asset_pointer: str, instruction_set, token: str) -> str:
        """Finalize character creation

        Args:
            cameo_id: The cameo ID
            username: Character username
            display_name: Character display name
            profile_asset_pointer: Asset pointer from upload_character_image
            instruction_set: Character instruction set (not used by API, always set to None)
            token: Access token

        Returns:
            character_id
        """
        # Note: API always expects instruction_set to be null
        # The instruction_set parameter is kept for backward compatibility but not used
        _ = instruction_set  # Suppress unused parameter warning
        json_data = {
            "cameo_id": cameo_id,
            "username": username,
            "display_name": display_name,
            "profile_asset_pointer": profile_asset_pointer,
            "instruction_set": None,
            "safety_instruction_set": None
        }

        result = await self._make_request("POST", "/characters/finalize", token, json_data=json_data)
        return result.get("character", {}).get("character_id")

    async def set_character_public(self, cameo_id: str, token: str) -> bool:
        """Set character as public

        Args:
            cameo_id: The cameo ID
            token: Access token

        Returns:
            True if successful
        """
        json_data = {"visibility": "public"}
        await self._make_request("POST", f"/project_y/cameos/by_id/{cameo_id}/update_v2", token, json_data=json_data)
        return True

    async def upload_character_image(self, image_data: bytes, token: str) -> str:
        """Upload character image and return asset_pointer

        Args:
            image_data: Image file bytes
            token: Access token

        Returns:
            asset_pointer
        """
        mp = CurlMime()
        mp.addpart(
            name="file",
            content_type="image/webp",
            filename="profile.webp",
            data=image_data
        )
        mp.addpart(
            name="use_case",
            data=b"profile"
        )

        result = await self._make_request("POST", "/project_y/file/upload", token, multipart=mp)
        return result.get("asset_pointer")

    async def delete_character(self, character_id: str, token: str) -> bool:
        """Delete a character

        Args:
            character_id: The character ID
            token: Access token

        Returns:
            True if successful
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        async with AsyncSession() as session:
            url = f"{self.base_url}/project_y/characters/{character_id}"

            kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "impersonate": "chrome"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.delete(url, **kwargs)
            if response.status_code not in [200, 204]:
                raise Exception(f"Failed to delete character: {response.status_code}")
            return True

    async def remix_video(self, remix_target_id: str, prompt: str, token: str,
                         orientation: str = "portrait", n_frames: int = 450, style_id: Optional[str] = None) -> str:
        """Generate video using remix (based on existing video)

        Args:
            remix_target_id: The video ID from Sora share link (e.g., s_690d100857248191b679e6de12db840e)
            prompt: Generation prompt
            token: Access token
            orientation: Video orientation (portrait/landscape)
            n_frames: Number of frames
            style_id: Optional style ID

        Returns:
            task_id
        """
        json_data = {
            "kind": "video",
            "prompt": prompt,
            "inpaint_items": [],
            "remix_target_id": remix_target_id,
            "cameo_ids": [],
            "cameo_replacements": {},
            "model": "sy_8",
            "orientation": orientation,
            "n_frames": n_frames,
            "style_id": style_id
        }

        # Generate sentinel token and call /nf/create using urllib
        proxy_url = await self.proxy_manager.get_proxy_url()
        sentinel_token, user_agent = await self._generate_sentinel_token(token)
        result = await self._nf_create_urllib(token, json_data, sentinel_token, proxy_url, user_agent=user_agent)
        return result.get("id")

    async def generate_storyboard(self, prompt: str, token: str, orientation: str = "landscape",
                                 media_id: Optional[str] = None, n_frames: int = 450, style_id: Optional[str] = None) -> str:
        """Generate video using storyboard mode

        Args:
            prompt: Formatted storyboard prompt (Shot 1:\nduration: 5.0sec\nScene: ...)
            token: Access token
            orientation: Video orientation (portrait/landscape)
            media_id: Optional image media_id for image-to-video
            n_frames: Number of frames
            style_id: Optional style ID

        Returns:
            task_id
        """
        inpaint_items = []
        if media_id:
            inpaint_items = [{
                "kind": "upload",
                "upload_id": media_id
            }]

        json_data = {
            "kind": "video",
            "prompt": prompt,
            "title": "Draft your video",
            "orientation": orientation,
            "size": "small",
            "n_frames": n_frames,
            "storyboard_id": None,
            "inpaint_items": inpaint_items,
            "remix_target_id": None,
            "model": "sy_8",
            "metadata": None,
            "style_id": style_id,
            "cameo_ids": None,
            "cameo_replacements": None,
            "audio_caption": None,
            "audio_transcript": None,
            "video_caption": None
        }

        result = await self._make_request("POST", "/nf/create/storyboard", token, json_data=json_data, add_sentinel_token=True)
        return result.get("id")

    async def enhance_prompt(self, prompt: str, token: str, expansion_level: str = "medium",
                            duration_s: int = 10, token_id: Optional[int] = None) -> str:
        """Enhance prompt using Sora's prompt enhancement API

        Args:
            prompt: Original prompt to enhance
            token: Access token
            expansion_level: Expansion level (medium/long)
            duration_s: Duration in seconds (10/15/20)
            token_id: Token ID for getting token-specific proxy (optional)

        Returns:
            Enhanced prompt text
        """
        json_data = {
            "prompt": prompt,
            "expansion_level": expansion_level,
            "duration_s": duration_s
        }

        result = await self._make_request("POST", "/editor/enhance_prompt", token, json_data=json_data, token_id=token_id)
        return result.get("enhanced_prompt", "")
