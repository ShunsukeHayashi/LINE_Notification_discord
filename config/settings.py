import os
from dotenv import load_dotenv
import logging
import re
from typing import Optional
from urllib.parse import urlparse
import json

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
load_dotenv(override=True)

class EnvironmentConfig:
    """環境設定の管理クラス"""
    
    def __init__(self):
        # テストモードの確認
        self.TESTING = os.getenv('TESTING', 'False').lower() == 'true'
        
        # 基本設定
        self.DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
        self.ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
        
        # Discord設定
        self.DISCORD_TOKEN = self._validate_token('DISCORD_TOKEN', required=True)
        self.DISCORD_CLIENT_ID = self._validate_token('DISCORD_CLIENT_ID')
        self.DISCORD_CLIENT_SECRET = self._validate_token('DISCORD_CLIENT_SECRET')
        
        # LINE Bot設定
        self.LINE_CHANNEL_ACCESS_TOKEN = self._validate_token('LINE_CHANNEL_ACCESS_TOKEN', required=True)
        self.LINE_CHANNEL_SECRET = self._validate_token('LINE_CHANNEL_SECRET', required=True)
        self.LINE_USER_ID = self._validate_token('LINE_USER_ID')
        
        # Supabase設定
        self.SUPABASE_URL = self._validate_url('SUPABASE_URL', required=True)
        self.SUPABASE_ANON_KEY = self._validate_token('SUPABASE_ANON_KEY', required=True)
        self.SUPABASE_SERVICE_ROLE_KEY = self._validate_token(
            'SUPABASE_SERVICE_ROLE_KEY',
            required=self.ENVIRONMENT == 'production'
        )
        
        # Webhook設定
        self.WEBHOOK_HANDLER_PATH = '/webhook'
        
        # 環境別の設定
        self._load_environment_specific_settings()

    def _validate_token(self, var_name: str, required: bool = False) -> Optional[str]:
        """トークンの検証"""
        value = os.getenv(var_name)
        if required and not value:
            raise ValueError(f"Required environment variable {var_name} is not set")
        
        if value and not self.TESTING:
            # テストモード以外でのトークンの形式チェック
            # LINEトークンは特殊文字を含むため、別の検証ルールを適用
            if var_name == 'LINE_CHANNEL_ACCESS_TOKEN':
                if not re.match(r'^[A-Za-z0-9+/=_\-\.]+$', value):
                    raise ValueError(f"Invalid token format for {var_name}")
            else:
                if not re.match(r'^[A-Za-z0-9_\-\.]+$', value):
                    raise ValueError(f"Invalid token format for {var_name}")
            
            # ログ出力（最初の10文字のみ）
            masked_value = value[:10] + "..." if len(value) > 10 else value
            logger.info(f"Loaded {var_name}: {masked_value}")
        
        return value

    def _validate_url(self, var_name: str, required: bool = False) -> Optional[str]:
        """URLの検証"""
        value = os.getenv(var_name)
        if required and not value:
            raise ValueError(f"Required environment variable {var_name} is not set")
        
        if value and not self.TESTING:
            try:
                result = urlparse(value)
                if not all([result.scheme, result.netloc]):
                    raise ValueError(f"Invalid URL format for {var_name}")
                
                # ログ出力（ホスト名のみ）
                logger.info(f"Loaded {var_name}: {result.netloc}")
            except Exception as e:
                raise ValueError(f"Invalid URL in {var_name}: {str(e)}")
        
        return value

    def _load_environment_specific_settings(self):
        """環境別の設定読み込み"""
        if self.TESTING:
            self.LOG_LEVEL = logging.DEBUG
            self.RETRY_ATTEMPTS = 1
            self.RETRY_DELAY = 0
            self.CONNECTION_TIMEOUT = 1
        elif self.ENVIRONMENT == 'development':
            self.LOG_LEVEL = logging.DEBUG
            self.RETRY_ATTEMPTS = 3
            self.RETRY_DELAY = 1
            self.CONNECTION_TIMEOUT = 5
        elif self.ENVIRONMENT == 'production':
            self.LOG_LEVEL = logging.INFO
            self.RETRY_ATTEMPTS = 5
            self.RETRY_DELAY = 2
            self.CONNECTION_TIMEOUT = 10
        else:
            raise ValueError(f"Invalid ENVIRONMENT value: {self.ENVIRONMENT}")

    def validate_all(self):
        """全設定の検証"""
        if self.TESTING:
            return  # テストモードでは詳細な検証をスキップ
            
        # Supabase設定の追加検証
        if self.ENVIRONMENT == 'production':
            if not self.SUPABASE_SERVICE_ROLE_KEY:
                raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required in production")
        
        # Discord設定の追加検証
        if self.DISCORD_TOKEN:
            if not re.match(r'^[A-Za-z0-9_\-\.]{50,}$', self.DISCORD_TOKEN):
                raise ValueError("Invalid Discord token format")
        
        # LINE設定の追加検証
        if self.LINE_CHANNEL_ACCESS_TOKEN:
            if not re.match(r'^[A-Za-z0-9+/=_\-\.]{100,}$', self.LINE_CHANNEL_ACCESS_TOKEN):
                raise ValueError("Invalid LINE Channel Access Token format")
        
        logger.info(f"Environment: {self.ENVIRONMENT}")
        logger.info(f"Debug mode: {self.DEBUG}")
        
        # 設定のエクスポート（機密情報を除く）
        self.export_settings()

    def export_settings(self):
        """設定のエクスポート（機密情報を除く）"""
        safe_settings = {
            'ENVIRONMENT': self.ENVIRONMENT,
            'DEBUG': self.DEBUG,
            'LOG_LEVEL': self.LOG_LEVEL,
            'RETRY_ATTEMPTS': self.RETRY_ATTEMPTS,
            'RETRY_DELAY': self.RETRY_DELAY,
            'CONNECTION_TIMEOUT': self.CONNECTION_TIMEOUT,
            'WEBHOOK_HANDLER_PATH': self.WEBHOOK_HANDLER_PATH
        }
        
        if self.DEBUG:
            settings_path = 'config/settings.json'
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            with open(settings_path, 'w') as f:
                json.dump(safe_settings, f, indent=2)
            logger.debug(f"Settings exported to {settings_path}")

# 設定のインスタンス化と検証
config = EnvironmentConfig()
config.validate_all()

# グローバル変数としてエクスポート
DISCORD_TOKEN = config.DISCORD_TOKEN
DISCORD_CLIENT_ID = config.DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET = config.DISCORD_CLIENT_SECRET
LINE_CHANNEL_ACCESS_TOKEN = config.LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET = config.LINE_CHANNEL_SECRET
LINE_USER_ID = config.LINE_USER_ID
SUPABASE_URL = config.SUPABASE_URL
SUPABASE_ANON_KEY = config.SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY = config.SUPABASE_SERVICE_ROLE_KEY
WEBHOOK_HANDLER_PATH = config.WEBHOOK_HANDLER_PATH
DEBUG = config.DEBUG
ENVIRONMENT = config.ENVIRONMENT
LOG_LEVEL = config.LOG_LEVEL
RETRY_ATTEMPTS = config.RETRY_ATTEMPTS
RETRY_DELAY = config.RETRY_DELAY
CONNECTION_TIMEOUT = config.CONNECTION_TIMEOUT