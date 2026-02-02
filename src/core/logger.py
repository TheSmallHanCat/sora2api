"""Debug logger module for detailed API request/response logging"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from .config import config

class DebugLogger:
    """Debug logger for API requests and responses"""
    
    def __init__(self):
        self.log_file = Path("logs.txt")
        self._setup_logger()
    
    def _setup_logger(self):
        """Setup file logger"""
        # Clear log file on startup
        if self.log_file.exists():
            self.log_file.unlink()

        # Create logger
        self.logger = logging.getLogger("debug_logger")
        self.logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        self.logger.handlers.clear()

        # Create file handler
        file_handler = logging.FileHandler(
            self.log_file,
            mode='a',
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Add handler
        self.logger.addHandler(file_handler)
        
        # Prevent propagation to root logger
        self.logger.propagate = False
    
    def _mask_token(self, token: str) -> str:
        """Mask token for logging (show first 6 and last 6 characters)"""
        if not config.debug_mask_token or len(token) <= 12:
            return token
        return f"{token[:6]}...{token[-6:]}"
    
    def _format_timestamp(self) -> str:
        """Format current timestamp"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    def _write_separator(self, char: str = "=", length: int = 100):
        """Write separator line"""
        self.logger.info(char * length)
    
    def log_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[Any] = None,
        files: Optional[Dict] = None,
        proxy: Optional[str] = None,
        source: str = "Server"
    ):
        """Log API request details to log.txt

        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            body: Request body
            files: Files to upload
            proxy: Proxy URL
            source: Request source - "Client" for user->sora2api, "Server" for sora2api->Sora
        """

        # Check if debug mode is enabled
        if not config.debug_enabled:
            return

        try:
            self._write_separator()
            self.logger.info(f"🔵 [REQUEST][{source}] {self._format_timestamp()}")
            self._write_separator("-")

            # Basic info
            self.logger.info(f"Method: {method}")
            self.logger.info(f"URL: {url}")

            # Headers
            self.logger.info("\n📋 Headers:")
            masked_headers = dict(headers)
            if "Authorization" in masked_headers:
                auth_value = masked_headers["Authorization"]
                if auth_value.startswith("Bearer "):
                    token = auth_value[7:]
                    masked_headers["Authorization"] = f"Bearer {self._mask_token(token)}"

            for key, value in masked_headers.items():
                self.logger.info(f"  {key}: {value}")

            # Body
            if body is not None:
                self.logger.info("\n📦 Request Body:")
                if isinstance(body, (dict, list)):
                    body_str = json.dumps(body, indent=2, ensure_ascii=False)
                    self.logger.info(body_str)
                else:
                    self.logger.info(str(body))

            # Files
            if files:
                self.logger.info("\n📎 Files:")
                try:
                    # Handle both dict and CurlMime objects
                    if hasattr(files, 'keys') and callable(getattr(files, 'keys', None)):
                        for key in files.keys():
                            self.logger.info(f"  {key}: <file data>")
                    else:
                        # CurlMime or other non-dict objects
                        self.logger.info("  <multipart form data>")
                except (AttributeError, TypeError):
                    # Fallback for objects that don't support iteration
                    self.logger.info("  <binary file data>")

            # Proxy
            if proxy:
                self.logger.info(f"\n🌐 Proxy: {proxy}")

            self._write_separator()
            self.logger.info("")  # Empty line

        except Exception as e:
            self.logger.error(f"Error logging request: {e}")
    
    def log_response(
        self,
        status_code: int,
        headers: Dict[str, str],
        body: Any,
        duration_ms: Optional[float] = None,
        source: str = "Server"
    ):
        """Log API response details to log.txt

        Args:
            status_code: HTTP status code
            headers: Response headers
            body: Response body
            duration_ms: Request duration in milliseconds
            source: Request source - "Client" for user->sora2api, "Server" for sora2api->Sora
        """

        # Check if debug mode is enabled
        if not config.debug_enabled:
            return

        try:
            self._write_separator()
            self.logger.info(f"🟢 [RESPONSE][{source}] {self._format_timestamp()}")
            self._write_separator("-")

            # Status
            status_emoji = "✅" if 200 <= status_code < 300 else "❌"
            self.logger.info(f"Status: {status_code} {status_emoji}")

            # Duration
            if duration_ms is not None:
                self.logger.info(f"Duration: {duration_ms:.2f}ms")

            # Headers
            self.logger.info("\n📋 Response Headers:")
            for key, value in headers.items():
                self.logger.info(f"  {key}: {value}")

            # Body
            self.logger.info("\n📦 Response Body:")
            if isinstance(body, (dict, list)):
                body_str = json.dumps(body, indent=2, ensure_ascii=False)
                self.logger.info(body_str)
            elif isinstance(body, str):
                # Try to parse as JSON
                try:
                    parsed = json.loads(body)
                    body_str = json.dumps(parsed, indent=2, ensure_ascii=False)
                    self.logger.info(body_str)
                except:
                    # Not JSON, log as text (limit length)
                    if len(body) > 2000:
                        self.logger.info(f"{body[:2000]}... (truncated)")
                    else:
                        self.logger.info(body)
            else:
                self.logger.info(str(body))

            self._write_separator()
            self.logger.info("")  # Empty line
            
        except Exception as e:
            self.logger.error(f"Error logging response: {e}")
    
    def log_error(
        self,
        error_message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
        source: str = "Server"
    ):
        """Log API error details to log.txt

        Args:
            error_message: Error message
            status_code: HTTP status code
            response_text: Response text
            source: Request source - "Client" for user->sora2api, "Server" for sora2api->Sora
        """

        # Check if debug mode is enabled
        if not config.debug_enabled:
            return

        try:
            self._write_separator()
            self.logger.info(f"🔴 [ERROR][{source}] {self._format_timestamp()}")
            self._write_separator("-")

            if status_code:
                self.logger.info(f"Status Code: {status_code}")

            self.logger.info(f"Error Message: {error_message}")

            if response_text:
                self.logger.info("\n📦 Error Response:")
                # Try to parse as JSON
                try:
                    parsed = json.loads(response_text)
                    body_str = json.dumps(parsed, indent=2, ensure_ascii=False)
                    self.logger.info(body_str)
                except:
                    # Not JSON, log as text
                    if len(response_text) > 2000:
                        self.logger.info(f"{response_text[:2000]}... (truncated)")
                    else:
                        self.logger.info(response_text)

            self._write_separator()
            self.logger.info("")  # Empty line

        except Exception as e:
            self.logger.error(f"Error logging error: {e}")
    
    def log_info(self, message: str):
        """Log general info message to log.txt"""

        # Check if debug mode is enabled
        if not config.debug_enabled:
            return

        try:
            self.logger.info(f"ℹ️  [{self._format_timestamp()}] {message}")
        except Exception as e:
            self.logger.error(f"Error logging info: {e}")

    def log_warning(self, message: str):
        """Log warning message to log.txt"""

        # Check if debug mode is enabled
        if not config.debug_enabled:
            return

        try:
            self.logger.warning(f"⚠️  [{self._format_timestamp()}] {message}")
        except Exception as e:
            self.logger.error(f"Error logging warning: {e}")

# Global debug logger instance
debug_logger = DebugLogger()

