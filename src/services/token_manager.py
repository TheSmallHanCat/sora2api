"""Token management module"""
import jwt
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from curl_cffi.requests import AsyncSession
from faker import Faker
from ..core.database import Database
from ..core.models import Token, TokenStats
from ..core.config import config
from .proxy_manager import ProxyManager
from ..core.logger import debug_logger

class TokenManager:
    """Token lifecycle manager"""

    def __init__(self, db: Database):
        self.db = db
        self._lock = asyncio.Lock()
        self.proxy_manager = ProxyManager(db)
        self.fake = Faker()
    
    async def decode_jwt(self, token: str) -> dict:
        """Decode JWT token without verification"""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded
        except Exception as e:
            raise ValueError(f"Invalid JWT token: {str(e)}")

    def _generate_random_username(self) -> str:
        """Generate a random username using faker

        Returns:
            A random username string
        """
        # Генерация реального имени
        first_name = self.fake.first_name()
        last_name = self.fake.last_name()

        # Удаление пробелов и специальных символов, оставляем только буквы
        first_name_clean = ''.join(c for c in first_name if c.isalpha())
        last_name_clean = ''.join(c for c in last_name if c.isalpha())

        # Генерация 1-4 случайных цифр
        random_digits = str(random.randint(1, 9999))

        # Случайный выбор формата имени пользователя
        format_choice = random.choice([
            f"{first_name_clean}{last_name_clean}{random_digits}",
            f"{first_name_clean}.{last_name_clean}{random_digits}",
            f"{first_name_clean}{random_digits}",
            f"{last_name_clean}{random_digits}",
            f"{first_name_clean[0]}{last_name_clean}{random_digits}",
            f"{first_name_clean}{last_name_clean[0]}{random_digits}"
        ])

        # Преобразование в нижний регистр
        return format_choice.lower()

    async def get_user_info(self, access_token: str) -> dict:
        """Get user info from Sora API"""
        proxy_url = await self.proxy_manager.get_proxy_url()

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Origin": "https://sora.chatgpt.com",
                "Referer": "https://sora.chatgpt.com/"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "chrome"  # Автоматическая генерация User-Agent и отпечатка браузера
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url

            response = await session.get(
                f"{config.sora_base_url}/me",
                **kwargs
            )

            if response.status_code != 200:
                raise ValueError(f"Failed to get user info: {response.status_code}")

            return response.json()

    async def get_subscription_info(self, token: str) -> Dict[str, Any]:
        """Get subscription information from Sora API

        Returns:
            {
                "plan_type": "chatgpt_team",
                "plan_title": "ChatGPT Business",
                "subscription_end": "2025-11-13T16:58:21Z"
            }
        """
        print(f"🔍 Начало получения информации о подписке...")
        proxy_url = await self.proxy_manager.get_proxy_url()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        async with AsyncSession() as session:
            url = "https://sora.chatgpt.com/backend/billing/subscriptions"
            print(f"📡 Запрос URL: {url}")
            print(f"🔑 Используем Token: {token[:30]}...")

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "chrome"  # Автогенерация User-Agent и отпечатка браузера
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 Используем прокси: {proxy_url}")

            response = await session.get(url, **kwargs)
            print(f"📥 Статус код ответа: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"📦 Данные ответа: {data}")

                # Извлечение первой информации о подписке
                if data.get("data") and len(data["data"]) > 0:
                    subscription = data["data"][0]
                    plan = subscription.get("plan", {})

                    result = {
                        "plan_type": plan.get("id", ""),
                        "plan_title": plan.get("title", ""),
                        "subscription_end": subscription.get("end_ts", "")
                    }
                    print(f"✅ Информация о подписке успешно извлечена: {result}")
                    return result

                print(f"⚠️  В данных ответа нет информации о подписке")
                return {
                    "plan_type": "",
                    "plan_title": "",
                    "subscription_end": ""
                }
            else:
                print(f"❌ Failed to get subscription info: {response.status_code}")
                print(f"📄 Содержимое ответа: {response.text}")

                # Check for token_expired error
                try:
                    error_data = response.json()
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == "token_expired":
                        raise Exception(f"Token истёк: {error_info.get('message', 'Token expired')}")
                except ValueError:
                    pass

                raise Exception(f"Failed to get subscription info: {response.status_code}")

    async def get_sora2_invite_code(self, access_token: str) -> dict:
        """Get Sora2 invite code"""
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 Начало получения кода приглашения Sora2...")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "chrome"  # Автоматическая генерация User-Agent и отпечатка браузера
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 Используется прокси: {proxy_url}")

            response = await session.get(
                "https://sora.chatgpt.com/backend/project_y/invite/mine",
                **kwargs
            )

            print(f"📥 Статус код ответа: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Код приглашения Sora2 успешно получен: {data}")
                return {
                    "supported": True,
                    "invite_code": data.get("invite_code"),
                    "redeemed_count": data.get("redeemed_count", 0),
                    "total_count": data.get("total_count", 0)
                }
            else:
                print(f"❌ Не удалось получить код приглашения Sora2: {response.status_code}")
                print(f"📄 Содержимое ответа: {response.text}")

                # Check for specific errors
                try:
                    error_data = response.json()
                    error_info = error_data.get("error", {})

                    # Check for unsupported_country_code
                    if error_info.get("code") == "unsupported_country_code":
                        country = error_info.get("param", "неизвестно")
                        raise Exception(f"Sora недоступна в вашей стране ({country}): {error_info.get('message', '')}")

                    # Check if it's 401 unauthorized (token doesn't support Sora2)
                    if response.status_code == 401 and "Unauthorized" in error_info.get("message", ""):
                        print(f"⚠️  Token не поддерживает Sora2, попытка активации...")

                        # Try to activate Sora2
                        try:
                            activate_response = await session.get(
                                "https://sora.chatgpt.com/backend/m/bootstrap",
                                **kwargs
                            )

                            if activate_response.status_code == 200:
                                print(f"✅ Запрос активации Sora2 успешен, повторное получение кода приглашения...")

                                # Retry getting invite code
                                retry_response = await session.get(
                                    "https://sora.chatgpt.com/backend/project_y/invite/mine",
                                    **kwargs
                                )

                                if retry_response.status_code == 200:
                                    retry_data = retry_response.json()
                                    print(f"✅ Sora2 успешно активирована! Код приглашения: {retry_data}")
                                    return {
                                        "supported": True,
                                        "invite_code": retry_data.get("invite_code"),
                                        "redeemed_count": retry_data.get("redeemed_count", 0),
                                        "total_count": retry_data.get("total_count", 0)
                                    }
                                else:
                                    print(f"⚠️  После активации не удалось получить код приглашения: {retry_response.status_code}")
                            else:
                                print(f"⚠️  Не удалось активировать Sora2: {activate_response.status_code}")
                        except Exception as activate_e:
                            print(f"⚠️  Ошибка при активации Sora2: {activate_e}")

                        return {
                            "supported": False,
                            "invite_code": None
                        }
                except ValueError:
                    pass

                return {
                    "supported": False,
                    "invite_code": None
                }

    async def get_sora2_remaining_count(self, access_token: str) -> dict:
        """Get Sora2 remaining video count

        Returns:
            {
                "remaining_count": 27,
                "rate_limit_reached": false,
                "access_resets_in_seconds": 46833
            }
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 Начало получения оставшегося количества Sora2...")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "chrome"  # Автоматическая генерация User-Agent и отпечатка браузера
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 Используется прокси: {proxy_url}")

            response = await session.get(
                "https://sora.chatgpt.com/backend/nf/check",
                **kwargs
            )

            print(f"📥 Статус-код ответа: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Количество оставшихся попыток Sora2 успешно получено: {data}")

                rate_limit_info = data.get("rate_limit_and_credit_balance", {})
                return {
                    "success": True,
                    "remaining_count": rate_limit_info.get("estimated_num_videos_remaining", 0),
                    "rate_limit_reached": rate_limit_info.get("rate_limit_reached", False),
                    "access_resets_in_seconds": rate_limit_info.get("access_resets_in_seconds", 0)
                }
            else:
                print(f"❌ Не удалось получить количество оставшихся попыток Sora2: {response.status_code}")
                print(f"📄 Содержимое ответа: {response.text[:500]}")
                return {
                    "success": False,
                    "remaining_count": 0,
                    "error": f"Failed to get remaining count: {response.status_code}"
                }

    async def check_username_available(self, access_token: str, username: str) -> bool:
        """Check if username is available

        Args:
            access_token: Access token for authentication
            username: Username to check

        Returns:
            True if username is available, False otherwise
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 Проверка доступности имени пользователя: {username}")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            kwargs = {
                "headers": headers,
                "json": {"username": username},
                "timeout": 30,
                "impersonate": "chrome"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 Используется прокси: {proxy_url}")

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/profile/username/check",
                **kwargs
            )

            print(f"📥 Статус-код ответа: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                available = data.get("available", False)
                print(f"✅ Результат проверки имени пользователя: available={available}")
                return available
            else:
                print(f"❌ Проверка имени пользователя не удалась: {response.status_code}")
                print(f"📄 Содержимое ответа: {response.text[:500]}")
                return False

    async def set_username(self, access_token: str, username: str) -> dict:
        """Set username for the account

        Args:
            access_token: Access token for authentication
            username: Username to set

        Returns:
            User profile information after setting username
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 Начало установки имени пользователя: {username}")

        async with AsyncSession() as session:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            kwargs = {
                "headers": headers,
                "json": {"username": username},
                "timeout": 30,
                "impersonate": "chrome"
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 Используется прокси: {proxy_url}")

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/profile/username/set",
                **kwargs
            )

            print(f"📥 Статус-код ответа: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Имя пользователя успешно установлено: {data.get('username')}")
                return data
            else:
                print(f"❌ Не удалось установить имя пользователя: {response.status_code}")
                print(f"📄 Содержимое ответа: {response.text[:500]}")
                raise Exception(f"Failed to set username: {response.status_code}")

    async def activate_sora2_invite(self, access_token: str, invite_code: str) -> dict:
        """Activate Sora2 with invite code"""
        import uuid
        proxy_url = await self.proxy_manager.get_proxy_url()

        print(f"🔍 Начало активации кода приглашения Sora2: {invite_code}")
        print(f"🔑 Префикс Access Token: {access_token[:50]}...")

        async with AsyncSession() as session:
            # Генерация ID устройства
            device_id = str(uuid.uuid4())

            # Устанавливаем только необходимые заголовки, пусть impersonate обработает остальное
            headers = {
                "authorization": f"Bearer {access_token}",
                "cookie": f"oai-did={device_id}"
            }

            print(f"🆔 ID устройства: {device_id}")
            print(f"📦 Тело запроса: {{'invite_code': '{invite_code}'}}")

            kwargs = {
                "headers": headers,
                "json": {"invite_code": invite_code},
                "timeout": 30,
                "impersonate": "chrome120"  # Используем chrome120 для автоматической обработки UA и других заголовков
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                print(f"🌐 Используется прокси: {proxy_url}")

            response = await session.post(
                "https://sora.chatgpt.com/backend/project_y/invite/accept",
                **kwargs
            )

            print(f"📥 Статус-код ответа: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Sora2 успешно активирована: {data}")
                return {
                    "success": data.get("success", False),
                    "already_accepted": data.get("already_accepted", False)
                }
            else:
                print(f"❌ Активация Sora2 не удалась: {response.status_code}")
                print(f"📄 Содержимое ответа: {response.text[:500]}")
                raise Exception(f"Failed to activate Sora2: {response.status_code}")

    async def st_to_at(self, session_token: str) -> dict:
        """Convert Session Token to Access Token"""
        debug_logger.log_info(f"[ST_TO_AT] Начало конвертации Session Token в Access Token...")
        proxy_url = await self.proxy_manager.get_proxy_url()

        async with AsyncSession() as session:
            headers = {
                "Cookie": f"__Secure-next-auth.session-token={session_token}",
                "Accept": "application/json",
                "Origin": "https://sora.chatgpt.com",
                "Referer": "https://sora.chatgpt.com/"
            }

            kwargs = {
                "headers": headers,
                "timeout": 30,
                "impersonate": "chrome"  # Автоматическая генерация User-Agent и отпечатка браузера
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                debug_logger.log_info(f"[ST_TO_AT] Используется прокси: {proxy_url}")

            url = "https://sora.chatgpt.com/api/auth/session"
            debug_logger.log_info(f"[ST_TO_AT] 📡 URL запроса: {url}")

            try:
                response = await session.get(url, **kwargs)
                debug_logger.log_info(f"[ST_TO_AT] 📥 Статус-код ответа: {response.status_code}")

                if response.status_code != 200:
                    error_msg = f"Failed to convert ST to AT: {response.status_code}"
                    debug_logger.log_info(f"[ST_TO_AT] ❌ {error_msg}")
                    debug_logger.log_info(f"[ST_TO_AT] Содержимое ответа: {response.text[:500]}")
                    raise ValueError(error_msg)

                # Получаем текст ответа для отладки
                response_text = response.text
                debug_logger.log_info(f"[ST_TO_AT] 📄 Содержимое ответа: {response_text[:500]}")

                # Проверяем, не пустой ли ответ
                if not response_text or response_text.strip() == "":
                    debug_logger.log_info(f"[ST_TO_AT] ❌ Пустое тело ответа")
                    raise ValueError("Response body is empty")

                try:
                    data = response.json()
                except Exception as json_err:
                    debug_logger.log_info(f"[ST_TO_AT] ❌ Ошибка парсинга JSON: {str(json_err)}")
                    debug_logger.log_info(f"[ST_TO_AT] Исходный ответ: {response_text[:1000]}")
                    raise ValueError(f"Failed to parse JSON response: {str(json_err)}")

                # Проверяем, не равен ли data None
                if data is None:
                    debug_logger.log_info(f"[ST_TO_AT] ❌ Пустой JSON в ответе")
                    raise ValueError("Response JSON is empty")

                access_token = data.get("accessToken")
                email = data.get("user", {}).get("email") if data.get("user") else None
                expires = data.get("expires")

                # Проверяем обязательные поля
                if not access_token:
                    debug_logger.log_info(f"[ST_TO_AT] ❌ В ответе отсутствует поле accessToken")
                    debug_logger.log_info(f"[ST_TO_AT] Данные ответа: {data}")
                    raise ValueError("Missing accessToken in response")

                debug_logger.log_info(f"[ST_TO_AT] ✅ Конвертация ST успешна")
                debug_logger.log_info(f"  - Email: {email}")
                debug_logger.log_info(f"  - Время истечения: {expires}")

                return {
                    "access_token": access_token,
                    "email": email,
                    "expires": expires
                }
            except Exception as e:
                debug_logger.log_info(f"[ST_TO_AT] 🔴 Исключение: {str(e)}")
                raise
    
    async def rt_to_at(self, refresh_token: str, client_id: Optional[str] = None) -> dict:
        """Convert Refresh Token to Access Token

        Args:
            refresh_token: Refresh Token
            client_id: Client ID (optional, uses default if not provided)
        """
        # Use provided client_id or default
        effective_client_id = client_id or "app_LlGpXReQgckcGGUo2JrYvtJK"

        debug_logger.log_info(f"[RT_TO_AT] Начало конвертации Refresh Token в Access Token...")
        debug_logger.log_info(f"[RT_TO_AT] Используется Client ID: {effective_client_id[:20]}...")
        proxy_url = await self.proxy_manager.get_proxy_url()

        async with AsyncSession() as session:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            kwargs = {
                "headers": headers,
                "json": {
                    "client_id": effective_client_id,
                    "grant_type": "refresh_token",
                    "redirect_uri": "com.openai.chat://auth0.openai.com/ios/com.openai.chat/callback",
                    "refresh_token": refresh_token
                },
                "timeout": 30,
                "impersonate": "chrome"  # Автоматическая генерация User-Agent и отпечатка браузера
            }

            if proxy_url:
                kwargs["proxy"] = proxy_url
                debug_logger.log_info(f"[RT_TO_AT] Используется прокси: {proxy_url}")

            url = "https://auth.openai.com/oauth/token"
            debug_logger.log_info(f"[RT_TO_AT] 📡 URL запроса: {url}")

            try:
                response = await session.post(url, **kwargs)
                debug_logger.log_info(f"[RT_TO_AT] 📥 Статус-код ответа: {response.status_code}")

                if response.status_code != 200:
                    error_msg = f"Failed to convert RT to AT: {response.status_code}"
                    debug_logger.log_info(f"[RT_TO_AT] ❌ {error_msg}")
                    debug_logger.log_info(f"[RT_TO_AT] Содержимое ответа: {response.text[:500]}")
                    raise ValueError(f"{error_msg} - {response.text}")

                # Получаем текст ответа для отладки
                response_text = response.text
                debug_logger.log_info(f"[RT_TO_AT] 📄 Содержимое ответа: {response_text[:500]}")

                # Проверяем, не пустой ли ответ
                if not response_text or response_text.strip() == "":
                    debug_logger.log_info(f"[RT_TO_AT] ❌ Пустое тело ответа")
                    raise ValueError("Response body is empty")

                try:
                    data = response.json()
                except Exception as json_err:
                    debug_logger.log_info(f"[RT_TO_AT] ❌ Ошибка парсинга JSON: {str(json_err)}")
                    debug_logger.log_info(f"[RT_TO_AT] Исходный ответ: {response_text[:1000]}")
                    raise ValueError(f"Failed to parse JSON response: {str(json_err)}")

                # Проверяем, не равен ли data None
                if data is None:
                    debug_logger.log_info(f"[RT_TO_AT] ❌ Пустой JSON в ответе")
                    raise ValueError("Response JSON is empty")

                access_token = data.get("access_token")
                new_refresh_token = data.get("refresh_token")
                expires_in = data.get("expires_in")

                # Проверяем обязательные поля
                if not access_token:
                    debug_logger.log_info(f"[RT_TO_AT] ❌ В ответе отсутствует поле access_token")
                    debug_logger.log_info(f"[RT_TO_AT] Данные ответа: {data}")
                    raise ValueError("Missing access_token in response")

                debug_logger.log_info(f"[RT_TO_AT] ✅ Конвертация RT успешна")
                debug_logger.log_info(f"  - Срок действия нового Access Token: {expires_in} секунд")
                debug_logger.log_info(f"  - Refresh Token обновлён: {'да' if new_refresh_token else 'нет'}")

                return {
                    "access_token": access_token,
                    "refresh_token": new_refresh_token,
                    "expires_in": expires_in
                }
            except Exception as e:
                debug_logger.log_info(f"[RT_TO_AT] 🔴 Исключение: {str(e)}")
                raise
    
    async def add_token(self, token_value: str,
                       st: Optional[str] = None,
                       rt: Optional[str] = None,
                       client_id: Optional[str] = None,
                       remark: Optional[str] = None,
                       update_if_exists: bool = False,
                       image_enabled: bool = True,
                       video_enabled: bool = True,
                       image_concurrency: int = -1,
                       video_concurrency: int = -1) -> Token:
        """Add a new Access Token to database

        Args:
            token_value: Access Token
            st: Session Token (optional)
            rt: Refresh Token (optional)
            client_id: Client ID (optional)
            remark: Remark (optional)
            update_if_exists: If True, update existing token instead of raising error
            image_enabled: Enable image generation (default: True)
            video_enabled: Enable video generation (default: True)
            image_concurrency: Image concurrency limit (-1 for no limit)
            video_concurrency: Video concurrency limit (-1 for no limit)

        Returns:
            Token object

        Raises:
            ValueError: If token already exists and update_if_exists is False
        """
        # Check if token already exists
        existing_token = await self.db.get_token_by_value(token_value)
        if existing_token:
            if not update_if_exists:
                raise ValueError(f"Token уже существует (email: {existing_token.email}). Для обновления сначала удалите старый Token или используйте функцию обновления.")
            # Update existing token
            return await self.update_existing_token(existing_token.id, token_value, st, rt, remark)

        # Decode JWT to get expiry time and email
        decoded = await self.decode_jwt(token_value)

        # Extract expiry time from JWT
        expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None

        # Extract email from JWT (OpenAI JWT format)
        jwt_email = None
        if "https://api.openai.com/profile" in decoded:
            jwt_email = decoded["https://api.openai.com/profile"].get("email")

        # Get user info from Sora API
        try:
            user_info = await self.get_user_info(token_value)
            email = user_info.get("email", jwt_email or "")
            name = user_info.get("name") or ""
        except Exception as e:
            # If API call fails, use JWT data
            email = jwt_email or ""
            name = email.split("@")[0] if email else ""

        # Get subscription info from Sora API
        plan_type = None
        plan_title = None
        subscription_end = None
        try:
            sub_info = await self.get_subscription_info(token_value)
            plan_type = sub_info.get("plan_type")
            plan_title = sub_info.get("plan_title")
            # Parse subscription end time
            if sub_info.get("subscription_end"):
                from dateutil import parser
                subscription_end = parser.parse(sub_info["subscription_end"])
        except Exception as e:
            error_msg = str(e)
            # Re-raise if it's a critical error (token expired)
            if "Token истёк" in error_msg:
                raise
            # If API call fails, subscription info will be None
            print(f"Failed to get subscription info: {e}")

        # Get Sora2 invite code
        sora2_supported = None
        sora2_invite_code = None
        sora2_redeemed_count = 0
        sora2_total_count = 0
        sora2_remaining_count = 0
        try:
            sora2_info = await self.get_sora2_invite_code(token_value)
            sora2_supported = sora2_info.get("supported", False)
            sora2_invite_code = sora2_info.get("invite_code")
            sora2_redeemed_count = sora2_info.get("redeemed_count", 0)
            sora2_total_count = sora2_info.get("total_count", 0)

            # If Sora2 is supported, get remaining count
            if sora2_supported:
                try:
                    remaining_info = await self.get_sora2_remaining_count(token_value)
                    if remaining_info.get("success"):
                        sora2_remaining_count = remaining_info.get("remaining_count", 0)
                        print(f"✅ Количество оставшихся попыток Sora2: {sora2_remaining_count}")
                except Exception as e:
                    print(f"Failed to get Sora2 remaining count: {e}")
        except Exception as e:
            error_msg = str(e)
            # Re-raise if it's a critical error (unsupported country)
            if "Sora недоступна в вашей стране" in error_msg:
                raise
            # If API call fails, Sora2 info will be None
            print(f"Failed to get Sora2 info: {e}")

        # Check and set username if needed
        try:
            # Get fresh user info to check username
            user_info = await self.get_user_info(token_value)
            username = user_info.get("username")

            # If username is null, need to set one
            if username is None:
                print(f"⚠️  Обнаружено пустое имя пользователя, требуется установка")

                # Generate random username
                max_attempts = 5
                for attempt in range(max_attempts):
                    generated_username = self._generate_random_username()
                    print(f"🔄 Попытка имени пользователя ({attempt + 1}/{max_attempts}): {generated_username}")

                    # Check if username is available
                    if await self.check_username_available(token_value, generated_username):
                        # Set the username
                        try:
                            await self.set_username(token_value, generated_username)
                            print(f"✅ Имя пользователя успешно установлено: {generated_username}")
                            break
                        except Exception as e:
                            print(f"❌ Не удалось установить имя пользователя: {e}")
                            if attempt == max_attempts - 1:
                                print(f"⚠️  Достигнуто максимальное количество попыток, пропуск установки имени")
                    else:
                        print(f"⚠️  Имя пользователя {generated_username} уже занято, пробуем следующее")
                        if attempt == max_attempts - 1:
                            print(f"⚠️  Достигнуто максимальное количество попыток, пропуск установки имени")
            else:
                print(f"✅ Имя пользователя уже установлено: {username}")
        except Exception as e:
            print(f"⚠️  Ошибка при проверке/установке имени пользователя: {e}")

        # Create token object
        token = Token(
            token=token_value,
            email=email,
            name=name,
            st=st,
            rt=rt,
            client_id=client_id,
            remark=remark,
            expiry_time=expiry_time,
            is_active=True,
            plan_type=plan_type,
            plan_title=plan_title,
            subscription_end=subscription_end,
            sora2_supported=sora2_supported,
            sora2_invite_code=sora2_invite_code,
            sora2_redeemed_count=sora2_redeemed_count,
            sora2_total_count=sora2_total_count,
            sora2_remaining_count=sora2_remaining_count,
            image_enabled=image_enabled,
            video_enabled=video_enabled,
            image_concurrency=image_concurrency,
            video_concurrency=video_concurrency
        )

        # Save to database
        token_id = await self.db.add_token(token)
        token.id = token_id

        return token

    async def update_existing_token(self, token_id: int, token_value: str,
                                    st: Optional[str] = None,
                                    rt: Optional[str] = None,
                                    remark: Optional[str] = None) -> Token:
        """Update an existing token with new information"""
        # Decode JWT to get expiry time
        decoded = await self.decode_jwt(token_value)
        expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None

        # Get user info from Sora API
        jwt_email = None
        if "https://api.openai.com/profile" in decoded:
            jwt_email = decoded["https://api.openai.com/profile"].get("email")

        try:
            user_info = await self.get_user_info(token_value)
            email = user_info.get("email", jwt_email or "")
            name = user_info.get("name", "")
        except Exception as e:
            email = jwt_email or ""
            name = email.split("@")[0] if email else ""

        # Get subscription info from Sora API
        plan_type = None
        plan_title = None
        subscription_end = None
        try:
            sub_info = await self.get_subscription_info(token_value)
            plan_type = sub_info.get("plan_type")
            plan_title = sub_info.get("plan_title")
            if sub_info.get("subscription_end"):
                from dateutil import parser
                subscription_end = parser.parse(sub_info["subscription_end"])
        except Exception as e:
            print(f"Failed to get subscription info: {e}")

        # Update token in database
        await self.db.update_token(
            token_id=token_id,
            token=token_value,
            st=st,
            rt=rt,
            remark=remark,
            expiry_time=expiry_time,
            plan_type=plan_type,
            plan_title=plan_title,
            subscription_end=subscription_end
        )

        # Get updated token
        updated_token = await self.db.get_token(token_id)
        return updated_token

    async def delete_token(self, token_id: int):
        """Delete a token"""
        await self.db.delete_token(token_id)

    async def update_token(self, token_id: int,
                          token: Optional[str] = None,
                          st: Optional[str] = None,
                          rt: Optional[str] = None,
                          client_id: Optional[str] = None,
                          remark: Optional[str] = None,
                          image_enabled: Optional[bool] = None,
                          video_enabled: Optional[bool] = None,
                          image_concurrency: Optional[int] = None,
                          video_concurrency: Optional[int] = None):
        """Update token (AT, ST, RT, client_id, remark, image_enabled, video_enabled, concurrency limits)"""
        # If token (AT) is updated, decode JWT to get new expiry time
        expiry_time = None
        if token:
            try:
                decoded = await self.decode_jwt(token)
                expiry_time = datetime.fromtimestamp(decoded.get("exp", 0)) if "exp" in decoded else None
            except Exception:
                pass  # If JWT decode fails, keep expiry_time as None

        await self.db.update_token(token_id, token=token, st=st, rt=rt, client_id=client_id, remark=remark, expiry_time=expiry_time,
                                   image_enabled=image_enabled, video_enabled=video_enabled,
                                   image_concurrency=image_concurrency, video_concurrency=video_concurrency)

    async def get_active_tokens(self) -> List[Token]:
        """Get all active tokens (not cooled down)"""
        return await self.db.get_active_tokens()
    
    async def get_all_tokens(self) -> List[Token]:
        """Get all tokens"""
        return await self.db.get_all_tokens()
    
    async def update_token_status(self, token_id: int, is_active: bool):
        """Update token active status"""
        await self.db.update_token_status(token_id, is_active)

    async def enable_token(self, token_id: int):
        """Enable a token and reset error count"""
        await self.db.update_token_status(token_id, True)
        # Reset error count when enabling (in token_stats table)
        await self.db.reset_error_count(token_id)

    async def disable_token(self, token_id: int):
        """Disable a token"""
        await self.db.update_token_status(token_id, False)

    async def test_token(self, token_id: int) -> dict:
        """Test if a token is valid by calling Sora API and refresh Sora2 info"""
        # Get token from database
        token_data = await self.db.get_token(token_id)
        if not token_data:
            return {"valid": False, "message": "Token not found"}

        try:
            # Try to get user info from Sora API
            user_info = await self.get_user_info(token_data.token)

            # Refresh Sora2 invite code and counts
            sora2_info = await self.get_sora2_invite_code(token_data.token)
            sora2_supported = sora2_info.get("supported", False)
            sora2_invite_code = sora2_info.get("invite_code")
            sora2_redeemed_count = sora2_info.get("redeemed_count", 0)
            sora2_total_count = sora2_info.get("total_count", 0)
            sora2_remaining_count = 0

            # If Sora2 is supported, get remaining count
            if sora2_supported:
                try:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token)
                    if remaining_info.get("success"):
                        sora2_remaining_count = remaining_info.get("remaining_count", 0)
                except Exception as e:
                    print(f"Failed to get Sora2 remaining count: {e}")

            # Update token Sora2 info in database
            await self.db.update_token_sora2(
                token_id,
                supported=sora2_supported,
                invite_code=sora2_invite_code,
                redeemed_count=sora2_redeemed_count,
                total_count=sora2_total_count,
                remaining_count=sora2_remaining_count
            )

            return {
                "valid": True,
                "message": "Token is valid",
                "email": user_info.get("email"),
                "username": user_info.get("username"),
                "sora2_supported": sora2_supported,
                "sora2_invite_code": sora2_invite_code,
                "sora2_redeemed_count": sora2_redeemed_count,
                "sora2_total_count": sora2_total_count,
                "sora2_remaining_count": sora2_remaining_count
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Token is invalid: {str(e)}"
            }

    async def record_usage(self, token_id: int, is_video: bool = False):
        """Record token usage"""
        await self.db.update_token_usage(token_id)
        
        if is_video:
            await self.db.increment_video_count(token_id)
        else:
            await self.db.increment_image_count(token_id)
    
    async def record_error(self, token_id: int):
        """Record token error"""
        await self.db.increment_error_count(token_id)

        # Check if should ban
        stats = await self.db.get_token_stats(token_id)
        admin_config = await self.db.get_admin_config()

        if stats and stats.consecutive_error_count >= admin_config.error_ban_threshold:
            await self.db.update_token_status(token_id, False)
    
    async def record_success(self, token_id: int, is_video: bool = False):
        """Record successful request (reset error count)"""
        await self.db.reset_error_count(token_id)

        # Update Sora2 remaining count after video generation
        if is_video:
            try:
                token_data = await self.db.get_token(token_id)
                if token_data and token_data.sora2_supported:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token)
                    if remaining_info.get("success"):
                        remaining_count = remaining_info.get("remaining_count", 0)
                        await self.db.update_token_sora2_remaining(token_id, remaining_count)
                        print(f"✅ Обновлено количество оставшихся попыток Sora2 для Token {token_id}: {remaining_count}")

                        # If remaining count is 0, set cooldown
                        if remaining_count == 0:
                            reset_seconds = remaining_info.get("access_resets_in_seconds", 0)
                            if reset_seconds > 0:
                                cooldown_until = datetime.now() + timedelta(seconds=reset_seconds)
                                await self.db.update_token_sora2_cooldown(token_id, cooldown_until)
                                print(f"⏱️ Token {token_id}: осталось 0 попыток, время охлаждения установлено до: {cooldown_until}")
            except Exception as e:
                print(f"Failed to update Sora2 remaining count: {e}")
    
    async def refresh_sora2_remaining_if_cooldown_expired(self, token_id: int):
        """Refresh Sora2 remaining count if cooldown has expired"""
        try:
            token_data = await self.db.get_token(token_id)
            if not token_data or not token_data.sora2_supported:
                return

            # Check if Sora2 cooldown has expired
            if token_data.sora2_cooldown_until and token_data.sora2_cooldown_until <= datetime.now():
                print(f"🔄 Token {token_id}: охлаждение Sora2 истекло, обновляем количество оставшихся попыток...")

                try:
                    remaining_info = await self.get_sora2_remaining_count(token_data.token)
                    if remaining_info.get("success"):
                        remaining_count = remaining_info.get("remaining_count", 0)
                        await self.db.update_token_sora2_remaining(token_id, remaining_count)
                        # Clear cooldown
                        await self.db.update_token_sora2_cooldown(token_id, None)
                        print(f"✅ Token {token_id}: количество оставшихся попыток Sora2 обновлено: {remaining_count}")
                except Exception as e:
                    print(f"Failed to refresh Sora2 remaining count: {e}")
        except Exception as e:
            print(f"Error in refresh_sora2_remaining_if_cooldown_expired: {e}")

    async def auto_refresh_expiring_token(self, token_id: int) -> bool:
        """
        Auto refresh token when expiry time is within 24 hours using ST or RT

        Returns:
            True if refresh successful, False otherwise
        """
        try:
            # 📍 Step 1: Получение данных Token
            debug_logger.log_info(f"[AUTO_REFRESH] Начало проверки Token {token_id}...")
            token_data = await self.db.get_token(token_id)

            if not token_data:
                debug_logger.log_info(f"[AUTO_REFRESH] ❌ Token {token_id} не существует")
                return False

            # 📍 Step 2: Проверка наличия времени истечения
            if not token_data.expiry_time:
                debug_logger.log_info(f"[AUTO_REFRESH] ⏭️  Token {token_id} без времени истечения, пропускаем обновление")
                return False  # No expiry time set

            # 📍 Step 3: Расчёт оставшегося времени
            time_until_expiry = token_data.expiry_time - datetime.now()
            hours_until_expiry = time_until_expiry.total_seconds() / 3600

            debug_logger.log_info(f"[AUTO_REFRESH] ⏰ Token {token_id} информация:")
            debug_logger.log_info(f"  - Email: {token_data.email}")
            debug_logger.log_info(f"  - Время истечения: {token_data.expiry_time.strftime('%Y-%m-%d %H:%M:%S')}")
            debug_logger.log_info(f"  - Оставшееся время: {hours_until_expiry:.2f} часов")
            debug_logger.log_info(f"  - Активен: {token_data.is_active}")
            debug_logger.log_info(f"  - Есть ST: {'да' if token_data.st else 'нет'}")
            debug_logger.log_info(f"  - Есть RT: {'да' if token_data.rt else 'нет'}")

            # 📍 Step 4: Проверка необходимости обновления
            if hours_until_expiry > 24:
                debug_logger.log_info(f"[AUTO_REFRESH] ⏭️  Token {token_id} оставшееся время > 24 часов, обновление не требуется")
                return False  # Token not expiring soon

            # 📍 Step 5: Запуск обновления
            if hours_until_expiry < 0:
                debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id} истёк, попытка автообновления...")
            else:
                debug_logger.log_info(f"[AUTO_REFRESH] 🟡 Token {token_id} истечёт через {hours_until_expiry:.2f} часов, попытка автообновления...")

            # Priority: ST > RT
            new_at = None
            new_st = None
            new_rt = None
            refresh_method = None

            # 📍 Step 6: Попытка обновления через ST
            if token_data.st:
                try:
                    debug_logger.log_info(f"[AUTO_REFRESH] 📝 Token {token_id}: попытка обновления через ST...")
                    result = await self.st_to_at(token_data.st)
                    new_at = result.get("access_token")
                    new_st = token_data.st  # ST refresh doesn't return new ST, so keep the old one
                    refresh_method = "ST"
                    debug_logger.log_info(f"[AUTO_REFRESH] ✅ Token {token_id}: обновление через ST успешно")
                except Exception as e:
                    debug_logger.log_info(f"[AUTO_REFRESH] ❌ Token {token_id}: обновление через ST не удалось - {str(e)}")
                    new_at = None

            # 📍 Step 7: Если ST не удалось, попытка RT
            if not new_at and token_data.rt:
                try:
                    debug_logger.log_info(f"[AUTO_REFRESH] 📝 Token {token_id}: попытка обновления через RT...")
                    result = await self.rt_to_at(token_data.rt, client_id=token_data.client_id)
                    new_at = result.get("access_token")
                    new_rt = result.get("refresh_token", token_data.rt)  # RT might be updated
                    refresh_method = "RT"
                    debug_logger.log_info(f"[AUTO_REFRESH] ✅ Token {token_id}: обновление через RT успешно")
                except Exception as e:
                    debug_logger.log_info(f"[AUTO_REFRESH] ❌ Token {token_id}: обновление через RT не удалось - {str(e)}")
                    new_at = None

            # 📍 Step 8: Обработка результата обновления
            if new_at:
                # Обновление успешно: обновляем Token
                debug_logger.log_info(f"[AUTO_REFRESH] 💾 Token {token_id}: сохранение нового Access Token...")
                await self.update_token(token_id, token=new_at, st=new_st, rt=new_rt)

                # Получение обновлённой информации о Token
                updated_token = await self.db.get_token(token_id)
                new_expiry_time = updated_token.expiry_time
                new_hours_until_expiry = ((new_expiry_time - datetime.now()).total_seconds() / 3600) if new_expiry_time else -1

                debug_logger.log_info(f"[AUTO_REFRESH] ✅ Token {token_id} автоматически обновлён успешно")
                debug_logger.log_info(f"  - Метод обновления: {refresh_method}")
                debug_logger.log_info(f"  - Новое время истечения: {new_expiry_time.strftime('%Y-%m-%d %H:%M:%S') if new_expiry_time else 'N/A'}")
                debug_logger.log_info(f"  - Новое оставшееся время: {new_hours_until_expiry:.2f} часов")

                # 📍 Step 9: Проверка времени истечения после обновления
                if new_hours_until_expiry < 0:
                    # Всё ещё истёк после обновления, отключаем Token
                    debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id}: всё ещё истёк после обновления (оставшееся время: {new_hours_until_expiry:.2f} часов), отключён")
                    await self.disable_token(token_id)
                    return False

                return True
            else:
                # Обновление не удалось: отключаем Token
                debug_logger.log_info(f"[AUTO_REFRESH] 🚫 Token {token_id}: не удалось обновить (нет действительного ST или RT), отключён")
                await self.disable_token(token_id)
                return False

        except Exception as e:
            debug_logger.log_info(f"[AUTO_REFRESH] 🔴 Token {token_id}: исключение при автоматическом обновлении - {str(e)}")
            return False
