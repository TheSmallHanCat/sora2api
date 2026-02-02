"""Database storage layer"""
import aiosqlite
import json
from datetime import datetime
from typing import Optional, List
from pathlib import Path
from .models import Token, TokenStats, Task, RequestLog, AdminConfig, ProxyConfig, WatermarkFreeConfig, CacheConfig, GenerationConfig, TokenRefreshConfig

class Database:
    """SQLite database manager"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Store database in data directory
            data_dir = Path(__file__).parent.parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "hancat.db")
        self.db_path = db_path

    def db_exists(self) -> bool:
        """Check if database file exists"""
        return Path(self.db_path).exists()

    async def _table_exists(self, db, table_name: str) -> bool:
        """Check if a table exists in the database"""
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        result = await cursor.fetchone()
        return result is not None

    async def _column_exists(self, db, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table"""
        try:
            cursor = await db.execute(f"PRAGMA table_info({table_name})")
            columns = await cursor.fetchall()
            return any(col[1] == column_name for col in columns)
        except:
            return False

    async def _ensure_config_rows(self, db, config_dict: dict = None):
        """Ensure all config tables have their default rows

        Args:
            db: Database connection
            config_dict: Configuration dictionary from setting.toml (optional)
        """
        # Ensure admin_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM admin_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get admin credentials from config_dict if provided, otherwise use defaults
            admin_username = "admin"
            admin_password = "admin"
            api_key = "han1234"
            error_ban_threshold = 3
            task_retry_enabled = True
            task_max_retries = 3
            auto_disable_on_401 = True

            if config_dict:
                global_config = config_dict.get("global", {})
                admin_username = global_config.get("admin_username", "admin")
                admin_password = global_config.get("admin_password", "admin")
                api_key = global_config.get("api_key", "han1234")

                admin_config = config_dict.get("admin", {})
                error_ban_threshold = admin_config.get("error_ban_threshold", 3)
                task_retry_enabled = admin_config.get("task_retry_enabled", True)
                task_max_retries = admin_config.get("task_max_retries", 3)
                auto_disable_on_401 = admin_config.get("auto_disable_on_401", True)

            await db.execute("""
                INSERT INTO admin_config (id, admin_username, admin_password, api_key, error_ban_threshold, task_retry_enabled, task_max_retries, auto_disable_on_401)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            """, (admin_username, admin_password, api_key, error_ban_threshold, task_retry_enabled, task_max_retries, auto_disable_on_401))

        # Ensure proxy_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM proxy_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get proxy config from config_dict if provided, otherwise use defaults
            proxy_enabled = False
            proxy_url = None

            if config_dict:
                proxy_config = config_dict.get("proxy", {})
                proxy_enabled = proxy_config.get("proxy_enabled", False)
                proxy_url = proxy_config.get("proxy_url", "")
                # Convert empty string to None
                proxy_url = proxy_url if proxy_url else None

            await db.execute("""
                INSERT INTO proxy_config (id, proxy_enabled, proxy_url)
                VALUES (1, ?, ?)
            """, (proxy_enabled, proxy_url))

        # Ensure watermark_free_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM watermark_free_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get watermark-free config from config_dict if provided, otherwise use defaults
            watermark_free_enabled = False
            parse_method = "third_party"
            custom_parse_url = None
            custom_parse_token = None
            fallback_on_failure = True  # Default to True

            if config_dict:
                watermark_config = config_dict.get("watermark_free", {})
                watermark_free_enabled = watermark_config.get("watermark_free_enabled", False)
                parse_method = watermark_config.get("parse_method", "third_party")
                custom_parse_url = watermark_config.get("custom_parse_url", "")
                custom_parse_token = watermark_config.get("custom_parse_token", "")
                fallback_on_failure = watermark_config.get("fallback_on_failure", True)

                # Convert empty strings to None
                custom_parse_url = custom_parse_url if custom_parse_url else None
                custom_parse_token = custom_parse_token if custom_parse_token else None

            await db.execute("""
                INSERT INTO watermark_free_config (id, watermark_free_enabled, parse_method, custom_parse_url, custom_parse_token, fallback_on_failure)
                VALUES (1, ?, ?, ?, ?, ?)
            """, (watermark_free_enabled, parse_method, custom_parse_url, custom_parse_token, fallback_on_failure))

        # Ensure cache_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM cache_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get cache config from config_dict if provided, otherwise use defaults
            cache_enabled = False
            cache_timeout = 600
            cache_base_url = None

            if config_dict:
                cache_config = config_dict.get("cache", {})
                cache_enabled = cache_config.get("enabled", False)
                cache_timeout = cache_config.get("timeout", 600)
                cache_base_url = cache_config.get("base_url", "")
                # Convert empty string to None
                cache_base_url = cache_base_url if cache_base_url else None

            await db.execute("""
                INSERT INTO cache_config (id, cache_enabled, cache_timeout, cache_base_url)
                VALUES (1, ?, ?, ?)
            """, (cache_enabled, cache_timeout, cache_base_url))

        # Ensure generation_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM generation_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get generation config from config_dict if provided, otherwise use defaults
            image_timeout = 300
            video_timeout = 3000

            if config_dict:
                generation_config = config_dict.get("generation", {})
                image_timeout = generation_config.get("image_timeout", 300)
                video_timeout = generation_config.get("video_timeout", 3000)

            await db.execute("""
                INSERT INTO generation_config (id, image_timeout, video_timeout)
                VALUES (1, ?, ?)
            """, (image_timeout, video_timeout))

        # Ensure token_refresh_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM token_refresh_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get token refresh config from config_dict if provided, otherwise use defaults
            at_auto_refresh_enabled = False

            if config_dict:
                token_refresh_config = config_dict.get("token_refresh", {})
                at_auto_refresh_enabled = token_refresh_config.get("at_auto_refresh_enabled", False)

            await db.execute("""
                INSERT INTO token_refresh_config (id, at_auto_refresh_enabled)
                VALUES (1, ?)
            """, (at_auto_refresh_enabled,))

        # Ensure call_logic_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM call_logic_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get call logic config from config_dict if provided, otherwise use defaults
            call_mode = "default"
            polling_mode_enabled = False

            if config_dict:
                call_logic_config = config_dict.get("call_logic", {})
                call_mode = call_logic_config.get("call_mode", "default")
                # Normalize call_mode
                if call_mode not in ("default", "polling"):
                    # Check legacy polling_mode_enabled field
                    polling_mode_enabled = call_logic_config.get("polling_mode_enabled", False)
                    call_mode = "polling" if polling_mode_enabled else "default"
                else:
                    polling_mode_enabled = call_mode == "polling"

            await db.execute("""
                INSERT INTO call_logic_config (id, call_mode, polling_mode_enabled)
                VALUES (1, ?, ?)
            """, (call_mode, polling_mode_enabled))

        # Ensure pow_proxy_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM pow_proxy_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get POW proxy config from config_dict if provided, otherwise use defaults
            pow_proxy_enabled = False
            pow_proxy_url = None

            if config_dict:
                pow_proxy_config = config_dict.get("pow_proxy", {})
                pow_proxy_enabled = pow_proxy_config.get("pow_proxy_enabled", False)
                pow_proxy_url = pow_proxy_config.get("pow_proxy_url", "")
                # Convert empty string to None
                pow_proxy_url = pow_proxy_url if pow_proxy_url else None

            await db.execute("""
                INSERT INTO pow_proxy_config (id, pow_proxy_enabled, pow_proxy_url)
                VALUES (1, ?, ?)
            """, (pow_proxy_enabled, pow_proxy_url))

        # Ensure pow_service_config has a row
        cursor = await db.execute("SELECT COUNT(*) FROM pow_service_config")
        count = await cursor.fetchone()
        if count[0] == 0:
            # Get POW service config from config_dict if provided, otherwise use defaults
            mode = "local"
            server_url = None
            api_key = None
            proxy_enabled = False
            proxy_url = None

            if config_dict:
                pow_service_config = config_dict.get("pow_service", {})
                mode = pow_service_config.get("mode", "local")
                server_url = pow_service_config.get("server_url", "")
                api_key = pow_service_config.get("api_key", "")
                proxy_enabled = pow_service_config.get("proxy_enabled", False)
                proxy_url = pow_service_config.get("proxy_url", "")
                # Convert empty strings to None
                server_url = server_url if server_url else None
                api_key = api_key if api_key else None
                proxy_url = proxy_url if proxy_url else None

            await db.execute("""
                INSERT INTO pow_service_config (id, mode, server_url, api_key, proxy_enabled, proxy_url)
                VALUES (1, ?, ?, ?, ?, ?)
            """, (mode, server_url, api_key, proxy_enabled, proxy_url))


    async def check_and_migrate_db(self, config_dict: dict = None):
        """Check database integrity and perform migrations if needed

        Args:
            config_dict: Configuration dictionary from setting.toml (optional)
                        Used to initialize new tables with values from setting.toml
        """
        async with aiosqlite.connect(self.db_path) as db:
            print("Checking database integrity and performing migrations...")

            # Check and add missing columns to tokens table
            if await self._table_exists(db, "tokens"):
                columns_to_add = [
                    ("sora2_supported", "BOOLEAN"),
                    ("sora2_invite_code", "TEXT"),
                    ("sora2_redeemed_count", "INTEGER DEFAULT 0"),
                    ("sora2_total_count", "INTEGER DEFAULT 0"),
                    ("sora2_remaining_count", "INTEGER DEFAULT 0"),
                    ("sora2_cooldown_until", "TIMESTAMP"),
                    ("image_enabled", "BOOLEAN DEFAULT 1"),
                    ("video_enabled", "BOOLEAN DEFAULT 1"),
                    ("image_concurrency", "INTEGER DEFAULT -1"),
                    ("video_concurrency", "INTEGER DEFAULT -1"),
                    ("client_id", "TEXT"),
                    ("proxy_url", "TEXT"),
                    ("is_expired", "BOOLEAN DEFAULT 0"),
                ]

                for col_name, col_type in columns_to_add:
                    if not await self._column_exists(db, "tokens", col_name):
                        try:
                            await db.execute(f"ALTER TABLE tokens ADD COLUMN {col_name} {col_type}")
                            print(f"  ✓ Added column '{col_name}' to tokens table")
                        except Exception as e:
                            print(f"  ✗ Failed to add column '{col_name}': {e}")

            # Check and add missing columns to token_stats table
            if await self._table_exists(db, "token_stats"):
                columns_to_add = [
                    ("consecutive_error_count", "INTEGER DEFAULT 0"),
                ]

                for col_name, col_type in columns_to_add:
                    if not await self._column_exists(db, "token_stats", col_name):
                        try:
                            await db.execute(f"ALTER TABLE token_stats ADD COLUMN {col_name} {col_type}")
                            print(f"  ✓ Added column '{col_name}' to token_stats table")
                        except Exception as e:
                            print(f"  ✗ Failed to add column '{col_name}': {e}")

            # Check and add missing columns to admin_config table
            if await self._table_exists(db, "admin_config"):
                columns_to_add = [
                    ("admin_username", "TEXT DEFAULT 'admin'"),
                    ("admin_password", "TEXT DEFAULT 'admin'"),
                    ("api_key", "TEXT DEFAULT 'han1234'"),
                ]

                for col_name, col_type in columns_to_add:
                    if not await self._column_exists(db, "admin_config", col_name):
                        try:
                            await db.execute(f"ALTER TABLE admin_config ADD COLUMN {col_name} {col_type}")
                            print(f"  ✓ Added column '{col_name}' to admin_config table")
                        except Exception as e:
                            print(f"  ✗ Failed to add column '{col_name}': {e}")

            # Check and add missing columns to watermark_free_config table
            if await self._table_exists(db, "watermark_free_config"):
                columns_to_add = [
                    ("parse_method", "TEXT DEFAULT 'third_party'"),
                    ("custom_parse_url", "TEXT"),
                    ("custom_parse_token", "TEXT"),
                    ("fallback_on_failure", "BOOLEAN DEFAULT 1"),
                ]

                for col_name, col_type in columns_to_add:
                    if not await self._column_exists(db, "watermark_free_config", col_name):
                        try:
                            await db.execute(f"ALTER TABLE watermark_free_config ADD COLUMN {col_name} {col_type}")
                            print(f"  ✓ Added column '{col_name}' to watermark_free_config table")
                        except Exception as e:
                            print(f"  ✗ Failed to add column '{col_name}': {e}")

            # Check and add missing columns to request_logs table
            if await self._table_exists(db, "request_logs"):
                columns_to_add = [
                    ("task_id", "TEXT"),
                    ("updated_at", "TIMESTAMP"),
                ]

                for col_name, col_type in columns_to_add:
                    if not await self._column_exists(db, "request_logs", col_name):
                        try:
                            await db.execute(f"ALTER TABLE request_logs ADD COLUMN {col_name} {col_type}")
                            print(f"  ✓ Added column '{col_name}' to request_logs table")
                        except Exception as e:
                            print(f"  ✗ Failed to add column '{col_name}': {e}")

            # Ensure all config tables have their default rows
            # Pass config_dict if available to initialize from setting.toml
            await self._ensure_config_rows(db, config_dict)

            await db.commit()
            print("Database migration check completed.")

    async def init_db(self):
        """Initialize database tables - creates all tables and ensures data integrity"""
        async with aiosqlite.connect(self.db_path) as db:
            # Tokens table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT UNIQUE NOT NULL,
                    email TEXT NOT NULL,
                    username TEXT NOT NULL,
                    name TEXT NOT NULL,
                    st TEXT,
                    rt TEXT,
                    client_id TEXT,
                    proxy_url TEXT,
                    remark TEXT,
                    expiry_time TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    cooled_until TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    use_count INTEGER DEFAULT 0,
                    plan_type TEXT,
                    plan_title TEXT,
                    subscription_end TIMESTAMP,
                    sora2_supported BOOLEAN,
                    sora2_invite_code TEXT,
                    sora2_redeemed_count INTEGER DEFAULT 0,
                    sora2_total_count INTEGER DEFAULT 0,
                    sora2_remaining_count INTEGER DEFAULT 0,
                    sora2_cooldown_until TIMESTAMP,
                    image_enabled BOOLEAN DEFAULT 1,
                    video_enabled BOOLEAN DEFAULT 1,
                    image_concurrency INTEGER DEFAULT -1,
                    video_concurrency INTEGER DEFAULT -1,
                    is_expired BOOLEAN DEFAULT 0
                )
            """)

            # Token stats table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS token_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER NOT NULL,
                    image_count INTEGER DEFAULT 0,
                    video_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    last_error_at TIMESTAMP,
                    today_image_count INTEGER DEFAULT 0,
                    today_video_count INTEGER DEFAULT 0,
                    today_error_count INTEGER DEFAULT 0,
                    today_date DATE,
                    consecutive_error_count INTEGER DEFAULT 0,
                    FOREIGN KEY (token_id) REFERENCES tokens(id)
                )
            """)

            # Tasks table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE NOT NULL,
                    token_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'processing',
                    progress FLOAT DEFAULT 0,
                    result_urls TEXT,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (token_id) REFERENCES tokens(id)
                )
            """)

            # Request logs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_id INTEGER,
                    task_id TEXT,
                    operation TEXT NOT NULL,
                    request_body TEXT,
                    response_body TEXT,
                    status_code INTEGER NOT NULL,
                    duration FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY (token_id) REFERENCES tokens(id)
                )
            """)

            # Admin config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admin_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    admin_username TEXT DEFAULT 'admin',
                    admin_password TEXT DEFAULT 'admin',
                    api_key TEXT DEFAULT 'han1234',
                    error_ban_threshold INTEGER DEFAULT 3,
                    task_retry_enabled BOOLEAN DEFAULT 1,
                    task_max_retries INTEGER DEFAULT 3,
                    auto_disable_on_401 BOOLEAN DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Proxy config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS proxy_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    proxy_enabled BOOLEAN DEFAULT 0,
                    proxy_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Watermark-free config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watermark_free_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    watermark_free_enabled BOOLEAN DEFAULT 0,
                    parse_method TEXT DEFAULT 'third_party',
                    custom_parse_url TEXT,
                    custom_parse_token TEXT,
                    fallback_on_failure BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Cache config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cache_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    cache_enabled BOOLEAN DEFAULT 0,
                    cache_timeout INTEGER DEFAULT 600,
                    cache_base_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Generation config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS generation_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    image_timeout INTEGER DEFAULT 300,
                    video_timeout INTEGER DEFAULT 3000,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Token refresh config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS token_refresh_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    at_auto_refresh_enabled BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Call logic config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS call_logic_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    call_mode TEXT DEFAULT 'default',
                    polling_mode_enabled BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # POW proxy config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pow_proxy_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    pow_proxy_enabled BOOLEAN DEFAULT 0,
                    pow_proxy_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create pow_service_config table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pow_service_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    mode TEXT DEFAULT 'local',
                    server_url TEXT,
                    api_key TEXT,
                    proxy_enabled BOOLEAN DEFAULT 0,
                    proxy_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON tasks(task_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_token_active ON tokens(is_active)")

            # Migration: Add daily statistics columns if they don't exist
            if not await self._column_exists(db, "token_stats", "today_image_count"):
                await db.execute("ALTER TABLE token_stats ADD COLUMN today_image_count INTEGER DEFAULT 0")
            if not await self._column_exists(db, "token_stats", "today_video_count"):
                await db.execute("ALTER TABLE token_stats ADD COLUMN today_video_count INTEGER DEFAULT 0")
            if not await self._column_exists(db, "token_stats", "today_error_count"):
                await db.execute("ALTER TABLE token_stats ADD COLUMN today_error_count INTEGER DEFAULT 0")
            if not await self._column_exists(db, "token_stats", "today_date"):
                await db.execute("ALTER TABLE token_stats ADD COLUMN today_date DATE")

            # Migration: Add retry_count column to tasks table if it doesn't exist
            if not await self._column_exists(db, "tasks", "retry_count"):
                await db.execute("ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0")

            # Migration: Add task retry config columns to admin_config table if they don't exist
            if not await self._column_exists(db, "admin_config", "task_retry_enabled"):
                await db.execute("ALTER TABLE admin_config ADD COLUMN task_retry_enabled BOOLEAN DEFAULT 1")
            if not await self._column_exists(db, "admin_config", "task_max_retries"):
                await db.execute("ALTER TABLE admin_config ADD COLUMN task_max_retries INTEGER DEFAULT 3")
            if not await self._column_exists(db, "admin_config", "auto_disable_on_401"):
                await db.execute("ALTER TABLE admin_config ADD COLUMN auto_disable_on_401 BOOLEAN DEFAULT 1")

            await db.commit()

    async def init_config_from_toml(self, config_dict: dict, is_first_startup: bool = True):
        """
        Initialize database configuration from setting.toml

        Args:
            config_dict: Configuration dictionary from setting.toml
            is_first_startup: If True, initialize all config rows from setting.toml.
                            If False (upgrade mode), only ensure missing config rows exist with default values.
        """
        async with aiosqlite.connect(self.db_path) as db:
            if is_first_startup:
                # First startup: Initialize all config tables with values from setting.toml
                await self._ensure_config_rows(db, config_dict)
            else:
                # Upgrade mode: Only ensure missing config rows exist (with default values, not from TOML)
                await self._ensure_config_rows(db, config_dict=None)

            await db.commit()

    # Token operations
    async def add_token(self, token: Token) -> int:
        """Add a new token"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO tokens (token, email, username, name, st, rt, client_id, proxy_url, remark, expiry_time, is_active,
                                   plan_type, plan_title, subscription_end, sora2_supported, sora2_invite_code,
                                   sora2_redeemed_count, sora2_total_count, sora2_remaining_count, sora2_cooldown_until,
                                   image_enabled, video_enabled, image_concurrency, video_concurrency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (token.token, token.email, "", token.name, token.st, token.rt, token.client_id, token.proxy_url,
                  token.remark, token.expiry_time, token.is_active,
                  token.plan_type, token.plan_title, token.subscription_end,
                  token.sora2_supported, token.sora2_invite_code,
                  token.sora2_redeemed_count, token.sora2_total_count,
                  token.sora2_remaining_count, token.sora2_cooldown_until,
                  token.image_enabled, token.video_enabled,
                  token.image_concurrency, token.video_concurrency))
            await db.commit()
            token_id = cursor.lastrowid

            # Create stats entry
            await db.execute("""
                INSERT INTO token_stats (token_id) VALUES (?)
            """, (token_id,))
            await db.commit()

            return token_id
    
    async def get_token(self, token_id: int) -> Optional[Token]:
        """Get token by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tokens WHERE id = ?", (token_id,))
            row = await cursor.fetchone()
            if row:
                return Token(**dict(row))
            return None
    
    async def get_token_by_value(self, token: str) -> Optional[Token]:
        """Get token by value"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tokens WHERE token = ?", (token,))
            row = await cursor.fetchone()
            if row:
                return Token(**dict(row))
            return None

    async def get_token_by_email(self, email: str) -> Optional[Token]:
        """Get token by email"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tokens WHERE email = ?", (email,))
            row = await cursor.fetchone()
            if row:
                return Token(**dict(row))
            return None
    
    async def get_active_tokens(self) -> List[Token]:
        """Get all active tokens (enabled, not cooled down, not expired)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM tokens
                WHERE is_active = 1
                AND (cooled_until IS NULL OR cooled_until < CURRENT_TIMESTAMP)
                AND expiry_time > CURRENT_TIMESTAMP
                ORDER BY last_used_at ASC NULLS FIRST
            """)
            rows = await cursor.fetchall()
            return [Token(**dict(row)) for row in rows]
    
    async def get_all_tokens(self) -> List[Token]:
        """Get all tokens"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tokens ORDER BY created_at DESC")
            rows = await cursor.fetchall()
            return [Token(**dict(row)) for row in rows]
    
    async def update_token_usage(self, token_id: int):
        """Update token usage"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens 
                SET last_used_at = CURRENT_TIMESTAMP, use_count = use_count + 1
                WHERE id = ?
            """, (token_id,))
            await db.commit()
    
    async def update_token_status(self, token_id: int, is_active: bool):
        """Update token status"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens SET is_active = ? WHERE id = ?
            """, (is_active, token_id))
            await db.commit()

    async def mark_token_expired(self, token_id: int):
        """Mark token as expired and disable it"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens SET is_expired = 1, is_active = 0 WHERE id = ?
            """, (token_id,))
            await db.commit()

    async def clear_token_expired(self, token_id: int):
        """Clear token expired flag"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens SET is_expired = 0 WHERE id = ?
            """, (token_id,))
            await db.commit()

    async def update_token_sora2(self, token_id: int, supported: bool, invite_code: Optional[str] = None,
                                redeemed_count: int = 0, total_count: int = 0, remaining_count: int = 0):
        """Update token Sora2 support info"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens
                SET sora2_supported = ?, sora2_invite_code = ?, sora2_redeemed_count = ?, sora2_total_count = ?, sora2_remaining_count = ?
                WHERE id = ?
            """, (supported, invite_code, redeemed_count, total_count, remaining_count, token_id))
            await db.commit()

    async def update_token_sora2_remaining(self, token_id: int, remaining_count: int):
        """Update token Sora2 remaining count"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens SET sora2_remaining_count = ? WHERE id = ?
            """, (remaining_count, token_id))
            await db.commit()

    async def update_token_sora2_cooldown(self, token_id: int, cooldown_until: Optional[datetime]):
        """Update token Sora2 cooldown time"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens SET sora2_cooldown_until = ? WHERE id = ?
            """, (cooldown_until, token_id))
            await db.commit()

    async def update_token_cooldown(self, token_id: int, cooled_until: datetime):
        """Update token cooldown"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tokens SET cooled_until = ? WHERE id = ?
            """, (cooled_until, token_id))
            await db.commit()
    
    async def delete_token(self, token_id: int):
        """Delete token"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM token_stats WHERE token_id = ?", (token_id,))
            await db.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
            await db.commit()

    async def update_token(self, token_id: int,
                          token: Optional[str] = None,
                          st: Optional[str] = None,
                          rt: Optional[str] = None,
                          client_id: Optional[str] = None,
                          proxy_url: Optional[str] = None,
                          remark: Optional[str] = None,
                          expiry_time: Optional[datetime] = None,
                          plan_type: Optional[str] = None,
                          plan_title: Optional[str] = None,
                          subscription_end: Optional[datetime] = None,
                          image_enabled: Optional[bool] = None,
                          video_enabled: Optional[bool] = None,
                          image_concurrency: Optional[int] = None,
                          video_concurrency: Optional[int] = None):
        """Update token (AT, ST, RT, client_id, proxy_url, remark, expiry_time, subscription info, image_enabled, video_enabled)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Build dynamic update query
            updates = []
            params = []

            if token is not None:
                updates.append("token = ?")
                params.append(token)

            if st is not None:
                updates.append("st = ?")
                params.append(st)

            if rt is not None:
                updates.append("rt = ?")
                params.append(rt)

            if client_id is not None:
                updates.append("client_id = ?")
                params.append(client_id)

            if proxy_url is not None:
                updates.append("proxy_url = ?")
                params.append(proxy_url)

            if remark is not None:
                updates.append("remark = ?")
                params.append(remark)

            if expiry_time is not None:
                updates.append("expiry_time = ?")
                params.append(expiry_time)

            if plan_type is not None:
                updates.append("plan_type = ?")
                params.append(plan_type)

            if plan_title is not None:
                updates.append("plan_title = ?")
                params.append(plan_title)

            if subscription_end is not None:
                updates.append("subscription_end = ?")
                params.append(subscription_end)

            if image_enabled is not None:
                updates.append("image_enabled = ?")
                params.append(image_enabled)

            if video_enabled is not None:
                updates.append("video_enabled = ?")
                params.append(video_enabled)

            if image_concurrency is not None:
                updates.append("image_concurrency = ?")
                params.append(image_concurrency)

            if video_concurrency is not None:
                updates.append("video_concurrency = ?")
                params.append(video_concurrency)

            if updates:
                params.append(token_id)
                query = f"UPDATE tokens SET {', '.join(updates)} WHERE id = ?"
                await db.execute(query, params)
                await db.commit()

    # Token stats operations
    async def get_token_stats(self, token_id: int) -> Optional[TokenStats]:
        """Get token statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM token_stats WHERE token_id = ?", (token_id,))
            row = await cursor.fetchone()
            if row:
                return TokenStats(**dict(row))
            return None
    
    async def increment_image_count(self, token_id: int):
        """Increment image generation count"""
        from datetime import date
        async with aiosqlite.connect(self.db_path) as db:
            today = str(date.today())
            # Get current stats
            cursor = await db.execute("SELECT today_date FROM token_stats WHERE token_id = ?", (token_id,))
            row = await cursor.fetchone()

            # If date changed, reset today's count
            if row and row[0] != today:
                await db.execute("""
                    UPDATE token_stats
                    SET image_count = image_count + 1,
                        today_image_count = 1,
                        today_date = ?
                    WHERE token_id = ?
                """, (today, token_id))
            else:
                # Same day, just increment both
                await db.execute("""
                    UPDATE token_stats
                    SET image_count = image_count + 1,
                        today_image_count = today_image_count + 1,
                        today_date = ?
                    WHERE token_id = ?
                """, (today, token_id))
            await db.commit()

    async def increment_video_count(self, token_id: int):
        """Increment video generation count"""
        from datetime import date
        async with aiosqlite.connect(self.db_path) as db:
            today = str(date.today())
            # Get current stats
            cursor = await db.execute("SELECT today_date FROM token_stats WHERE token_id = ?", (token_id,))
            row = await cursor.fetchone()

            # If date changed, reset today's count
            if row and row[0] != today:
                await db.execute("""
                    UPDATE token_stats
                    SET video_count = video_count + 1,
                        today_video_count = 1,
                        today_date = ?
                    WHERE token_id = ?
                """, (today, token_id))
            else:
                # Same day, just increment both
                await db.execute("""
                    UPDATE token_stats
                    SET video_count = video_count + 1,
                        today_video_count = today_video_count + 1,
                        today_date = ?
                    WHERE token_id = ?
                """, (today, token_id))
            await db.commit()
    
    async def increment_error_count(self, token_id: int, increment_consecutive: bool = True):
        """Increment error count

        Args:
            token_id: Token ID
            increment_consecutive: Whether to increment consecutive error count (False for overload errors)
        """
        from datetime import date
        async with aiosqlite.connect(self.db_path) as db:
            today = str(date.today())
            # Get current stats
            cursor = await db.execute("SELECT today_date FROM token_stats WHERE token_id = ?", (token_id,))
            row = await cursor.fetchone()

            # If date changed, reset today's error count
            if row and row[0] != today:
                if increment_consecutive:
                    await db.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            consecutive_error_count = consecutive_error_count + 1,
                            today_error_count = 1,
                            today_date = ?,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = ?
                    """, (today, token_id))
                else:
                    await db.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            today_error_count = 1,
                            today_date = ?,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = ?
                    """, (today, token_id))
            else:
                # Same day, just increment counters
                if increment_consecutive:
                    await db.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            consecutive_error_count = consecutive_error_count + 1,
                            today_error_count = today_error_count + 1,
                            today_date = ?,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = ?
                    """, (today, token_id))
                else:
                    await db.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            today_error_count = today_error_count + 1,
                            today_date = ?,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = ?
                    """, (today, token_id))
            await db.commit()
    
    async def reset_error_count(self, token_id: int):
        """Reset consecutive error count (keep total error_count)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE token_stats SET consecutive_error_count = 0 WHERE token_id = ?
            """, (token_id,))
            await db.commit()
    
    # Task operations
    async def create_task(self, task: Task) -> int:
        """Create a new task"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO tasks (task_id, token_id, model, prompt, status, progress)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task.task_id, task.token_id, task.model, task.prompt, task.status, task.progress))
            await db.commit()
            return cursor.lastrowid
    
    async def update_task(self, task_id: str, status: str, progress: float, 
                         result_urls: Optional[str] = None, error_message: Optional[str] = None):
        """Update task status"""
        async with aiosqlite.connect(self.db_path) as db:
            completed_at = datetime.now() if status in ["completed", "failed"] else None
            await db.execute("""
                UPDATE tasks 
                SET status = ?, progress = ?, result_urls = ?, error_message = ?, completed_at = ?
                WHERE task_id = ?
            """, (status, progress, result_urls, error_message, completed_at, task_id))
            await db.commit()
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = await cursor.fetchone()
            if row:
                return Task(**dict(row))
            return None
    
    # Request log operations
    async def log_request(self, log: RequestLog) -> int:
        """Log a request and return log ID"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO request_logs (token_id, task_id, operation, request_body, response_body, status_code, duration)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (log.token_id, log.task_id, log.operation, log.request_body, log.response_body,
                  log.status_code, log.duration))
            await db.commit()
            return cursor.lastrowid

    async def update_request_log(self, log_id: int, response_body: Optional[str] = None,
                                 status_code: Optional[int] = None, duration: Optional[float] = None):
        """Update request log with completion data"""
        async with aiosqlite.connect(self.db_path) as db:
            updates = []
            params = []

            if response_body is not None:
                updates.append("response_body = ?")
                params.append(response_body)
            if status_code is not None:
                updates.append("status_code = ?")
                params.append(status_code)
            if duration is not None:
                updates.append("duration = ?")
                params.append(duration)

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(log_id)
                query = f"UPDATE request_logs SET {', '.join(updates)} WHERE id = ?"
                await db.execute(query, params)
                await db.commit()

    async def update_request_log_task_id(self, log_id: int, task_id: str):
        """Update request log with task_id"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE request_logs
                SET task_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (task_id, log_id))
            await db.commit()

    async def get_recent_logs(self, limit: int = 100) -> List[dict]:
        """Get recent logs with token email"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT
                    rl.id,
                    rl.token_id,
                    rl.task_id,
                    rl.operation,
                    rl.request_body,
                    rl.response_body,
                    rl.status_code,
                    rl.duration,
                    rl.created_at,
                    t.email as token_email,
                    t.username as token_username
                FROM request_logs rl
                LEFT JOIN tokens t ON rl.token_id = t.id
                ORDER BY rl.created_at DESC
                LIMIT ?
            """, (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def clear_all_logs(self):
        """Clear all request logs"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM request_logs")
            await db.commit()

    # Admin config operations
    async def get_admin_config(self) -> AdminConfig:
        """Get admin configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM admin_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return AdminConfig(**dict(row))
            # If no row exists, return a default config with placeholder values
            # This should not happen in normal operation as _ensure_config_rows should create it
            return AdminConfig(admin_username="admin", admin_password="admin", api_key="han1234")
    
    async def update_admin_config(self, config: AdminConfig):
        """Update admin configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE admin_config
                SET admin_username = ?, admin_password = ?, api_key = ?, error_ban_threshold = ?,
                    task_retry_enabled = ?, task_max_retries = ?, auto_disable_on_401 = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (config.admin_username, config.admin_password, config.api_key, config.error_ban_threshold,
                  config.task_retry_enabled, config.task_max_retries, config.auto_disable_on_401))
            await db.commit()
    
    # Proxy config operations
    async def get_proxy_config(self) -> ProxyConfig:
        """Get proxy configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM proxy_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return ProxyConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return ProxyConfig(proxy_enabled=False)
    
    async def update_proxy_config(self, enabled: bool, proxy_url: Optional[str]):
        """Update proxy configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE proxy_config
                SET proxy_enabled = ?, proxy_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (enabled, proxy_url))
            await db.commit()

    # Watermark-free config operations
    async def get_watermark_free_config(self) -> WatermarkFreeConfig:
        """Get watermark-free configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM watermark_free_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return WatermarkFreeConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return WatermarkFreeConfig(watermark_free_enabled=False, parse_method="third_party")

    async def update_watermark_free_config(self, enabled: bool, parse_method: str = None,
                                          custom_parse_url: str = None, custom_parse_token: str = None,
                                          fallback_on_failure: bool = None):
        """Update watermark-free configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            if parse_method is None and custom_parse_url is None and custom_parse_token is None and fallback_on_failure is None:
                # Only update enabled status
                await db.execute("""
                    UPDATE watermark_free_config
                    SET watermark_free_enabled = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (enabled,))
            else:
                # Update all fields
                await db.execute("""
                    UPDATE watermark_free_config
                    SET watermark_free_enabled = ?, parse_method = ?, custom_parse_url = ?,
                        custom_parse_token = ?, fallback_on_failure = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, (enabled, parse_method or "third_party", custom_parse_url, custom_parse_token,
                      fallback_on_failure if fallback_on_failure is not None else True))
            await db.commit()

    # Cache config operations
    async def get_cache_config(self) -> CacheConfig:
        """Get cache configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM cache_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return CacheConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return CacheConfig(cache_enabled=False, cache_timeout=600)

    async def update_cache_config(self, enabled: bool = None, timeout: int = None, base_url: Optional[str] = None):
        """Update cache configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            # Get current config first
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM cache_config WHERE id = 1")
            row = await cursor.fetchone()

            if row:
                current = dict(row)
                # Update only provided fields
                new_enabled = enabled if enabled is not None else current.get("cache_enabled", False)
                new_timeout = timeout if timeout is not None else current.get("cache_timeout", 600)
                new_base_url = base_url if base_url is not None else current.get("cache_base_url")
            else:
                new_enabled = enabled if enabled is not None else False
                new_timeout = timeout if timeout is not None else 600
                new_base_url = base_url

            # Convert empty string to None
            new_base_url = new_base_url if new_base_url else None

            await db.execute("""
                UPDATE cache_config
                SET cache_enabled = ?, cache_timeout = ?, cache_base_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (new_enabled, new_timeout, new_base_url))
            await db.commit()

    # Generation config operations
    async def get_generation_config(self) -> GenerationConfig:
        """Get generation configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM generation_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return GenerationConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return GenerationConfig(image_timeout=300, video_timeout=3000)

    async def update_generation_config(self, image_timeout: int = None, video_timeout: int = None):
        """Update generation configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            # Get current config first
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM generation_config WHERE id = 1")
            row = await cursor.fetchone()

            if row:
                current = dict(row)
                # Update only provided fields
                new_image_timeout = image_timeout if image_timeout is not None else current.get("image_timeout", 300)
                new_video_timeout = video_timeout if video_timeout is not None else current.get("video_timeout", 3000)
            else:
                new_image_timeout = image_timeout if image_timeout is not None else 300
                new_video_timeout = video_timeout if video_timeout is not None else 3000

            await db.execute("""
                UPDATE generation_config
                SET image_timeout = ?, video_timeout = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (new_image_timeout, new_video_timeout))
            await db.commit()

    # Token refresh config operations
    async def get_token_refresh_config(self) -> TokenRefreshConfig:
        """Get token refresh configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM token_refresh_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return TokenRefreshConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return TokenRefreshConfig(at_auto_refresh_enabled=False)

    async def update_token_refresh_config(self, at_auto_refresh_enabled: bool):
        """Update token refresh configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE token_refresh_config
                SET at_auto_refresh_enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, (at_auto_refresh_enabled,))
            await db.commit()

    # Call logic config operations
    async def get_call_logic_config(self) -> "CallLogicConfig":
        """Get call logic configuration"""
        from .models import CallLogicConfig
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM call_logic_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                row_dict = dict(row)
                if not row_dict.get("call_mode"):
                    row_dict["call_mode"] = "polling" if row_dict.get("polling_mode_enabled") else "default"
                return CallLogicConfig(**row_dict)
            return CallLogicConfig(call_mode="default", polling_mode_enabled=False)

    async def update_call_logic_config(self, call_mode: str):
        """Update call logic configuration"""
        normalized = "polling" if call_mode == "polling" else "default"
        polling_mode_enabled = normalized == "polling"
        async with aiosqlite.connect(self.db_path) as db:
            # Use INSERT OR REPLACE to ensure the row exists
            await db.execute("""
                INSERT OR REPLACE INTO call_logic_config (id, call_mode, polling_mode_enabled, updated_at)
                VALUES (1, ?, ?, CURRENT_TIMESTAMP)
            """, (normalized, polling_mode_enabled))
            await db.commit()

    # POW proxy config operations
    async def get_pow_proxy_config(self) -> "PowProxyConfig":
        """Get POW proxy configuration"""
        from .models import PowProxyConfig
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM pow_proxy_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return PowProxyConfig(**dict(row))
            return PowProxyConfig(pow_proxy_enabled=False, pow_proxy_url=None)

    async def get_pow_service_config(self) -> "PowServiceConfig":
        """Get POW service configuration"""
        from .models import PowServiceConfig
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM pow_service_config WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return PowServiceConfig(**dict(row))
            return PowServiceConfig(
                mode="local",
                server_url=None,
                api_key=None,
                proxy_enabled=False,
                proxy_url=None
            )

    async def update_pow_proxy_config(self, pow_proxy_enabled: bool, pow_proxy_url: Optional[str] = None):
        """Update POW proxy configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            # Use INSERT OR REPLACE to ensure the row exists
            await db.execute("""
                INSERT OR REPLACE INTO pow_proxy_config (id, pow_proxy_enabled, pow_proxy_url, updated_at)
                VALUES (1, ?, ?, CURRENT_TIMESTAMP)
            """, (pow_proxy_enabled, pow_proxy_url))
            await db.commit()

    async def update_pow_service_config(
        self,
        mode: str,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        proxy_enabled: Optional[bool] = None,
        proxy_url: Optional[str] = None
    ):
        """Update POW service configuration"""
        async with aiosqlite.connect(self.db_path) as db:
            # Use INSERT OR REPLACE to ensure the row exists
            await db.execute("""
                INSERT OR REPLACE INTO pow_service_config (id, mode, server_url, api_key, proxy_enabled, proxy_url, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (mode, server_url, api_key, proxy_enabled, proxy_url))
            await db.commit()


