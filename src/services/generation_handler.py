"""Generation handling module"""
import json
import asyncio
import base64
import time
import random
import re
from typing import Optional, AsyncGenerator, Dict, Any
from datetime import datetime
from .sora_client import SoraClient
from .token_manager import TokenManager
from .load_balancer import LoadBalancer
from .file_cache import FileCache
from .concurrency_manager import ConcurrencyManager
from ..core.database import Database
from ..core.models import Task, RequestLog
from ..core.config import config
from ..core.logger import debug_logger

# Custom exception to carry token_id information
class GenerationError(Exception):
    """Custom exception for generation errors that includes token_id"""
    def __init__(self, message: str, token_id: Optional[int] = None):
        super().__init__(message)
        self.token_id = token_id

# Model configuration
MODEL_CONFIG = {
    "gpt-image": {
        "type": "image",
        "width": 360,
        "height": 360
    },
    "gpt-image-landscape": {
        "type": "image",
        "width": 540,
        "height": 360
    },
    "gpt-image-portrait": {
        "type": "image",
        "width": 360,
        "height": 540
    },
    # Video models with 10s duration (300 frames)
    "sora2-landscape-10s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 300
    },
    "sora2-portrait-10s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 300
    },
    # Video models with 15s duration (450 frames)
    "sora2-landscape-15s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 450
    },
    "sora2-portrait-15s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 450
    },
    # Video models with 25s duration (750 frames) - require Pro subscription
    "sora2-landscape-25s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 750,
        "model": "sy_8",
        "size": "small",
        "require_pro": True
    },
    "sora2-portrait-25s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 750,
        "model": "sy_8",
        "size": "small",
        "require_pro": True
    },
    # Pro video models (require Pro subscription)
    "sora2pro-landscape-10s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 300,
        "model": "sy_ore",
        "size": "small",
        "require_pro": True
    },
    "sora2pro-portrait-10s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 300,
        "model": "sy_ore",
        "size": "small",
        "require_pro": True
    },
    "sora2pro-landscape-15s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 450,
        "model": "sy_ore",
        "size": "small",
        "require_pro": True
    },
    "sora2pro-portrait-15s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 450,
        "model": "sy_ore",
        "size": "small",
        "require_pro": True
    },
    "sora2pro-landscape-25s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 750,
        "model": "sy_ore",
        "size": "small",
        "require_pro": True
    },
    "sora2pro-portrait-25s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 750,
        "model": "sy_ore",
        "size": "small",
        "require_pro": True
    },
    # Pro HD video models (require Pro subscription, high quality)
    "sora2pro-hd-landscape-10s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 300,
        "model": "sy_ore",
        "size": "large",
        "require_pro": True
    },
    "sora2pro-hd-portrait-10s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 300,
        "model": "sy_ore",
        "size": "large",
        "require_pro": True
    },
    "sora2pro-hd-landscape-15s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 450,
        "model": "sy_ore",
        "size": "large",
        "require_pro": True
    },
    "sora2pro-hd-portrait-15s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 450,
        "model": "sy_ore",
        "size": "large",
        "require_pro": True
    },
    # Prompt enhancement models
    "prompt-enhance-short-10s": {
        "type": "prompt_enhance",
        "expansion_level": "short",
        "duration_s": 10
    },
    "prompt-enhance-short-15s": {
        "type": "prompt_enhance",
        "expansion_level": "short",
        "duration_s": 15
    },
    "prompt-enhance-short-20s": {
        "type": "prompt_enhance",
        "expansion_level": "short",
        "duration_s": 20
    },
    "prompt-enhance-medium-10s": {
        "type": "prompt_enhance",
        "expansion_level": "medium",
        "duration_s": 10
    },
    "prompt-enhance-medium-15s": {
        "type": "prompt_enhance",
        "expansion_level": "medium",
        "duration_s": 15
    },
    "prompt-enhance-medium-20s": {
        "type": "prompt_enhance",
        "expansion_level": "medium",
        "duration_s": 20
    },
    "prompt-enhance-long-10s": {
        "type": "prompt_enhance",
        "expansion_level": "long",
        "duration_s": 10
    },
    "prompt-enhance-long-15s": {
        "type": "prompt_enhance",
        "expansion_level": "long",
        "duration_s": 15
    },
    "prompt-enhance-long-20s": {
        "type": "prompt_enhance",
        "expansion_level": "long",
        "duration_s": 20
    }
}

class GenerationHandler:
    """Handle generation requests"""

    def __init__(self, sora_client: SoraClient, token_manager: TokenManager,
                 load_balancer: LoadBalancer, db: Database, proxy_manager=None,
                 concurrency_manager: Optional[ConcurrencyManager] = None):
        self.sora_client = sora_client
        self.token_manager = token_manager
        self.load_balancer = load_balancer
        self.db = db
        self.concurrency_manager = concurrency_manager
        self.file_cache = FileCache(
            cache_dir="tmp",
            default_timeout=config.cache_timeout,
            proxy_manager=proxy_manager
        )

    def _get_base_url(self) -> str:
        """Get base URL for cache files"""
        # Use configured cache base URL if available
        if config.cache_base_url:
            return config.cache_base_url.rstrip('/')
        # Otherwise use server address
        return f"http://{config.server_host}:{config.server_port}"
    
    def _decode_base64_image(self, image_str: str) -> bytes:
        """Decode base64 image"""
        # Remove data URI prefix if present
        if "," in image_str:
            image_str = image_str.split(",", 1)[1]
        return base64.b64decode(image_str)

    def _decode_base64_video(self, video_str: str) -> bytes:
        """Decode base64 video"""
        # Remove data URI prefix if present
        if "," in video_str:
            video_str = video_str.split(",", 1)[1]
        return base64.b64decode(video_str)

    def _should_retry_on_error(self, error: Exception) -> bool:
        """判断错误是否应该触发重试

        Args:
            error: 捕获的异常

        Returns:
            True if should retry, False otherwise
        """
        error_str = str(error).lower()

        # 排除 CF Shield/429 错误（这些错误重试也会失败）
        if "cf_shield" in error_str or "cloudflare" in error_str:
            return False
        if "429" in error_str or "rate limit" in error_str:
            return False

        # 其他所有错误都可以重试
        return True

    def _process_character_username(self, username_hint: str) -> str:
        """Process character username from API response

        Logic:
        1. Remove prefix (e.g., "blackwill." from "blackwill.meowliusma68")
        2. Keep the remaining part (e.g., "meowliusma68")
        3. Append 3 random digits
        4. Return final username (e.g., "meowliusma68123")

        Args:
            username_hint: Original username from API (e.g., "blackwill.meowliusma68")

        Returns:
            Processed username with 3 random digits appended
        """
        # Split by dot and take the last part
        if "." in username_hint:
            base_username = username_hint.split(".")[-1]
        else:
            base_username = username_hint

        # Generate 3 random digits
        random_digits = str(random.randint(100, 999))

        # Return final username
        final_username = f"{base_username}{random_digits}"
        debug_logger.log_info(f"Processed username: {username_hint} -> {final_username}")

        return final_username

    def _clean_remix_link_from_prompt(self, prompt: str) -> str:
        """Remove remix link from prompt

        Removes both formats:
        1. Full URL: https://sora.chatgpt.com/p/s_68e3a06dcd888191b150971da152c1f5
        2. Short ID: s_68e3a06dcd888191b150971da152c1f5

        Args:
            prompt: Original prompt that may contain remix link

        Returns:
            Cleaned prompt without remix link
        """
        if not prompt:
            return prompt

        # Remove full URL format: https://sora.chatgpt.com/p/s_[a-f0-9]{32}
        cleaned = re.sub(r'https://sora\.chatgpt\.com/p/s_[a-f0-9]{32}', '', prompt)

        # Remove short ID format: s_[a-f0-9]{32}
        cleaned = re.sub(r's_[a-f0-9]{32}', '', cleaned)

        # Clean up extra whitespace
        cleaned = ' '.join(cleaned.split())

        debug_logger.log_info(f"Cleaned prompt: '{prompt}' -> '{cleaned}'")

        return cleaned

    def _extract_style(self, prompt: str) -> tuple[str, Optional[str]]:
        """Extract style from prompt

        Args:
            prompt: Original prompt

        Returns:
            Tuple of (cleaned_prompt, style_id)
        """
        # Valid style IDs
        VALID_STYLES = {
            "festive", "kakalaka", "news", "selfie", "handheld",
            "golden", "anime", "retro", "nostalgic", "comic"
        }

        # Extract {style} pattern
        match = re.search(r'\{([^}]+)\}', prompt)
        if match:
            style_candidate = match.group(1).strip()

            # Check if it's a single word (no spaces) and in valid styles list
            if ' ' not in style_candidate and style_candidate.lower() in VALID_STYLES:
                # Valid style found - remove {style} from prompt
                cleaned_prompt = re.sub(r'\{[^}]+\}', '', prompt).strip()
                # Clean up extra whitespace
                cleaned_prompt = ' '.join(cleaned_prompt.split())
                debug_logger.log_info(f"Extracted style: '{style_candidate}' from prompt: '{prompt}'")
                return cleaned_prompt, style_candidate.lower()
            else:
                # Not a valid style - treat as normal prompt
                debug_logger.log_info(f"'{style_candidate}' is not a valid style (contains spaces or not in style list), treating as normal prompt")
                return prompt, None

        return prompt, None

    async def _download_file(self, url: str) -> bytes:
        """Download file from URL

        Args:
            url: File URL

        Returns:
            File bytes
        """
        from curl_cffi.requests import AsyncSession

        proxy_url = await self.load_balancer.proxy_manager.get_proxy_url()

        kwargs = {
            "timeout": 30,
            "impersonate": "chrome"
        }

        if proxy_url:
            kwargs["proxy"] = proxy_url

        async with AsyncSession() as session:
            response = await session.get(url, **kwargs)
            if response.status_code != 200:
                raise Exception(f"Failed to download file: {response.status_code}")
            return response.content
    
    async def check_token_availability(self, is_image: bool, is_video: bool) -> bool:
        """Check if tokens are available for the given model type

        Args:
            is_image: Whether checking for image generation
            is_video: Whether checking for video generation

        Returns:
            True if available tokens exist, False otherwise
        """
        token_obj = await self.load_balancer.select_token(for_image_generation=is_image, for_video_generation=is_video)
        return token_obj is not None

    async def handle_generation(self, model: str, prompt: str,
                               image: Optional[str] = None,
                               video: Optional[str] = None,
                               remix_target_id: Optional[str] = None,
                               stream: bool = True) -> AsyncGenerator[str, None]:
        """Handle generation request

        Args:
            model: Model name
            prompt: Generation prompt
            image: Base64 encoded image
            video: Base64 encoded video or video URL
            remix_target_id: Sora share link video ID for remix
            stream: Whether to stream response
        """
        start_time = time.time()
        log_id = None  # Initialize log_id to avoid reference before assignment
        token_obj = None  # Initialize token_obj to avoid reference before assignment

        # Validate model
        if model not in MODEL_CONFIG:
            raise ValueError(f"Invalid model: {model}")

        model_config = MODEL_CONFIG[model]
        is_video = model_config["type"] == "video"
        is_image = model_config["type"] == "image"
        is_prompt_enhance = model_config["type"] == "prompt_enhance"

        # Handle prompt enhancement
        if is_prompt_enhance:
            async for chunk in self._handle_prompt_enhance(prompt, model_config, stream):
                yield chunk
            return

        # Non-streaming mode: only check availability
        if not stream:
            available = await self.check_token_availability(is_image, is_video)
            if available:
                if is_image:
                    message = "All tokens available for image generation. Please enable streaming to use the generation feature."
                else:
                    message = "All tokens available for video generation. Please enable streaming to use the generation feature."
            else:
                if is_image:
                    message = "No available models for image generation"
                else:
                    message = "No available models for video generation"

            yield self._format_non_stream_response(message, is_availability_check=True)
            return

        # Handle character creation and remix flows for video models
        if is_video:
            # Remix flow: remix_target_id provided
            if remix_target_id:
                async for chunk in self._handle_remix(remix_target_id, prompt, model_config):
                    yield chunk
                return

            # Character creation flow: video provided
            if video:
                # Decode video if it's base64
                video_data = self._decode_base64_video(video) if video.startswith("data:") or not video.startswith("http") else video

                # If no prompt, just create character and return
                if not prompt:
                    async for chunk in self._handle_character_creation_only(video_data, model_config):
                        yield chunk
                    return
                else:
                    # If prompt provided, create character and generate video
                    async for chunk in self._handle_character_and_video_generation(video_data, prompt, model_config):
                        yield chunk
                    return

        # Streaming mode: proceed with actual generation
        # Check if model requires Pro subscription
        require_pro = model_config.get("require_pro", False)

        # Select token (with lock for image generation, Sora2 quota check for video generation)
        # If Pro is required, filter for Pro tokens only
        token_obj = await self.load_balancer.select_token(
            for_image_generation=is_image,
            for_video_generation=is_video,
            require_pro=require_pro
        )
        if not token_obj:
            if require_pro:
                raise Exception("No available Pro tokens. Pro models require a ChatGPT Pro subscription.")
            elif is_image:
                raise Exception("No available tokens for image generation. All tokens are either disabled, cooling down, locked, or expired.")
            else:
                raise Exception("No available tokens for video generation. All tokens are either disabled, cooling down, Sora2 quota exhausted, don't support Sora2, or expired.")

        # Acquire lock for image generation
        if is_image:
            lock_acquired = await self.load_balancer.token_lock.acquire_lock(token_obj.id)
            if not lock_acquired:
                raise Exception(f"Failed to acquire lock for token {token_obj.id}")

            # Acquire concurrency slot for image generation
            if self.concurrency_manager:
                concurrency_acquired = await self.concurrency_manager.acquire_image(token_obj.id)
                if not concurrency_acquired:
                    await self.load_balancer.token_lock.release_lock(token_obj.id)
                    raise Exception(f"Failed to acquire concurrency slot for token {token_obj.id}")

        # Acquire concurrency slot for video generation
        if is_video and self.concurrency_manager:
            concurrency_acquired = await self.concurrency_manager.acquire_video(token_obj.id)
            if not concurrency_acquired:
                raise Exception(f"Failed to acquire concurrency slot for token {token_obj.id}")

        task_id = None
        is_first_chunk = True  # Track if this is the first chunk
        log_id = None  # Initialize log_id

        try:
            # Create initial log entry BEFORE submitting task to upstream
            # This ensures the log is created even if upstream fails
            log_id = await self._log_request(
                token_obj.id,
                f"generate_{model_config['type']}",
                {"model": model, "prompt": prompt, "has_image": image is not None},
                {},  # Empty response initially
                -1,  # -1 means in-progress
                -1.0,  # -1.0 means in-progress
                task_id=None  # Will be updated after task submission
            )

            # Upload image if provided
            media_id = None
            if image:
                if stream:
                    yield self._format_stream_chunk(
                        reasoning_content="**Image Upload Begins**\n\nUploading image to server...\n",
                        is_first=is_first_chunk
                    )
                    is_first_chunk = False

                image_data = self._decode_base64_image(image)
                media_id = await self.sora_client.upload_image(image_data, token_obj.token)

                if stream:
                    yield self._format_stream_chunk(
                        reasoning_content="Image uploaded successfully. Proceeding to generation...\n"
                    )

            # Generate
            if stream:
                if is_first_chunk:
                    yield self._format_stream_chunk(
                        reasoning_content="**Generation Process Begins**\n\nInitializing generation request...\n",
                        is_first=True
                    )
                    is_first_chunk = False
                else:
                    yield self._format_stream_chunk(
                        reasoning_content="**Generation Process Begins**\n\nInitializing generation request...\n"
                    )
            
            if is_video:
                # Get n_frames from model configuration
                n_frames = model_config.get("n_frames", 300)  # Default to 300 frames (10s)

                # Extract style from prompt
                clean_prompt, style_id = self._extract_style(prompt)

                # Check if prompt is in storyboard format
                if self.sora_client.is_storyboard_prompt(clean_prompt):
                    # Storyboard mode
                    if stream:
                        yield self._format_stream_chunk(
                            reasoning_content="Detected storyboard format. Converting to storyboard API format...\n"
                        )

                    formatted_prompt = self.sora_client.format_storyboard_prompt(clean_prompt)
                    debug_logger.log_info(f"Storyboard mode detected. Formatted prompt: {formatted_prompt}")

                    task_id = await self.sora_client.generate_storyboard(
                        formatted_prompt, token_obj.token,
                        orientation=model_config["orientation"],
                        media_id=media_id,
                        n_frames=n_frames,
                        style_id=style_id
                    )
                else:
                    # Normal video generation
                    # Get model and size from config (default to sy_8 and small for backward compatibility)
                    sora_model = model_config.get("model", "sy_8")
                    video_size = model_config.get("size", "small")

                    task_id = await self.sora_client.generate_video(
                        clean_prompt, token_obj.token,
                        orientation=model_config["orientation"],
                        media_id=media_id,
                        n_frames=n_frames,
                        style_id=style_id,
                        model=sora_model,
                        size=video_size,
                        token_id=token_obj.id
                    )
            else:
                task_id = await self.sora_client.generate_image(
                    prompt, token_obj.token,
                    width=model_config["width"],
                    height=model_config["height"],
                    media_id=media_id,
                    token_id=token_obj.id
                )

            # Save task to database
            task = Task(
                task_id=task_id,
                token_id=token_obj.id,
                model=model,
                prompt=prompt,
                status="processing",
                progress=0.0
            )
            await self.db.create_task(task)

            # Update log entry with task_id now that we have it
            if log_id:
                await self.db.update_request_log_task_id(log_id, task_id)

            # Record usage
            await self.token_manager.record_usage(token_obj.id, is_video=is_video)
            
            # Poll for results with timeout
            async for chunk in self._poll_task_result(task_id, token_obj.token, is_video, stream, prompt, token_obj.id, log_id, start_time):
                yield chunk
            
            # Record success
            await self.token_manager.record_success(token_obj.id, is_video=is_video)

            # Release lock for image generation
            if is_image:
                await self.load_balancer.token_lock.release_lock(token_obj.id)
                # Release concurrency slot for image generation
                if self.concurrency_manager:
                    await self.concurrency_manager.release_image(token_obj.id)

            # Release concurrency slot for video generation
            if is_video and self.concurrency_manager:
                await self.concurrency_manager.release_video(token_obj.id)

            # Log successful request with complete task info
            duration = time.time() - start_time

            # Get complete task info from database
            task_info = await self.db.get_task(task_id)
            response_data = {
                "task_id": task_id,
                "status": "success",
                "prompt": prompt,
                "model": model
            }

            # Add result_urls if available
            if task_info and task_info.result_urls:
                try:
                    result_urls = json.loads(task_info.result_urls)
                    response_data["result_urls"] = result_urls
                except:
                    response_data["result_urls"] = task_info.result_urls

            # Update log entry with completion data
            if log_id:
                await self.db.update_request_log(
                    log_id,
                    response_body=json.dumps(response_data),
                    status_code=200,
                    duration=duration
                )

        except Exception as e:
            # Release lock for image generation on error
            if is_image and token_obj:
                await self.load_balancer.token_lock.release_lock(token_obj.id)
                # Release concurrency slot for image generation
                if self.concurrency_manager:
                    await self.concurrency_manager.release_image(token_obj.id)

            # Release concurrency slot for video generation on error
            if is_video and token_obj and self.concurrency_manager:
                await self.concurrency_manager.release_video(token_obj.id)

            # Parse error message to check if it's a structured error (JSON)
            error_response = None
            try:
                error_response = json.loads(str(e))
            except:
                pass

            # Check for CF shield/429 error
            is_cf_or_429 = False
            if error_response and isinstance(error_response, dict):
                error_info = error_response.get("error", {})
                if error_info.get("code") == "cf_shield_429":
                    is_cf_or_429 = True

            # Record error (check if it's an overload error or CF/429 error)
            if token_obj:
                error_str = str(e).lower()
                is_overload = "heavy_load" in error_str or "under heavy load" in error_str
                # Don't record error for CF shield/429 (not token's fault)
                if not is_cf_or_429:
                    await self.token_manager.record_error(token_obj.id, is_overload=is_overload)

            # Update log entry with error data
            duration = time.time() - start_time
            if log_id:
                if error_response:
                    # Structured error (e.g., unsupported_country_code, cf_shield_429)
                    status_code = 429 if is_cf_or_429 else 400
                    await self.db.update_request_log(
                        log_id,
                        response_body=json.dumps(error_response),
                        status_code=status_code,
                        duration=duration
                    )
                else:
                    # Generic error
                    await self.db.update_request_log(
                        log_id,
                        response_body=json.dumps({"error": str(e)}),
                        status_code=500,
                        duration=duration
                    )
            # Wrap exception with token_id information
            if token_obj:
                raise GenerationError(str(e), token_id=token_obj.id)
            else:
                raise e

    async def handle_generation_with_retry(self, model: str, prompt: str,
                                          image: Optional[str] = None,
                                          video: Optional[str] = None,
                                          remix_target_id: Optional[str] = None,
                                          stream: bool = True) -> AsyncGenerator[str, None]:
        """Handle generation request with automatic retry on failure

        Args:
            model: Model name
            prompt: Generation prompt
            image: Base64 encoded image
            video: Base64 encoded video or video URL
            remix_target_id: Sora share link video ID for remix
            stream: Whether to stream response
        """
        # Get admin config for retry settings
        admin_config = await self.db.get_admin_config()
        retry_enabled = admin_config.task_retry_enabled
        max_retries = admin_config.task_max_retries if retry_enabled else 0
        auto_disable_on_401 = admin_config.auto_disable_on_401

        retry_count = 0
        last_error = None
        last_token_id = None  # Track the token that caused the error

        while retry_count <= max_retries:
            try:
                # Try generation
                async for chunk in self.handle_generation(model, prompt, image, video, remix_target_id, stream):
                    yield chunk
                # If successful, return
                return

            except Exception as e:
                last_error = e
                error_str = str(e)

                # Extract token_id from GenerationError if available
                if isinstance(e, GenerationError) and e.token_id:
                    last_token_id = e.token_id

                # Check if this is a 401 error
                is_401_error = "401" in error_str or "unauthorized" in error_str.lower() or "token_invalidated" in error_str.lower()

                # If 401 error and auto-disable is enabled, disable the token
                if is_401_error and auto_disable_on_401 and last_token_id:
                    debug_logger.log_info(f"Detected 401 error, auto-disabling token {last_token_id}")
                    try:
                        await self.db.update_token_status(last_token_id, False)
                        if stream:
                            yield self._format_stream_chunk(
                                reasoning_content=f"**检测到401错误，已自动禁用Token {last_token_id}**\\n\\n正在使用其他Token重试...\\n\\n"
                            )
                    except Exception as disable_error:
                        debug_logger.log_error(
                            error_message=f"Failed to disable token {last_token_id}: {str(disable_error)}",
                            status_code=500,
                            response_text=str(disable_error)
                        )

                # Check if we should retry
                should_retry = (
                    retry_enabled and
                    retry_count < max_retries and
                    self._should_retry_on_error(e)
                )

                if should_retry:
                    retry_count += 1
                    debug_logger.log_info(f"Generation failed, retrying ({retry_count}/{max_retries}): {str(e)}")

                    # Send retry notification to user if streaming
                    if stream:
                        yield self._format_stream_chunk(
                            reasoning_content=f"**生成失败，正在重试**\\n\\n第 {retry_count} 次重试（共 {max_retries} 次）...\\n\\n失败原因：{str(e)}\\n\\n"
                        )

                    # Small delay before retry
                    await asyncio.sleep(2)
                else:
                    # No more retries, raise the error
                    raise last_error

        # If we exhausted all retries, raise the last error
        if last_error:
            raise last_error

    async def _poll_task_result(self, task_id: str, token: str, is_video: bool,
                                stream: bool, prompt: str, token_id: int = None,
                                log_id: int = None, start_time: float = None) -> AsyncGenerator[str, None]:
        """Poll for task result with timeout"""
        # Get timeout from config
        timeout = config.video_timeout if is_video else config.image_timeout
        poll_interval = config.poll_interval
        max_attempts = int(timeout / poll_interval)  # Calculate max attempts based on timeout
        last_progress = 0
        start_time = time.time()
        last_heartbeat_time = start_time  # Track last heartbeat for image generation
        heartbeat_interval = 10  # Send heartbeat every 10 seconds for image generation
        last_status_output_time = start_time  # Track last status output time for video generation
        video_status_interval = 30  # Output status every 30 seconds for video generation

        debug_logger.log_info(f"Starting task polling: task_id={task_id}, is_video={is_video}, timeout={timeout}s, max_attempts={max_attempts}")

        # Check and log watermark-free mode status at the beginning
        if is_video:
            watermark_free_config = await self.db.get_watermark_free_config()
            debug_logger.log_info(f"Watermark-free mode: {'ENABLED' if watermark_free_config.watermark_free_enabled else 'DISABLED'}")

        for attempt in range(max_attempts):
            # Check if timeout exceeded
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                debug_logger.log_error(
                    error_message=f"Task timeout: {elapsed_time:.1f}s > {timeout}s",
                    status_code=408,
                    response_text=f"Task {task_id} timed out after {elapsed_time:.1f} seconds"
                )
                # Release lock if this is an image generation task
                if not is_video and token_id:
                    await self.load_balancer.token_lock.release_lock(token_id)
                    debug_logger.log_info(f"Released lock for token {token_id} due to timeout")
                    # Release concurrency slot for image generation
                    if self.concurrency_manager:
                        await self.concurrency_manager.release_image(token_id)
                        debug_logger.log_info(f"Released concurrency slot for token {token_id} due to timeout")

                # Release concurrency slot for video generation
                if is_video and token_id and self.concurrency_manager:
                    await self.concurrency_manager.release_video(token_id)
                    debug_logger.log_info(f"Released concurrency slot for token {token_id} due to timeout")

                # Update task status to failed
                await self.db.update_task(task_id, "failed", 0, error_message=f"Generation timeout after {elapsed_time:.1f} seconds")

                # Update request log with timeout error
                if log_id and start_time:
                    duration = time.time() - start_time
                    await self.db.update_request_log(
                        log_id,
                        response_body=json.dumps({"error": f"Generation timeout after {elapsed_time:.1f} seconds"}),
                        status_code=408,
                        duration=duration
                    )

                raise Exception(f"Upstream API timeout: Generation exceeded {timeout} seconds limit")


            await asyncio.sleep(poll_interval)

            try:
                if is_video:
                    # Get pending tasks to check progress
                    pending_tasks = await self.sora_client.get_pending_tasks(token, token_id=token_id)

                    # Find matching task in pending tasks
                    task_found = False
                    for task in pending_tasks:
                        if task.get("id") == task_id:
                            task_found = True
                            # Update progress
                            progress_pct = task.get("progress_pct")
                            # Handle null progress at the beginning
                            if progress_pct is None:
                                progress_pct = 0
                            else:
                                progress_pct = int(progress_pct * 100)

                            # Update last_progress for tracking
                            last_progress = progress_pct
                            status = task.get("status", "processing")

                            # Update database with current progress
                            await self.db.update_task(task_id, "processing", progress_pct)

                            # Output status every 30 seconds (not just when progress changes)
                            current_time = time.time()
                            if stream and (current_time - last_status_output_time >= video_status_interval):
                                last_status_output_time = current_time
                                debug_logger.log_info(f"Task {task_id} progress: {progress_pct}% (status: {status})")
                                yield self._format_stream_chunk(
                                    reasoning_content=f"**Video Generation Progress**: {progress_pct}% ({status})\n"
                                )
                            break

                    # If task not found in pending tasks, it's completed - fetch from drafts
                    if not task_found:
                        debug_logger.log_info(f"Task {task_id} not found in pending tasks, fetching from drafts...")
                        result = await self.sora_client.get_video_drafts(token, token_id=token_id)
                        items = result.get("items", [])

                        # Find matching task in drafts
                        for item in items:
                            if item.get("task_id") == task_id:
                                # Check for content violation
                                kind = item.get("kind")
                                reason_str = item.get("reason_str") or item.get("markdown_reason_str")
                                url = item.get("url") or item.get("downloadable_url")
                                debug_logger.log_info(f"Found task {task_id} in drafts with kind: {kind}, reason_str: {reason_str}, has_url: {bool(url)}")

                                # Check if content violates policy
                                # Violation indicators: kind is violation type, or has reason_str, or missing video URL
                                is_violation = (
                                    kind == "sora_content_violation" or
                                    (reason_str and reason_str.strip()) or  # Has non-empty reason
                                    not url  # No video URL means generation failed
                                )

                                if is_violation:
                                    error_message = f"Content policy violation: {reason_str or 'Content violates guardrails'}"

                                    debug_logger.log_error(
                                        error_message=error_message,
                                        status_code=400,
                                        response_text=json.dumps(item)
                                    )

                                    # Update task status
                                    await self.db.update_task(task_id, "failed", 0, error_message=error_message)

                                    # Release resources
                                    if token_id and self.concurrency_manager:
                                        await self.concurrency_manager.release_video(token_id)
                                        debug_logger.log_info(f"Released concurrency slot for token {token_id} due to content violation")

                                    # Return error in stream format
                                    if stream:
                                        yield self._format_stream_chunk(
                                            reasoning_content=f"**Content Policy Violation**\n\n{reason_str}\n"
                                        )
                                        yield self._format_stream_chunk(
                                            content=f"❌ 生成失败: {reason_str}",
                                            finish_reason="STOP"
                                        )
                                        yield "data: [DONE]\n\n"

                                    # Stop polling immediately
                                    return

                                # Check if watermark-free mode is enabled
                                watermark_free_config = await self.db.get_watermark_free_config()
                                watermark_free_enabled = watermark_free_config.watermark_free_enabled

                                if watermark_free_enabled:
                                    # Watermark-free mode: post video and get watermark-free URL
                                    debug_logger.log_info(f"Entering watermark-free mode for task {task_id}")
                                    generation_id = item.get("id")
                                    debug_logger.log_info(f"Generation ID: {generation_id}")
                                    if not generation_id:
                                        raise Exception("Generation ID not found in video draft")

                                    if stream:
                                        yield self._format_stream_chunk(
                                            reasoning_content="**Video Generation Completed**\n\nWatermark-free mode enabled. Publishing video to get watermark-free version...\n"
                                        )

                                    # Get watermark-free config to determine parse method
                                    watermark_config = await self.db.get_watermark_free_config()
                                    parse_method = watermark_config.parse_method or "third_party"

                                    # Post video to get watermark-free version
                                    try:
                                        debug_logger.log_info(f"Calling post_video_for_watermark_free with generation_id={generation_id}, prompt={prompt[:50]}...")
                                        post_id = await self.sora_client.post_video_for_watermark_free(
                                            generation_id=generation_id,
                                            prompt=prompt,
                                            token=token
                                        )
                                        debug_logger.log_info(f"Received post_id: {post_id}")

                                        if not post_id:
                                            raise Exception("Failed to get post ID from publish API")

                                        # Get watermark-free video URL based on parse method
                                        if parse_method == "custom":
                                            # Use custom parse server
                                            if not watermark_config.custom_parse_url or not watermark_config.custom_parse_token:
                                                raise Exception("Custom parse server URL or token not configured")

                                            if stream:
                                                yield self._format_stream_chunk(
                                                    reasoning_content=f"Video published successfully. Post ID: {post_id}\nUsing custom parse server to get watermark-free URL...\n"
                                                )

                                            debug_logger.log_info(f"Using custom parse server: {watermark_config.custom_parse_url}")
                                            watermark_free_url = await self.sora_client.get_watermark_free_url_custom(
                                                parse_url=watermark_config.custom_parse_url,
                                                parse_token=watermark_config.custom_parse_token,
                                                post_id=post_id
                                            )
                                        else:
                                            # Use third-party parse (default)
                                            watermark_free_url = f"https://oscdn2.dyysy.com/MP4/{post_id}.mp4"
                                            debug_logger.log_info(f"Using third-party parse server")

                                        debug_logger.log_info(f"Watermark-free URL: {watermark_free_url}")

                                        if stream:
                                            yield self._format_stream_chunk(
                                                reasoning_content=f"Video published successfully. Post ID: {post_id}\nNow {'caching' if config.cache_enabled else 'preparing'} watermark-free video...\n"
                                            )

                                        # Cache watermark-free video (if cache enabled)
                                        if config.cache_enabled:
                                            try:
                                                cached_filename = await self.file_cache.download_and_cache(watermark_free_url, "video", token_id=token_id)
                                                local_url = f"{self._get_base_url()}/tmp/{cached_filename}"
                                                if stream:
                                                    yield self._format_stream_chunk(
                                                        reasoning_content="Watermark-free video cached successfully. Preparing final response...\n"
                                                    )

                                                # Delete the published post after caching
                                                try:
                                                    debug_logger.log_info(f"Deleting published post: {post_id}")
                                                    await self.sora_client.delete_post(post_id, token)
                                                    debug_logger.log_info(f"Published post deleted successfully: {post_id}")
                                                    if stream:
                                                        yield self._format_stream_chunk(
                                                            reasoning_content="Published post deleted successfully.\n"
                                                        )
                                                except Exception as delete_error:
                                                    debug_logger.log_error(
                                                        error_message=f"Failed to delete published post {post_id}: {str(delete_error)}",
                                                        status_code=500,
                                                        response_text=str(delete_error)
                                                    )
                                                    if stream:
                                                        yield self._format_stream_chunk(
                                                            reasoning_content=f"Warning: Failed to delete published post - {str(delete_error)}\n"
                                                        )
                                            except Exception as cache_error:
                                                # Fallback to watermark-free URL if caching fails
                                                local_url = watermark_free_url
                                                if stream:
                                                    yield self._format_stream_chunk(
                                                        reasoning_content=f"Warning: Failed to cache file - {str(cache_error)}\nUsing original watermark-free URL instead...\n"
                                                    )
                                        else:
                                            # Cache disabled: use watermark-free URL directly
                                            local_url = watermark_free_url
                                            if stream:
                                                yield self._format_stream_chunk(
                                                    reasoning_content="Cache is disabled. Using watermark-free URL directly...\n"
                                                )

                                    except Exception as publish_error:
                                        # Fallback to normal mode if publish fails
                                        debug_logger.log_error(
                                            error_message=f"Watermark-free mode failed: {str(publish_error)}",
                                            status_code=500,
                                            response_text=str(publish_error)
                                        )
                                        if stream:
                                            yield self._format_stream_chunk(
                                                reasoning_content=f"Warning: Failed to get watermark-free version - {str(publish_error)}\nFalling back to normal video...\n"
                                            )
                                        # Use downloadable_url instead of url
                                        url = item.get("downloadable_url") or item.get("url")
                                        if not url:
                                            raise Exception("Video URL not found")
                                        if config.cache_enabled:
                                            try:
                                                cached_filename = await self.file_cache.download_and_cache(url, "video", token_id=token_id)
                                                local_url = f"{self._get_base_url()}/tmp/{cached_filename}"
                                            except Exception as cache_error:
                                                local_url = url
                                        else:
                                            local_url = url
                                else:
                                    # Normal mode: use downloadable_url instead of url
                                    url = item.get("downloadable_url") or item.get("url")
                                    if url:
                                        # Cache video file (if cache enabled)
                                        if config.cache_enabled:
                                            if stream:
                                                yield self._format_stream_chunk(
                                                    reasoning_content="**Video Generation Completed**\n\nVideo generation successful. Now caching the video file...\n"
                                                )

                                            try:
                                                cached_filename = await self.file_cache.download_and_cache(url, "video", token_id=token_id)
                                                local_url = f"{self._get_base_url()}/tmp/{cached_filename}"
                                                if stream:
                                                    yield self._format_stream_chunk(
                                                        reasoning_content="Video file cached successfully. Preparing final response...\n"
                                                    )
                                            except Exception as cache_error:
                                                # Fallback to original URL if caching fails
                                                local_url = url
                                                if stream:
                                                    yield self._format_stream_chunk(
                                                        reasoning_content=f"Warning: Failed to cache file - {str(cache_error)}\nUsing original URL instead...\n"
                                                    )
                                        else:
                                            # Cache disabled: use original URL directly
                                            local_url = url
                                            if stream:
                                                yield self._format_stream_chunk(
                                                    reasoning_content="**Video Generation Completed**\n\nCache is disabled. Using original URL directly...\n"
                                                )

                                # Task completed
                                await self.db.update_task(
                                    task_id, "completed", 100.0,
                                    result_urls=json.dumps([local_url])
                                )

                                if stream:
                                    # Final response with content
                                    yield self._format_stream_chunk(
                                        content=f"```html\n<video src='{local_url}' controls></video>\n```",
                                        finish_reason="STOP"
                                    )
                                    yield "data: [DONE]\n\n"
                                return
                else:
                    result = await self.sora_client.get_image_tasks(token, token_id=token_id)
                    task_responses = result.get("task_responses", [])

                    # Find matching task
                    task_found = False
                    for task_resp in task_responses:
                        if task_resp.get("id") == task_id:
                            task_found = True
                            status = task_resp.get("status")
                            progress = task_resp.get("progress_pct", 0) * 100

                            if status == "succeeded":
                                # Extract URLs
                                generations = task_resp.get("generations", [])
                                urls = [gen.get("url") for gen in generations if gen.get("url")]

                                if urls:
                                    # Cache image files
                                    if stream:
                                        yield self._format_stream_chunk(
                                            reasoning_content=f"**Image Generation Completed**\n\nImage generation successful. Now caching {len(urls)} image(s)...\n"
                                        )

                                    base_url = self._get_base_url()
                                    local_urls = []

                                    # Check if cache is enabled
                                    if config.cache_enabled:
                                        for idx, url in enumerate(urls):
                                            try:
                                                cached_filename = await self.file_cache.download_and_cache(url, "image", token_id=token_id)
                                                local_url = f"{base_url}/tmp/{cached_filename}"
                                                local_urls.append(local_url)
                                                if stream and len(urls) > 1:
                                                    yield self._format_stream_chunk(
                                                        reasoning_content=f"Cached image {idx + 1}/{len(urls)}...\n"
                                                    )
                                            except Exception as cache_error:
                                                # Fallback to original URL if caching fails
                                                local_urls.append(url)
                                                if stream:
                                                    yield self._format_stream_chunk(
                                                        reasoning_content=f"Warning: Failed to cache image {idx + 1} - {str(cache_error)}\nUsing original URL instead...\n"
                                                    )

                                        if stream and all(u.startswith(base_url) for u in local_urls):
                                            yield self._format_stream_chunk(
                                                reasoning_content="All images cached successfully. Preparing final response...\n"
                                            )
                                    else:
                                        # Cache disabled: use original URLs directly
                                        local_urls = urls
                                        if stream:
                                            yield self._format_stream_chunk(
                                                reasoning_content="Cache is disabled. Using original URLs directly...\n"
                                            )

                                    await self.db.update_task(
                                        task_id, "completed", 100.0,
                                        result_urls=json.dumps(local_urls)
                                    )

                                    if stream:
                                        # Final response with content (Markdown format)
                                        content_markdown = "\n".join([f"![Generated Image]({url})" for url in local_urls])
                                        yield self._format_stream_chunk(
                                            content=content_markdown,
                                            finish_reason="STOP"
                                        )
                                        yield "data: [DONE]\n\n"
                                    return

                            elif status == "failed":
                                error_msg = task_resp.get("error_message", "Generation failed")
                                await self.db.update_task(task_id, "failed", progress, error_message=error_msg)
                                raise Exception(error_msg)

                            elif status == "processing":
                                # Update progress only if changed significantly
                                if progress > last_progress + 20:  # Update every 20%
                                    last_progress = progress
                                    await self.db.update_task(task_id, "processing", progress)

                                    if stream:
                                        yield self._format_stream_chunk(
                                            reasoning_content=f"**Processing**\n\nGeneration in progress: {progress:.0f}% completed...\n"
                                        )

                    # For image generation, send heartbeat every 10 seconds if no progress update
                    if not is_video and stream:
                        current_time = time.time()
                        if current_time - last_heartbeat_time >= heartbeat_interval:
                            last_heartbeat_time = current_time
                            elapsed = int(current_time - start_time)
                            yield self._format_stream_chunk(
                                reasoning_content=f"Image generation in progress... ({elapsed}s elapsed)\n"
                            )

                    # If task not found in response, send heartbeat for image generation
                    if not task_found and not is_video and stream:
                        current_time = time.time()
                        if current_time - last_heartbeat_time >= heartbeat_interval:
                            last_heartbeat_time = current_time
                            elapsed = int(current_time - start_time)
                            yield self._format_stream_chunk(
                                reasoning_content=f"Image generation in progress... ({elapsed}s elapsed)\n"
                            )

                # Progress update for stream mode (fallback if no status from API)
                if stream and attempt % 10 == 0:  # Update every 10 attempts (roughly 20% intervals)
                    estimated_progress = min(90, (attempt / max_attempts) * 100)
                    if estimated_progress > last_progress + 20:  # Update every 20%
                        last_progress = estimated_progress
                        yield self._format_stream_chunk(
                            reasoning_content=f"**Processing**\n\nGeneration in progress: {estimated_progress:.0f}% completed (estimated)...\n"
                        )
            
            except Exception as e:
                # Check for CF shield/429 error - don't retry these
                error_str = str(e)
                is_cf_or_429 = False
                try:
                    error_response = json.loads(error_str)
                    if isinstance(error_response, dict):
                        error_info = error_response.get("error", {})
                        if error_info.get("code") == "cf_shield_429":
                            is_cf_or_429 = True
                except (json.JSONDecodeError, ValueError):
                    pass

                # CF shield/429 detected - fail immediately
                if is_cf_or_429:
                    debug_logger.log_error(
                        error_message="CF Shield/429 detected during polling, failing task immediately",
                        status_code=429,
                        response_text=error_str
                    )
                    # Update task status to failed
                    await self.db.update_task(task_id, "failed", 0, error_message="Cloudflare challenge or rate limit (429) triggered")

                    # Update request log with CF/429 error
                    if log_id and start_time:
                        duration = time.time() - start_time
                        await self.db.update_request_log(
                            log_id,
                            response_body=json.dumps({"error": "Cloudflare challenge or rate limit (429) triggered"}),
                            status_code=429,
                            duration=duration
                        )

                    # Release resources
                    if not is_video and token_id:
                        await self.load_balancer.token_lock.release_lock(token_id)
                        if self.concurrency_manager:
                            await self.concurrency_manager.release_image(token_id)
                    if is_video and token_id and self.concurrency_manager:
                        await self.concurrency_manager.release_video(token_id)

                    # Send error message to client if streaming
                    if stream:
                        yield self._format_stream_chunk(
                            reasoning_content="**CF Shield/429 Error**\\n\\nCloudflare challenge or rate limit (429) triggered\\n"
                        )
                        yield self._format_stream_chunk(
                            content="❌ Generation failed: Cloudflare challenge or rate limit (429) triggered. Please change proxy or reduce request frequency.",
                            finish_reason="STOP"
                        )
                        yield "data: [DONE]\\n\\n"

                    # Exit polling immediately
                    return

                # For other errors, retry if not last attempt
                if attempt >= max_attempts - 1:
                    raise e
                continue

        # Timeout - release lock if image generation
        if not is_video and token_id:
            await self.load_balancer.token_lock.release_lock(token_id)
            debug_logger.log_info(f"Released lock for token {token_id} due to max attempts reached")
            # Release concurrency slot for image generation
            if self.concurrency_manager:
                await self.concurrency_manager.release_image(token_id)
                debug_logger.log_info(f"Released concurrency slot for token {token_id} due to max attempts reached")

        # Release concurrency slot for video generation
        if is_video and token_id and self.concurrency_manager:
            await self.concurrency_manager.release_video(token_id)
            debug_logger.log_info(f"Released concurrency slot for token {token_id} due to max attempts reached")

        await self.db.update_task(task_id, "failed", 0, error_message=f"Generation timeout after {timeout} seconds")
        raise Exception(f"Upstream API timeout: Generation exceeded {timeout} seconds limit")
    
    def _format_stream_chunk(self, content: str = None, reasoning_content: str = None,
                            finish_reason: str = None, is_first: bool = False) -> str:
        """Format streaming response chunk

        Args:
            content: Final response content (for user-facing output)
            reasoning_content: Thinking/reasoning process content
            finish_reason: Finish reason (e.g., "STOP")
            is_first: Whether this is the first chunk (includes role)
        """
        chunk_id = f"chatcmpl-{int(datetime.now().timestamp() * 1000)}"

        delta = {}

        # Add role for first chunk
        if is_first:
            delta["role"] = "assistant"

        # Add content fields
        if content is not None:
            delta["content"] = content
        else:
            delta["content"] = None

        if reasoning_content is not None:
            delta["reasoning_content"] = reasoning_content
        else:
            delta["reasoning_content"] = None

        delta["tool_calls"] = None

        response = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(datetime.now().timestamp()),
            "model": "sora",
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
                "native_finish_reason": finish_reason
            }],
            "usage": {
                "prompt_tokens": 0
            }
        }

        # Add completion tokens for final chunk
        if finish_reason:
            response["usage"]["completion_tokens"] = 1
            response["usage"]["total_tokens"] = 1

        return f'data: {json.dumps(response)}\n\n'
    
    def _format_non_stream_response(self, content: str, media_type: str = None, is_availability_check: bool = False) -> str:
        """Format non-streaming response

        Args:
            content: Response content (either URL for generation or message for availability check)
            media_type: Type of media ("video", "image") - only used for generation responses
            is_availability_check: Whether this is an availability check response
        """
        if not is_availability_check:
            # Generation response with media
            if media_type == "video":
                content = f"```html\n<video src='{content}' controls></video>\n```"
            else:
                content = f"![Generated Image]({content})"

        response = {
            "id": f"chatcmpl-{datetime.now().timestamp()}",
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": "sora",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }]
        }
        return json.dumps(response)

    async def _log_request(self, token_id: Optional[int], operation: str,
                          request_data: Dict[str, Any], response_data: Dict[str, Any],
                          status_code: int, duration: float, task_id: Optional[str] = None) -> Optional[int]:
        """Log request to database and return log ID"""
        try:
            log = RequestLog(
                token_id=token_id,
                task_id=task_id,
                operation=operation,
                request_body=json.dumps(request_data),
                response_body=json.dumps(response_data),
                status_code=status_code,
                duration=duration
            )
            return await self.db.log_request(log)
        except Exception as e:
            # Don't fail the request if logging fails
            print(f"Failed to log request: {e}")
            return None

    # ==================== Prompt Enhancement Handler ====================

    async def _handle_prompt_enhance(self, prompt: str, model_config: Dict, stream: bool) -> AsyncGenerator[str, None]:
        """Handle prompt enhancement request

        Args:
            prompt: Original prompt to enhance
            model_config: Model configuration
            stream: Whether to stream response
        """
        expansion_level = model_config["expansion_level"]
        duration_s = model_config["duration_s"]

        # Select token
        token_obj = await self.load_balancer.select_token(for_video_generation=True)
        if not token_obj:
            error_msg = "No available tokens for prompt enhancement"
            if stream:
                yield self._format_stream_chunk(reasoning_content=f"**Error:** {error_msg}", is_first=True)
                yield self._format_stream_chunk(finish_reason="STOP")
            else:
                yield self._format_non_stream_response(error_msg)
            return

        try:
            # Call enhance_prompt API
            enhanced_prompt = await self.sora_client.enhance_prompt(
                prompt=prompt,
                token=token_obj.token,
                expansion_level=expansion_level,
                duration_s=duration_s,
                token_id=token_obj.id
            )

            if stream:
                # Stream response
                yield self._format_stream_chunk(
                    content=enhanced_prompt,
                    is_first=True
                )
                yield self._format_stream_chunk(finish_reason="STOP")
            else:
                # Non-stream response
                yield self._format_non_stream_response(enhanced_prompt)

        except Exception as e:
            error_msg = f"Prompt enhancement failed: {str(e)}"
            debug_logger.log_error(error_msg)
            if stream:
                yield self._format_stream_chunk(content=f"Error: {error_msg}", is_first=True)
                yield self._format_stream_chunk(finish_reason="STOP")
            else:
                yield self._format_non_stream_response(error_msg)

    # ==================== Character Creation and Remix Handlers ====================

    async def _handle_character_creation_only(self, video_data, model_config: Dict) -> AsyncGenerator[str, None]:
        """Handle character creation only (no video generation)

        Flow:
        1. Download video if URL, or use bytes directly
        2. Upload video to create character
        3. Poll for character processing
        4. Download and cache avatar
        5. Upload avatar
        6. Finalize character
        7. Set character as public
        8. Return success message
        """
        token_obj = await self.load_balancer.select_token(for_video_generation=True)
        if not token_obj:
            raise Exception("No available tokens for character creation")

        start_time = time.time()
        try:
            yield self._format_stream_chunk(
                reasoning_content="**Character Creation Begins**\n\nInitializing character creation...\n",
                is_first=True
            )

            # Handle video URL or bytes
            if isinstance(video_data, str):
                # It's a URL, download it
                yield self._format_stream_chunk(
                    reasoning_content="Downloading video file...\n"
                )
                video_bytes = await self._download_file(video_data)
            else:
                video_bytes = video_data

            # Step 1: Upload video
            yield self._format_stream_chunk(
                reasoning_content="Uploading video file...\n"
            )
            cameo_id = await self.sora_client.upload_character_video(video_bytes, token_obj.token)
            debug_logger.log_info(f"Video uploaded, cameo_id: {cameo_id}")

            # Step 2: Poll for character processing
            yield self._format_stream_chunk(
                reasoning_content="Processing video to extract character...\n"
            )
            cameo_status = await self._poll_cameo_status(cameo_id, token_obj.token)
            debug_logger.log_info(f"Cameo status: {cameo_status}")

            # Extract character info immediately after polling completes
            username_hint = cameo_status.get("username_hint", "character")
            display_name = cameo_status.get("display_name_hint", "Character")

            # Process username: remove prefix and add 3 random digits
            username = self._process_character_username(username_hint)

            # Output character name immediately
            yield self._format_stream_chunk(
                reasoning_content=f"✨ 角色已识别: {display_name} (@{username})\n"
            )

            # Step 3: Download and cache avatar
            yield self._format_stream_chunk(
                reasoning_content="Downloading character avatar...\n"
            )
            profile_asset_url = cameo_status.get("profile_asset_url")
            if not profile_asset_url:
                raise Exception("Profile asset URL not found in cameo status")

            avatar_data = await self.sora_client.download_character_image(profile_asset_url)
            debug_logger.log_info(f"Avatar downloaded, size: {len(avatar_data)} bytes")

            # Step 4: Upload avatar
            yield self._format_stream_chunk(
                reasoning_content="Uploading character avatar...\n"
            )
            asset_pointer = await self.sora_client.upload_character_image(avatar_data, token_obj.token)
            debug_logger.log_info(f"Avatar uploaded, asset_pointer: {asset_pointer}")

            # Step 5: Finalize character
            yield self._format_stream_chunk(
                reasoning_content="Finalizing character creation...\n"
            )
            # instruction_set_hint is a string, but instruction_set in cameo_status might be an array
            instruction_set = cameo_status.get("instruction_set_hint") or cameo_status.get("instruction_set")

            character_id = await self.sora_client.finalize_character(
                cameo_id=cameo_id,
                username=username,
                display_name=display_name,
                profile_asset_pointer=asset_pointer,
                instruction_set=instruction_set,
                token=token_obj.token
            )
            debug_logger.log_info(f"Character finalized, character_id: {character_id}")

            # Step 6: Set character as public
            yield self._format_stream_chunk(
                reasoning_content="Setting character as public...\n"
            )
            await self.sora_client.set_character_public(cameo_id, token_obj.token)
            debug_logger.log_info(f"Character set as public")

            # Log successful character creation
            duration = time.time() - start_time
            await self._log_request(
                token_id=token_obj.id,
                operation="character_only",
                request_data={
                    "type": "character_creation",
                    "has_video": True
                },
                response_data={
                    "success": True,
                    "username": username,
                    "display_name": display_name,
                    "character_id": character_id,
                    "cameo_id": cameo_id
                },
                status_code=200,
                duration=duration
            )

            # Step 7: Return success message
            yield self._format_stream_chunk(
                content=f"角色创建成功，角色名@{username}",
                finish_reason="STOP"
            )
            yield "data: [DONE]\n\n"

        except Exception as e:
            # Parse error to check for CF shield/429
            error_response = None
            try:
                error_response = json.loads(str(e))
            except:
                pass

            # Check for CF shield/429 error
            is_cf_or_429 = False
            if error_response and isinstance(error_response, dict):
                error_info = error_response.get("error", {})
                if error_info.get("code") == "cf_shield_429":
                    is_cf_or_429 = True

            # Log failed character creation
            duration = time.time() - start_time
            await self._log_request(
                token_id=token_obj.id if token_obj else None,
                operation="character_only",
                request_data={
                    "type": "character_creation",
                    "has_video": True
                },
                response_data={
                    "success": False,
                    "error": str(e)
                },
                status_code=429 if is_cf_or_429 else 500,
                duration=duration
            )

            # Record error (check if it's an overload error or CF/429 error)
            if token_obj:
                error_str = str(e).lower()
                is_overload = "heavy_load" in error_str or "under heavy load" in error_str
                # Don't record error for CF shield/429 (not token's fault)
                if not is_cf_or_429:
                    await self.token_manager.record_error(token_obj.id, is_overload=is_overload)

            debug_logger.log_error(
                error_message=f"Character creation failed: {str(e)}",
                status_code=429 if is_cf_or_429 else 500,
                response_text=str(e)
            )
            raise

    async def _handle_character_and_video_generation(self, video_data, prompt: str, model_config: Dict) -> AsyncGenerator[str, None]:
        """Handle character creation and video generation

        Flow:
        1. Download video if URL, or use bytes directly
        2. Upload video to create character
        3. Poll for character processing
        4. Download and cache avatar
        5. Upload avatar
        6. Finalize character
        7. Generate video with character (@username + prompt)
        8. Delete character
        9. Return video result
        """
        token_obj = await self.load_balancer.select_token(for_video_generation=True)
        if not token_obj:
            raise Exception("No available tokens for video generation")

        character_id = None
        start_time = time.time()
        username = None
        display_name = None
        cameo_id = None
        try:
            yield self._format_stream_chunk(
                reasoning_content="**Character Creation and Video Generation Begins**\n\nInitializing...\n",
                is_first=True
            )

            # Handle video URL or bytes
            if isinstance(video_data, str):
                # It's a URL, download it
                yield self._format_stream_chunk(
                    reasoning_content="Downloading video file...\n"
                )
                video_bytes = await self._download_file(video_data)
            else:
                video_bytes = video_data

            # Step 1: Upload video
            yield self._format_stream_chunk(
                reasoning_content="Uploading video file...\n"
            )
            cameo_id = await self.sora_client.upload_character_video(video_bytes, token_obj.token)
            debug_logger.log_info(f"Video uploaded, cameo_id: {cameo_id}")

            # Step 2: Poll for character processing
            yield self._format_stream_chunk(
                reasoning_content="Processing video to extract character...\n"
            )
            cameo_status = await self._poll_cameo_status(cameo_id, token_obj.token)
            debug_logger.log_info(f"Cameo status: {cameo_status}")

            # Extract character info immediately after polling completes
            username_hint = cameo_status.get("username_hint", "character")
            display_name = cameo_status.get("display_name_hint", "Character")

            # Process username: remove prefix and add 3 random digits
            username = self._process_character_username(username_hint)

            # Output character name immediately
            yield self._format_stream_chunk(
                reasoning_content=f"✨ 角色已识别: {display_name} (@{username})\n"
            )

            # Step 3: Download and cache avatar
            yield self._format_stream_chunk(
                reasoning_content="Downloading character avatar...\n"
            )
            profile_asset_url = cameo_status.get("profile_asset_url")
            if not profile_asset_url:
                raise Exception("Profile asset URL not found in cameo status")

            avatar_data = await self.sora_client.download_character_image(profile_asset_url)
            debug_logger.log_info(f"Avatar downloaded, size: {len(avatar_data)} bytes")

            # Step 4: Upload avatar
            yield self._format_stream_chunk(
                reasoning_content="Uploading character avatar...\n"
            )
            asset_pointer = await self.sora_client.upload_character_image(avatar_data, token_obj.token)
            debug_logger.log_info(f"Avatar uploaded, asset_pointer: {asset_pointer}")

            # Step 5: Finalize character
            yield self._format_stream_chunk(
                reasoning_content="Finalizing character creation...\n"
            )
            # instruction_set_hint is a string, but instruction_set in cameo_status might be an array
            instruction_set = cameo_status.get("instruction_set_hint") or cameo_status.get("instruction_set")

            character_id = await self.sora_client.finalize_character(
                cameo_id=cameo_id,
                username=username,
                display_name=display_name,
                profile_asset_pointer=asset_pointer,
                instruction_set=instruction_set,
                token=token_obj.token
            )
            debug_logger.log_info(f"Character finalized, character_id: {character_id}")

            # Log successful character creation (before video generation)
            character_creation_duration = time.time() - start_time
            await self._log_request(
                token_id=token_obj.id,
                operation="character_with_video",
                request_data={
                    "type": "character_creation_with_video",
                    "has_video": True,
                    "prompt": prompt
                },
                response_data={
                    "success": True,
                    "username": username,
                    "display_name": display_name,
                    "character_id": character_id,
                    "cameo_id": cameo_id,
                    "stage": "character_created"
                },
                status_code=200,
                duration=character_creation_duration
            )

            # Step 6: Generate video with character
            yield self._format_stream_chunk(
                reasoning_content="**Video Generation Process Begins**\n\nGenerating video with character...\n"
            )

            # Prepend @username to prompt
            full_prompt = f"@{username} {prompt}"
            debug_logger.log_info(f"Full prompt: {full_prompt}")

            # Get n_frames from model configuration
            n_frames = model_config.get("n_frames", 300)  # Default to 300 frames (10s)

            # Get model and size from config (default to sy_8 and small for backward compatibility)
            sora_model = model_config.get("model", "sy_8")
            video_size = model_config.get("size", "small")

            task_id = await self.sora_client.generate_video(
                full_prompt, token_obj.token,
                orientation=model_config["orientation"],
                n_frames=n_frames,
                model=sora_model,
                size=video_size,
                token_id=token_obj.id
            )
            debug_logger.log_info(f"Video generation started, task_id: {task_id}")

            # Save task to database
            task = Task(
                task_id=task_id,
                token_id=token_obj.id,
                model=f"sora2-video-{model_config['orientation']}",
                prompt=full_prompt,
                status="processing",
                progress=0.0
            )
            await self.db.create_task(task)

            # Record usage
            await self.token_manager.record_usage(token_obj.id, is_video=True)

            # Poll for results
            async for chunk in self._poll_task_result(task_id, token_obj.token, True, True, full_prompt, token_obj.id):
                yield chunk

            # Record success
            await self.token_manager.record_success(token_obj.id, is_video=True)

        except Exception as e:
            # Log failed character creation
            duration = time.time() - start_time
            await self._log_request(
                token_id=token_obj.id if token_obj else None,
                operation="character_with_video",
                request_data={
                    "type": "character_creation_with_video",
                    "has_video": True,
                    "prompt": prompt
                },
                response_data={
                    "success": False,
                    "username": username,
                    "display_name": display_name,
                    "character_id": character_id,
                    "cameo_id": cameo_id,
                    "error": str(e)
                },
                status_code=500,
                duration=duration
            )

            # Parse error to check for CF shield/429
            error_response = None
            try:
                error_response = json.loads(str(e))
            except:
                pass

            # Check for CF shield/429 error
            is_cf_or_429 = False
            if error_response and isinstance(error_response, dict):
                error_info = error_response.get("error", {})
                if error_info.get("code") == "cf_shield_429":
                    is_cf_or_429 = True

            # Record error (check if it's an overload error or CF/429 error)
            if token_obj:
                error_str = str(e).lower()
                is_overload = "heavy_load" in error_str or "under heavy load" in error_str
                # Don't record error for CF shield/429 (not token's fault)
                if not is_cf_or_429:
                    await self.token_manager.record_error(token_obj.id, is_overload=is_overload)
            debug_logger.log_error(
                error_message=f"Character and video generation failed: {str(e)}",
                status_code=429 if is_cf_or_429 else 500,
                response_text=str(e)
            )
            raise
        finally:
            # Step 7: Delete character
            if character_id:
                try:
                    yield self._format_stream_chunk(
                        reasoning_content="Cleaning up temporary character...\n"
                    )
                    await self.sora_client.delete_character(character_id, token_obj.token)
                    debug_logger.log_info(f"Character deleted: {character_id}")
                except Exception as e:
                    debug_logger.log_error(
                        error_message=f"Failed to delete character: {str(e)}",
                        status_code=500,
                        response_text=str(e)
                    )

    async def _handle_remix(self, remix_target_id: str, prompt: str, model_config: Dict) -> AsyncGenerator[str, None]:
        """Handle remix video generation

        Flow:
        1. Select token
        2. Clean remix link from prompt
        3. Call remix API
        4. Poll for results
        5. Return video result
        """
        token_obj = await self.load_balancer.select_token(for_video_generation=True)
        if not token_obj:
            raise Exception("No available tokens for remix generation")

        task_id = None
        try:
            yield self._format_stream_chunk(
                reasoning_content="**Remix Generation Process Begins**\n\nInitializing remix request...\n",
                is_first=True
            )

            # Clean remix link from prompt to avoid duplication
            clean_prompt = self._clean_remix_link_from_prompt(prompt)

            # Extract style from prompt
            clean_prompt, style_id = self._extract_style(clean_prompt)

            # Get n_frames from model configuration
            n_frames = model_config.get("n_frames", 300)  # Default to 300 frames (10s)

            # Call remix API
            yield self._format_stream_chunk(
                reasoning_content="Sending remix request to server...\n"
            )
            task_id = await self.sora_client.remix_video(
                remix_target_id=remix_target_id,
                prompt=clean_prompt,
                token=token_obj.token,
                orientation=model_config["orientation"],
                n_frames=n_frames,
                style_id=style_id
            )
            debug_logger.log_info(f"Remix generation started, task_id: {task_id}")

            # Save task to database
            task = Task(
                task_id=task_id,
                token_id=token_obj.id,
                model=f"sora2-video-{model_config['orientation']}",
                prompt=f"remix:{remix_target_id} {clean_prompt}",
                status="processing",
                progress=0.0
            )
            await self.db.create_task(task)

            # Record usage
            await self.token_manager.record_usage(token_obj.id, is_video=True)

            # Poll for results
            async for chunk in self._poll_task_result(task_id, token_obj.token, True, True, clean_prompt, token_obj.id):
                yield chunk

            # Record success
            await self.token_manager.record_success(token_obj.id, is_video=True)

        except Exception as e:
            # Parse error to check for CF shield/429
            error_response = None
            try:
                error_response = json.loads(str(e))
            except:
                pass

            # Check for CF shield/429 error
            is_cf_or_429 = False
            if error_response and isinstance(error_response, dict):
                error_info = error_response.get("error", {})
                if error_info.get("code") == "cf_shield_429":
                    is_cf_or_429 = True

            # Record error (check if it's an overload error or CF/429 error)
            if token_obj:
                error_str = str(e).lower()
                is_overload = "heavy_load" in error_str or "under heavy load" in error_str
                # Don't record error for CF shield/429 (not token's fault)
                if not is_cf_or_429:
                    await self.token_manager.record_error(token_obj.id, is_overload=is_overload)
            debug_logger.log_error(
                error_message=f"Remix generation failed: {str(e)}",
                status_code=429 if is_cf_or_429 else 500,
                response_text=str(e)
            )
            raise

    async def _poll_cameo_status(self, cameo_id: str, token: str, timeout: int = 600, poll_interval: int = 5) -> Dict[str, Any]:
        """Poll for cameo (character) processing status

        Args:
            cameo_id: The cameo ID
            token: Access token
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            Cameo status dictionary with display_name_hint, username_hint, profile_asset_url, instruction_set_hint
        """
        start_time = time.time()
        max_attempts = int(timeout / poll_interval)
        consecutive_errors = 0
        max_consecutive_errors = 3  # Allow up to 3 consecutive errors before failing

        for attempt in range(max_attempts):
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                raise Exception(f"Cameo processing timeout after {elapsed_time:.1f} seconds")

            await asyncio.sleep(poll_interval)

            try:
                status = await self.sora_client.get_cameo_status(cameo_id, token)
                current_status = status.get("status")
                status_message = status.get("status_message", "")

                # Reset error counter on successful request
                consecutive_errors = 0

                debug_logger.log_info(f"Cameo status: {current_status} (message: {status_message}) (attempt {attempt + 1}/{max_attempts})")

                # Check if processing failed
                if current_status == "failed":
                    error_message = status_message or "Character creation failed"
                    debug_logger.log_error(
                        error_message=f"Cameo processing failed: {error_message}",
                        status_code=500,
                        response_text=error_message
                    )
                    raise Exception(f"角色创建失败: {error_message}")

                # Check if processing is complete
                # Primary condition: status_message == "Completed" means processing is done
                if status_message == "Completed":
                    debug_logger.log_info(f"Cameo processing completed (status: {current_status}, message: {status_message})")
                    return status

                # Fallback condition: finalized status
                if current_status == "finalized":
                    debug_logger.log_info(f"Cameo processing completed (status: {current_status}, message: {status_message})")
                    return status

            except Exception as e:
                consecutive_errors += 1
                error_msg = str(e)

                # Check if it's a character creation failure (not a network error)
                # These should be raised immediately, not retried
                if "角色创建失败" in error_msg:
                    raise

                # Log error with context
                debug_logger.log_error(
                    error_message=f"Failed to get cameo status (attempt {attempt + 1}/{max_attempts}, consecutive errors: {consecutive_errors}): {error_msg}",
                    status_code=500,
                    response_text=error_msg
                )

                # Check if it's a TLS/connection error
                is_tls_error = "TLS" in error_msg or "curl" in error_msg or "OPENSSL" in error_msg

                if is_tls_error:
                    # For TLS errors, use exponential backoff
                    backoff_time = min(poll_interval * (2 ** (consecutive_errors - 1)), 30)
                    debug_logger.log_info(f"TLS error detected, using exponential backoff: {backoff_time}s")
                    await asyncio.sleep(backoff_time)

                # Fail if too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    raise Exception(f"Too many consecutive errors ({consecutive_errors}) while polling cameo status: {error_msg}")

                # Continue polling on error
                continue

        raise Exception(f"Cameo processing timeout after {timeout} seconds")
