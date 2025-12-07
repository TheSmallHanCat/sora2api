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

# Model configuration
MODEL_CONFIG = {
    "sora-image": {
        "type": "image",
        "width": 360,
        "height": 360
    },
    "sora-image-landscape": {
        "type": "image",
        "width": 540,
        "height": 360
    },
    "sora-image-portrait": {
        "type": "image",
        "width": 360,
        "height": 540
    },
    # Video models with 10s duration (300 frames)
    "sora-video-10s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 300
    },
    "sora-video-landscape-10s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 300
    },
    "sora-video-portrait-10s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 300
    },
    # Video models with 15s duration (450 frames)
    "sora-video-15s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 450
    },
    "sora-video-landscape-15s": {
        "type": "video",
        "orientation": "landscape",
        "n_frames": 450
    },
    "sora-video-portrait-15s": {
        "type": "video",
        "orientation": "portrait",
        "n_frames": 450
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

        # Validate model
        if model not in MODEL_CONFIG:
            raise ValueError(f"Invalid model: {model}")

        model_config = MODEL_CONFIG[model]
        is_video = model_config["type"] == "video"
        is_image = model_config["type"] == "image"

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
        # Select token (with lock for image generation, Sora2 quota check for video generation)
        token_obj = await self.load_balancer.select_token(for_image_generation=is_image, for_video_generation=is_video)
        if not token_obj:
            if is_image:
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

        try:
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

                # Check if prompt is in storyboard format
                if self.sora_client.is_storyboard_prompt(prompt):
                    # Storyboard mode
                    if stream:
                        yield self._format_stream_chunk(
                            reasoning_content="Detected storyboard format. Converting to storyboard API format...\n"
                        )

                    formatted_prompt = self.sora_client.format_storyboard_prompt(prompt)
                    debug_logger.log_info(f"Storyboard mode detected. Formatted prompt: {formatted_prompt}")

                    task_id = await self.sora_client.generate_storyboard(
                        formatted_prompt, token_obj.token,
                        orientation=model_config["orientation"],
                        media_id=media_id,
                        n_frames=n_frames
                    )
                else:
                    # Normal video generation
                    task_id = await self.sora_client.generate_video(
                        prompt, token_obj.token,
                        orientation=model_config["orientation"],
                        media_id=media_id,
                        n_frames=n_frames
                    )
            else:
                task_id = await self.sora_client.generate_image(
                    prompt, token_obj.token,
                    width=model_config["width"],
                    height=model_config["height"],
                    media_id=media_id
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
            
            # Record usage
            await self.token_manager.record_usage(token_obj.id, is_video=is_video)
            
            # Poll for results with timeout
            async for chunk in self._poll_task_result(task_id, token_obj.token, is_video, stream, prompt, token_obj.id):
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

            # Log successful request
            duration = time.time() - start_time
            await self._log_request(
                token_obj.id,
                f"generate_{model_config['type']}",
                {"model": model, "prompt": prompt, "has_image": image is not None},
                {"task_id": task_id, "status": "success"},
                200,
                duration
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

            # Record error
            if token_obj:
                await self.token_manager.record_error(token_obj.id)

            # Log failed request
            duration = time.time() - start_time
            await self._log_request(
                token_obj.id if token_obj else None,
                f"generate_{model_config['type'] if model_config else 'unknown'}",
                {"model": model, "prompt": prompt, "has_image": image is not None},
                {"error": str(e)},
                500,
                duration
            )
            raise e
    
    async def _poll_task_result(self, task_id: str, token: str, is_video: bool,
                                stream: bool, prompt: str, token_id: int = None) -> AsyncGenerator[str, None]:
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

                await self.db.update_task(task_id, "failed", 0, error_message=f"Generation timeout after {elapsed_time:.1f} seconds")
                raise Exception(f"Upstream API timeout: Generation exceeded {timeout} seconds limit")


            await asyncio.sleep(poll_interval)

            try:
                if is_video:
                    # Get pending tasks to check progress
                    pending_tasks = await self.sora_client.get_pending_tasks(token)

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
                        result = await self.sora_client.get_video_drafts(token)
                        items = result.get("items", [])

                        # Find matching task in drafts
                        for item in items:
                            if item.get("task_id") == task_id:
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
                                                cached_filename = await self.file_cache.download_and_cache(watermark_free_url, "video")
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
                                                cached_filename = await self.file_cache.download_and_cache(url, "video")
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
                                                cached_filename = await self.file_cache.download_and_cache(url, "video")
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
                    result = await self.sora_client.get_image_tasks(token)
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
                                                cached_filename = await self.file_cache.download_and_cache(url, "image")
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
                          status_code: int, duration: float):
        """Log request to database"""
        try:
            log = RequestLog(
                token_id=token_id,
                operation=operation,
                request_body=json.dumps(request_data),
                response_body=json.dumps(response_data),
                status_code=status_code,
                duration=duration
            )
            await self.db.log_request(log)
        except Exception as e:
            # Don't fail the request if logging fails
            print(f"Failed to log request: {e}")

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

            # Step 7: Return success message
            yield self._format_stream_chunk(
                content=f"Персонаж успешно создан, имя @{username}",
                finish_reason="STOP"
            )
            yield "data: [DONE]\n\n"

        except Exception as e:
            debug_logger.log_error(
                error_message=f"Character creation failed: {str(e)}",
                status_code=500,
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

            # Step 6: Generate video with character
            yield self._format_stream_chunk(
                reasoning_content="**Video Generation Process Begins**\n\nGenerating video with character...\n"
            )

            # Prepend @username to prompt
            full_prompt = f"@{username} {prompt}"
            debug_logger.log_info(f"Full prompt: {full_prompt}")

            # Get n_frames from model configuration
            n_frames = model_config.get("n_frames", 300)  # Default to 300 frames (10s)

            task_id = await self.sora_client.generate_video(
                full_prompt, token_obj.token,
                orientation=model_config["orientation"],
                n_frames=n_frames
            )
            debug_logger.log_info(f"Video generation started, task_id: {task_id}")

            # Save task to database
            task = Task(
                task_id=task_id,
                token_id=token_obj.id,
                model=f"sora-video-{model_config['orientation']}",
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
            # Record error
            if token_obj:
                await self.token_manager.record_error(token_obj.id)
            debug_logger.log_error(
                error_message=f"Character and video generation failed: {str(e)}",
                status_code=500,
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
                n_frames=n_frames
            )
            debug_logger.log_info(f"Remix generation started, task_id: {task_id}")

            # Save task to database
            task = Task(
                task_id=task_id,
                token_id=token_obj.id,
                model=f"sora-video-{model_config['orientation']}",
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
            # Record error
            if token_obj:
                await self.token_manager.record_error(token_obj.id)
            debug_logger.log_error(
                error_message=f"Remix generation failed: {str(e)}",
                status_code=500,
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
