"""Configuration management"""
import tomli
from pathlib import Path
from typing import Dict, Any, Optional

class Config:
    """Application configuration"""

    def __init__(self):
        self._config = self._load_config()
        self._admin_username: Optional[str] = None
        self._admin_password: Optional[str] = None
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from setting.toml"""
        config_path = Path(__file__).parent.parent.parent / "config" / "setting.toml"
        with open(config_path, "rb") as f:
            return tomli.load(f)

    def reload_config(self):
        """Reload configuration from file"""
        self._config = self._load_config()

    def get_raw_config(self) -> Dict[str, Any]:
        """Get raw configuration dictionary"""
        return self._config
    
    @property
    def admin_username(self) -> str:
        # If admin_username is set from database, use it; otherwise fall back to config file
        if self._admin_username is not None:
            return self._admin_username
        return self._config["global"]["admin_username"]

    @admin_username.setter
    def admin_username(self, value: str):
        self._admin_username = value
        self._config["global"]["admin_username"] = value

    def set_admin_username_from_db(self, username: str):
        """Set admin username from database"""
        self._admin_username = username

    @property
    def sora_base_url(self) -> str:
        return self._config["sora"]["base_url"]
    
    @property
    def sora_timeout(self) -> int:
        return self._config["sora"]["timeout"]
    
    @property
    def sora_max_retries(self) -> int:
        return self._config["sora"]["max_retries"]
    
    @property
    def poll_interval(self) -> float:
        return self._config["sora"]["poll_interval"]
    
    @property
    def max_poll_attempts(self) -> int:
        return self._config["sora"]["max_poll_attempts"]
    
    @property
    def server_host(self) -> str:
        return self._config["server"]["host"]
    
    @property
    def server_port(self) -> int:
        return self._config["server"]["port"]

    @property
    def debug_enabled(self) -> bool:
        return self._config.get("debug", {}).get("enabled", False)

    @property
    def debug_log_requests(self) -> bool:
        return self._config.get("debug", {}).get("log_requests", True)

    @property
    def debug_log_responses(self) -> bool:
        return self._config.get("debug", {}).get("log_responses", True)

    @property
    def debug_mask_token(self) -> bool:
        return self._config.get("debug", {}).get("mask_token", True)

    # Mutable properties for runtime updates
    @property
    def api_key(self) -> str:
        return self._config["global"]["api_key"]

    @api_key.setter
    def api_key(self, value: str):
        self._config["global"]["api_key"] = value

    @property
    def admin_password(self) -> str:
        # If admin_password is set from database, use it; otherwise fall back to config file
        if self._admin_password is not None:
            return self._admin_password
        return self._config["global"]["admin_password"]

    @admin_password.setter
    def admin_password(self, value: str):
        self._admin_password = value
        self._config["global"]["admin_password"] = value

    def set_admin_password_from_db(self, password: str):
        """Set admin password from database"""
        self._admin_password = password

    def set_debug_enabled(self, enabled: bool):
        """Set debug mode enabled/disabled"""
        if "debug" not in self._config:
            self._config["debug"] = {}
        self._config["debug"]["enabled"] = enabled

    @property
    def cache_timeout(self) -> int:
        """Get cache timeout in seconds"""
        return self._config.get("cache", {}).get("timeout", 7200)

    def set_cache_timeout(self, timeout: int):
        """Set cache timeout in seconds"""
        if "cache" not in self._config:
            self._config["cache"] = {}
        self._config["cache"]["timeout"] = timeout

    @property
    def cache_base_url(self) -> str:
        """Get cache base URL"""
        return self._config.get("cache", {}).get("base_url", "")

    def set_cache_base_url(self, base_url: str):
        """Set cache base URL"""
        if "cache" not in self._config:
            self._config["cache"] = {}
        self._config["cache"]["base_url"] = base_url

    @property
    def cache_enabled(self) -> bool:
        """Get cache enabled status"""
        return self._config.get("cache", {}).get("enabled", False)

    def set_cache_enabled(self, enabled: bool):
        """Set cache enabled status"""
        if "cache" not in self._config:
            self._config["cache"] = {}
        self._config["cache"]["enabled"] = enabled

    @property
    def image_timeout(self) -> int:
        """Get image generation timeout in seconds"""
        return self._config.get("generation", {}).get("image_timeout", 300)

    def set_image_timeout(self, timeout: int):
        """Set image generation timeout in seconds"""
        if "generation" not in self._config:
            self._config["generation"] = {}
        self._config["generation"]["image_timeout"] = timeout

    @property
    def video_timeout(self) -> int:
        """Get video generation timeout in seconds"""
        return self._config.get("generation", {}).get("video_timeout", 3000)

    def set_video_timeout(self, timeout: int):
        """Set video generation timeout in seconds"""
        if "generation" not in self._config:
            self._config["generation"] = {}
        self._config["generation"]["video_timeout"] = timeout

    @property
    def watermark_free_enabled(self) -> bool:
        """Get watermark-free mode enabled status"""
        return self._config.get("watermark_free", {}).get("watermark_free_enabled", False)

    def set_watermark_free_enabled(self, enabled: bool):
        """Set watermark-free mode enabled/disabled"""
        if "watermark_free" not in self._config:
            self._config["watermark_free"] = {}
        self._config["watermark_free"]["watermark_free_enabled"] = enabled

    @property
    def watermark_free_parse_method(self) -> str:
        """Get watermark-free parse method"""
        return self._config.get("watermark_free", {}).get("parse_method", "third_party")

    @property
    def watermark_free_custom_url(self) -> str:
        """Get custom parse server URL"""
        return self._config.get("watermark_free", {}).get("custom_parse_url", "")

    @property
    def watermark_free_custom_token(self) -> str:
        """Get custom parse server access token"""
        return self._config.get("watermark_free", {}).get("custom_parse_token", "")

    @property
    def at_auto_refresh_enabled(self) -> bool:
        """Get AT auto refresh enabled status"""
        return self._config.get("token_refresh", {}).get("at_auto_refresh_enabled", False)

    def set_at_auto_refresh_enabled(self, enabled: bool):
        """Set AT auto refresh enabled/disabled"""
        if "token_refresh" not in self._config:
            self._config["token_refresh"] = {}
        self._config["token_refresh"]["at_auto_refresh_enabled"] = enabled

    @property
    def polling_mode_enabled(self) -> bool:
        """Get polling mode enabled status"""
        return self.call_logic_mode == "polling"

    @property
    def call_logic_mode(self) -> str:
        """Get call logic mode (default or polling)"""
        call_logic = self._config.get("call_logic", {})
        mode = call_logic.get("call_mode")
        if mode in ("default", "polling"):
            return mode
        if call_logic.get("polling_mode_enabled", False):
            return "polling"
        return "default"

    def set_polling_mode_enabled(self, enabled: bool):
        """Set polling mode enabled/disabled"""
        self.set_call_logic_mode("polling" if enabled else "default")

    def set_call_logic_mode(self, mode: str):
        """Set call logic mode (default or polling)"""
        normalized = "polling" if mode == "polling" else "default"
        if "call_logic" not in self._config:
            self._config["call_logic"] = {}
        self._config["call_logic"]["call_mode"] = normalized
        self._config["call_logic"]["polling_mode_enabled"] = normalized == "polling"

    @property
    def pow_proxy_enabled(self) -> bool:
        """Get POW proxy enabled status

        DEPRECATED: This configuration is deprecated. Use pow_service_proxy_enabled instead.
        All POW proxy settings are now unified under [pow_service] section.
        """
        return self._config.get("pow_proxy", {}).get("pow_proxy_enabled", False)

    def set_pow_proxy_enabled(self, enabled: bool):
        """Set POW proxy enabled/disabled

        DEPRECATED: This configuration is deprecated. Use set_pow_service_proxy_enabled instead.
        All POW proxy settings are now unified under [pow_service] section.
        """
        if "pow_proxy" not in self._config:
            self._config["pow_proxy"] = {}
        self._config["pow_proxy"]["pow_proxy_enabled"] = enabled

    @property
    def pow_proxy_url(self) -> str:
        """Get POW proxy URL

        DEPRECATED: This configuration is deprecated. Use pow_service_proxy_url instead.
        All POW proxy settings are now unified under [pow_service] section.
        """
        return self._config.get("pow_proxy", {}).get("pow_proxy_url", "")

    def set_pow_proxy_url(self, url: str):
        """Set POW proxy URL

        DEPRECATED: This configuration is deprecated. Use set_pow_service_proxy_url instead.
        All POW proxy settings are now unified under [pow_service] section.
        """
        if "pow_proxy" not in self._config:
            self._config["pow_proxy"] = {}
        self._config["pow_proxy"]["pow_proxy_url"] = url

    @property
    def pow_service_mode(self) -> str:
        """Get POW service mode (local or external)"""
        return self._config.get("pow_service", {}).get("mode", "local")

    def set_pow_service_mode(self, mode: str):
        """Set POW service mode"""
        if "pow_service" not in self._config:
            self._config["pow_service"] = {}
        self._config["pow_service"]["mode"] = mode

    @property
    def pow_service_server_url(self) -> str:
        """Get POW service server URL"""
        return self._config.get("pow_service", {}).get("server_url", "")

    def set_pow_service_server_url(self, url: str):
        """Set POW service server URL"""
        if "pow_service" not in self._config:
            self._config["pow_service"] = {}
        self._config["pow_service"]["server_url"] = url

    @property
    def pow_service_api_key(self) -> str:
        """Get POW service API key"""
        return self._config.get("pow_service", {}).get("api_key", "")

    def set_pow_service_api_key(self, api_key: str):
        """Set POW service API key"""
        if "pow_service" not in self._config:
            self._config["pow_service"] = {}
        self._config["pow_service"]["api_key"] = api_key

    @property
    def pow_service_proxy_enabled(self) -> bool:
        """Get POW service proxy enabled status"""
        return self._config.get("pow_service", {}).get("proxy_enabled", False)

    def set_pow_service_proxy_enabled(self, enabled: bool):
        """Set POW service proxy enabled status"""
        if "pow_service" not in self._config:
            self._config["pow_service"] = {}
        self._config["pow_service"]["proxy_enabled"] = enabled

    @property
    def pow_service_proxy_url(self) -> str:
        """Get POW service proxy URL"""
        return self._config.get("pow_service", {}).get("proxy_url", "")

    def set_pow_service_proxy_url(self, url: str):
        """Set POW service proxy URL"""
        if "pow_service" not in self._config:
            self._config["pow_service"] = {}
        self._config["pow_service"]["proxy_url"] = url

# Global config instance
config = Config()
