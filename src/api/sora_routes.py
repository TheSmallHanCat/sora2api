from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional, Tuple, Any
import json
import time
from ..core.auth import verify_api_key_header
from ..core.models import VideoCreateRequest
from ..services.generation_handler import GenerationHandler, MODEL_CONFIG
from ..core.logger import debug_logger

router = APIRouter()

generation_handler: GenerationHandler = None

def set_generation_handler(handler: GenerationHandler):
    global generation_handler
    generation_handler = handler

def _parse_size(size: Optional[str]) -> Optional[Tuple[int, int]]:
    if not size:
        return None
    parts = size.lower().split("x")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None

def _normalize_seconds(seconds: Optional[Any]) -> Optional[int]:
    if seconds is None:
        return None
    try:
        return int(seconds)
    except (ValueError, TypeError):
        return None

def _select_video_model(model: Optional[str], seconds: Optional[Any], size: Optional[str]) -> str:
    if model and model in MODEL_CONFIG:
        return model
    if model and model != "sora-2":
        raise HTTPException(status_code=400, detail=f"Invalid model: {model}")
    duration = _normalize_seconds(seconds)
    if duration not in (10, 15, 25):
        duration = 10
    orientation = "landscape"
    parsed_size = _parse_size(size)
    if parsed_size and parsed_size[1] > parsed_size[0]:
        orientation = "portrait"
    candidate = f"sora2-{orientation}-{duration}s"
    if candidate not in MODEL_CONFIG:
        raise HTTPException(status_code=400, detail=f"Invalid model: {candidate}")
    return candidate

@router.post("/v1/videos")
async def create_video(
    request: VideoCreateRequest,
    api_key: str = Depends(verify_api_key_header)
):
    start_time = time.time()
    try:
        model = _select_video_model(request.model, request.seconds, request.size)
        model_config = MODEL_CONFIG[model]
        if model_config.get("type") != "video":
            raise HTTPException(status_code=400, detail=f"Invalid model: {model}")
        task_id = await generation_handler.start_video_task(
            model=model,
            prompt=request.prompt,
            image=request.image,
            metadata=request.metadata
        )
        response_data = {
            "id": task_id,
            "object": "video",
            "model": model,
            "created_at": int(datetime.now().timestamp()),
            "status": "processing",
            "progress": 0
        }
        debug_logger.log_response(
            status_code=201,
            headers={"Content-Type": "application/json"},
            body=response_data,
            duration_ms=(time.time() - start_time) * 1000,
            source="Client"
        )
        return JSONResponse(status_code=201, content=response_data)
    except HTTPException:
        raise
    except Exception as e:
        error_response = {
            "error": {
                "message": str(e),
                "type": "server_error"
            }
        }
        debug_logger.log_response(
            status_code=500,
            headers={"Content-Type": "application/json"},
            body=error_response,
            duration_ms=(time.time() - start_time) * 1000,
            source="Client"
        )
        return JSONResponse(status_code=500, content=error_response)

@router.get("/v1/videos/{video_id}")
async def get_video(
    video_id: str,
    api_key: str = Depends(verify_api_key_header)
):
    task = await generation_handler.db.get_task(video_id)
    if not task:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "message": "Task not found",
                    "type": "invalid_request_error"
                }
            }
        )
    status_map = {
        "processing": "processing",
        "completed": "succeeded",
        "failed": "failed"
    }
    status = status_map.get(task.status, "processing")
    url = None
    if task.result_urls:
        try:
            urls = json.loads(task.result_urls)
            if isinstance(urls, list) and urls:
                url = urls[0]
        except Exception:
            url = task.result_urls
    created_at = int(task.created_at.timestamp()) if task.created_at else int(time.time())
    response_data = {
        "id": task.task_id,
        "object": "video",
        "model": task.model,
        "created_at": created_at,
        "status": status,
        "progress": int(task.progress or 0),
        "url": url,
        "error": None
    }
    if status == "failed":
        response_data["error"] = {
            "message": task.error_message or "Generation failed",
            "type": "invalid_request_error"
        }
    return JSONResponse(content=response_data)
