"""Sora API client module"""
import base64
import io
import time
import random
import string
import re
from typing import Optional, Dict, Any, Tuple
from curl_cffi.requests import AsyncSession
from curl_cffi import CurlMime
from .proxy_manager import ProxyManager
from ..core.config import config
from ..core.logger import debug_logger

class SoraClient:
    """Sora API client with proxy support"""

    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.base_url = config.sora_base_url
        self.timeout = config.sora_timeout

    @staticmethod
    def _generate_sentinel_token() -> str:
        """
        Генерация openai-sentinel-token
        Согласно логике тестового файла, можно передать любую случайную строку
        Генерация случайной строки из 10-20 символов (буквы+цифры)
        """
        length = random.randint(10, 20)
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=length))
        return random_str

    @staticmethod
    def is_storyboard_prompt(prompt: str) -> bool:
        """Определяет, является ли промпт форматом покадрового режима

        Формат: [time]prompt или [time]prompt\n[time]prompt
        Пример: [5.0s]кошка прыгает с парашютом [5.0s]кошка приземляется

        Args:
            prompt: Введенный пользователем промпт

        Returns:
            True if prompt matches storyboard format
        """
        if not prompt:
            return False
        # Совпадение формата: [цифраs] или [цифра.цифраs]
        pattern = r'\[\d+(?:\.\d+)?s\]'
        matches = re.findall(pattern, prompt)
        # Должна быть хотя бы одна временная метка для режима раскадровки
        return len(matches) >= 1

    @staticmethod
    def format_storyboard_prompt(prompt: str) -> str:
        """Преобразование промпта формата раскадровки в формат API

        Вход: Волшебное приключение котика\n[5.0s]Котик прыгает с парашютом [5.0s]Котик приземляется
        Выход: current timeline:\nShot 1:...\n\ninstructions:\nВолшебное приключение котика

        Args:
            prompt: Исходный промпт в формате раскадровки

        Returns:
            Отформатированный промпт для API
        """
        # Совпадение шаблона [время]содержание
        pattern = r'\[(\d+(?:\.\d+)?)s\]\s*([^\[]+)'
        matches = re.findall(pattern, prompt)

        if not matches:
            return prompt

        # Извлечение общего описания (содержимое до первой [время])
        first_bracket_pos = prompt.find('[')
        instructions = ""
        if first_bracket_pos > 0:
            instructions = prompt[:first_bracket_pos].strip()

        # Форматирование кадров
        formatted_shots = []
        for idx, (duration, scene) in enumerate(matches, 1):
            scene = scene.strip()
            shot = f"Shot {idx}:\nduration: {duration}sec\nScene: {scene}"
            formatted_shots.append(shot)

        timeline = "\n\n".join(formatted_shots)

        # Если есть общее описание, добавляем секцию instructions
        if instructions:
            return f"current timeline:\n{timeline}\n\ninstructions:\n{instructions}"
        else:
            return timeline

    async def _make_request(self, method: str, endpoint: str, token: str,
                           json_data: Optional[Dict] = None,
                           multipart: Optional[Dict] = None,
                           add_sentinel_token: bool = False) -> Dict[str, Any]:
        """Make HTTP request with proxy support

        Args:
            method: HTTP method (GET/POST)
            endpoint: API endpoint
            token: Access token
            json_data: JSON request body
            multipart: Multipart form data (for file uploads)
            add_sentinel_token: Whether to add openai-sentinel-token header (only for generation requests)
        """
        proxy_url = await self.proxy_manager.get_proxy_url()

        headers = {
            "Authorization": f"Bearer {token}"
        }

        # Добавляем sentinel token только при запросах генерации
        if add_sentinel_token:
            headers["openai-sentinel-token"] = self._generate_sentinel_token()

        if not multipart:
            headers["Content-Type"] = "application/json"

        async with AsyncSession() as session:
            url = f"{self.base_url}{endpoint}"

            kwargs = {
                "headers": headers,
                "timeout": self.timeout,
                "impersonate": "chrome"  # Автоматическая генерация User-Agent и отпечатка браузера
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
                proxy=proxy_url
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
                duration_ms=duration_ms
            )

            # Check status
            if response.status_code not in [200, 201]:
                error_msg = f"API request failed: {response.status_code} - {response.text}"
                debug_logger.log_error(
                    error_message=error_msg,
                    status_code=response.status_code,
                    response_text=response.text
                )
                raise Exception(error_msg)

            return response_json if response_json else response.json()
    
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Get user information"""
        return await self._make_request("GET", "/me", token)
    
    async def upload_image(self, image_data: bytes, token: str, filename: str = "image.png") -> str:
        """Upload image and return media_id

        Использование объекта CurlMime для загрузки файлов (правильный способ для curl_cffi)
        Справка: https://curl-cffi.readthedocs.io/en/latest/quick_start.html#uploads
        """
        # Определение типа изображения
        mime_type = "image/png"
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            mime_type = "image/jpeg"
        elif filename.lower().endswith('.webp'):
            mime_type = "image/webp"

        # Создание объекта CurlMime
        mp = CurlMime()

        # Добавление части файла
        mp.addpart(
            name="file",
            content_type=mime_type,
            filename=filename,
            data=image_data
        )

        # Добавление поля с именем файла
        mp.addpart(
            name="file_name",
            data=filename.encode('utf-8')
        )

        result = await self._make_request("POST", "/uploads", token, multipart=mp)
        return result["id"]
    
    async def generate_image(self, prompt: str, token: str, width: int = 360,
                            height: int = 360, media_id: Optional[str] = None) -> str:
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

        # Для запроса генерации требуется добавить sentinel token
        result = await self._make_request("POST", "/video_gen", token, json_data=json_data, add_sentinel_token=True)
        return result["id"]
    
    async def generate_video(self, prompt: str, token: str, orientation: str = "landscape",
                            media_id: Optional[str] = None, n_frames: int = 450) -> str:
        """Generate video (text-to-video or image-to-video)"""
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
            "size": "small",
            "n_frames": n_frames,
            "model": "sy_8",
            "inpaint_items": inpaint_items
        }

        # Для запроса генерации требуется добавить sentinel token
        result = await self._make_request("POST", "/nf/create", token, json_data=json_data, add_sentinel_token=True)
        return result["id"]
    
    async def get_image_tasks(self, token: str, limit: int = 20) -> Dict[str, Any]:
        """Get recent image generation tasks"""
        return await self._make_request("GET", f"/v2/recent_tasks?limit={limit}", token)
    
    async def get_video_drafts(self, token: str, limit: int = 15) -> Dict[str, Any]:
        """Get recent video drafts"""
        return await self._make_request("GET", f"/project_y/profile/drafts?limit={limit}", token)

    async def get_pending_tasks(self, token: str) -> list:
        """Get pending video generation tasks

        Returns:
            List of pending tasks with progress information
        """
        result = await self._make_request("GET", "/nf/pending", token)
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

        # Для запроса публикации требуется добавить sentinel token
        result = await self._make_request("POST", "/project_y/post", token, json_data=json_data, add_sentinel_token=True)

        # Возвращаем post.id
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
                duration_ms=duration_ms
            )

            # Check status (DELETE typically returns 204 No Content or 200 OK)
            if response.status_code not in [200, 204]:
                error_msg = f"Delete post failed: {response.status_code} - {response.text}"
                debug_logger.log_error(
                    error_message=error_msg,
                    status_code=response.status_code,
                    response_text=response.text
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
                    duration_ms=duration_ms
                )

                # Check status
                if response.status_code != 200:
                    error_msg = f"Custom parse failed: {response.status_code} - {response.text}"
                    debug_logger.log_error(
                        error_message=error_msg,
                        status_code=response.status_code,
                        response_text=response.text
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
                        response_text=str(result)
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
                response_text=str(e)
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
                         orientation: str = "portrait", n_frames: int = 450) -> str:
        """Generate video using remix (based on existing video)

        Args:
            remix_target_id: The video ID from Sora share link (e.g., s_690d100857248191b679e6de12db840e)
            prompt: Generation prompt
            token: Access token
            orientation: Video orientation (portrait/landscape)
            n_frames: Number of frames

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
            "n_frames": n_frames
        }

        result = await self._make_request("POST", "/nf/create", token, json_data=json_data, add_sentinel_token=True)
        return result.get("id")

    async def generate_storyboard(self, prompt: str, token: str, orientation: str = "landscape",
                                 media_id: Optional[str] = None, n_frames: int = 450) -> str:
        """Generate video using storyboard mode

        Args:
            prompt: Formatted storyboard prompt (Shot 1:\nduration: 5.0sec\nScene: ...)
            token: Access token
            orientation: Video orientation (portrait/landscape)
            media_id: Optional image media_id for image-to-video
            n_frames: Number of frames

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
            "style_id": None,
            "cameo_ids": None,
            "cameo_replacements": None,
            "audio_caption": None,
            "audio_transcript": None,
            "video_caption": None
        }

        result = await self._make_request("POST", "/nf/create/storyboard", token, json_data=json_data, add_sentinel_token=True)
        return result.get("id")
