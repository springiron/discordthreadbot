#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot設定を一元管理するモジュール
環境変数の読み込みと設定値の検証・変換を担当
"""

import os
import logging
from typing import List, Dict, Any, Set, Optional, Union, Callable
import sys

# 基本的なロギング設定（config.pyが最初に読み込まれる可能性があるため）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("config")

# 設定値のスキーマ定義
class ConfigSchema:
    """設定値のスキーマ定義（型情報、デフォルト値、検証ルールなど）"""
    
    def __init__(self):
        # Bot設定
        self.DISCORD_BOT_TOKEN = {
            "type": str,
            "default": "",
            "env_var": ["DISCORD_BOT_TOKEN", "BOT_TOKEN"],  # 複数の環境変数名をサポート
            "required": True,
            "description": "Discord Bot APIトークン"
        }
        
        # デバッグモード
        self.DEBUG_MODE = {
            "type": bool,
            "default": False,
            "env_var": "DEBUG_MODE",
            "converter": lambda x: str(x).lower() == "true" if isinstance(x, str) else bool(x),
            "description": "デバッグモードの有効/無効"
        }
        
        # ロギングレベル
        self.LOG_LEVEL = {
            "type": str,
            "default": "INFO",
            "env_var": "LOG_LEVEL",
            "validator": lambda x: x in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
            "description": "ロギングレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）"
        }
        
        # スレッド設定
        self.THREAD_AUTO_ARCHIVE_DURATION = {
            "type": int,
            "default": 10080,  # 1週間（分）
            "env_var": "THREAD_AUTO_ARCHIVE_DURATION",
            "description": "スレッド自動アーカイブ時間（分）"
        }
        
        self.THREAD_NAME_TEMPLATE = {
            "type": str,
            "default": "{username}の募集",
            "env_var": "THREAD_NAME_TEMPLATE",
            "description": "スレッド名のテンプレート（{username}は投稿者名に置換）"
        }
        
        # トリガーキーワード
        self.TRIGGER_KEYWORDS = {
            "type": list,
            "default": ["募集"],
            "env_var": "TRIGGER_KEYWORDS",
            "converter": lambda x: x.split(",") if isinstance(x, str) else x,
            "description": "スレッド作成のトリガーとなるキーワード（カンマ区切り）"
        }
        
        # 有効なチャンネル
        self.ENABLED_CHANNEL_IDS = {
            "type": set,
            "default": set(),
            "env_var": "ENABLED_CHANNEL_IDS",
            "converter": lambda x: {int(channel_id.strip()) for channel_id in x.split(",") if channel_id.strip()} if isinstance(x, str) else x,
            "description": "有効なチャンネルIDのリスト（カンマ区切り）"
        }
        
        # キープアライブ設定
        self.KEEP_ALIVE_ENABLED = {
            "type": bool,
            "default": True,
            "env_var": "KEEP_ALIVE_ENABLED",
            "converter": lambda x: str(x).lower() == "true" if isinstance(x, str) else bool(x),
            "description": "キープアライブ機能の有効/無効"
        }
        
        self.KEEP_ALIVE_INTERVAL = {
            "type": int,
            "default": 30,
            "env_var": "KEEP_ALIVE_INTERVAL",
            "converter": lambda x: int(x) if isinstance(x, str) and x.isdigit() else 30,
            "description": "キープアライブ間隔（分）"
        }
        
        # HTTPサーバーポート
        self.PORT = {
            "type": int,
            "default": 8080,
            "env_var": "PORT",
            "converter": lambda x: int(x) if isinstance(x, str) and x.isdigit() else 8080,
            "description": "ヘルスチェックサーバーのポート番号"
        }
        
        # Botの意図設定
        self.BOT_INTENTS = {
            "type": dict,
            "default": {
                "message_content": True,
                "guilds": True,
                "guild_messages": True,
            },
            "description": "Botの意図（intents）設定"
        }

class Config:
    """設定管理クラス"""
    
    def __init__(self):
        # スキーマの取得
        self._schema = ConfigSchema()
        
        # 環境変数から読み込んだ値を保持する辞書
        self._values = {}
        
        # .envファイルの読み込み（あれば）
        self._load_env_file()
        
        # 全ての設定値を読み込む
        self._load_all_settings()
        
    def _load_env_file(self) -> bool:
        """
        .envファイルがあれば読み込む
        
        Returns:
            bool: .envファイルを読み込めた場合はTrue
        """
        try:
            from dotenv import load_dotenv
            loaded = load_dotenv()
            if loaded:
                logger.info(".envファイルから環境変数を読み込みました")
            return loaded
        except ImportError:
            logger.warning("python-dotenvがインストールされていません")
            return False
    
    def _load_all_settings(self):
        """スキーマ定義に基づいて全ての設定値を読み込む"""
        # スキーマのすべての属性に対して処理
        for attr_name in dir(self._schema):
            # スキーマのプライベート属性やメソッドはスキップ
            if attr_name.startswith('_') or callable(getattr(self._schema, attr_name)):
                continue
                
            # スキーマから設定定義を取得
            schema_value = getattr(self._schema, attr_name)
            if isinstance(schema_value, dict):
                # 環境変数から値を取得
                value = self._get_setting_value(attr_name, schema_value)
                # 値を保存
                self._values[attr_name] = value
    
    def _get_setting_value(self, name: str, schema: dict) -> Any:
        """
        スキーマに基づいて環境変数から設定値を取得
        
        Args:
            name: 設定名
            schema: 設定のスキーマ情報
            
        Returns:
            Any: 取得した設定値（デフォルト値または環境変数の値）
        """
        # デフォルト値を取得
        default_value = schema.get('default')
        
        # 環境変数名（リストまたは文字列）
        env_vars = schema.get('env_var', [])
        if isinstance(env_vars, str):
            env_vars = [env_vars]
        
        # 環境変数から値を取得
        value = None
        for env_var in env_vars:
            if env_var in os.environ:
                value = os.environ[env_var]
                break
        
        # 値が見つからない場合はデフォルト値を使用
        if value is None:
            # 必須フィールドの場合は警告
            if schema.get('required', False):
                logger.warning(f"必須設定 '{name}' の値が見つかりません。環境変数 {env_vars} を設定してください。")
            return default_value
        
        # 変換関数があれば適用
        if 'converter' in schema:
            try:
                value = schema['converter'](value)
            except Exception as e:
                logger.error(f"設定 '{name}' の値変換中にエラーが発生しました: {e}")
                # 変換エラーの場合はデフォルト値を使用
                return default_value
        
        # バリデーションがあれば実行
        if 'validator' in schema and callable(schema['validator']):
            if not schema['validator'](value):
                logger.warning(f"設定 '{name}' の値 '{value}' が有効ではありません。デフォルト値を使用します。")
                return default_value
                
        return value
    
    def __getattr__(self, name: str) -> Any:
        """
        属性アクセスを _values 辞書に転送
        
        Args:
            name: 設定名
            
        Returns:
            Any: 設定値
            
        Raises:
            AttributeError: 設定が見つからない場合
        """
        if name in self._values:
            return self._values[name]
        raise AttributeError(f"設定 '{name}' が見つかりません")
    
    def print_settings(self):
        """現在の設定値をログに出力"""
        logger.info("===== 現在の設定 =====")
        for name, value in self._values.items():
            # センシティブな情報は一部マスク
            if 'token' in name.lower():
                masked = str(value)[:5] + '...' if value and len(str(value)) > 5 else value
                logger.info(f"{name}: {masked}")
            else:
                logger.info(f"{name}: {value}")
        logger.info("=====================")

# シングルトンインスタンスを作成
BOT_CONFIG = Config()

# 後方互換性のためのエイリアス
DISCORD_BOT_TOKEN = BOT_CONFIG.DISCORD_BOT_TOKEN
DEBUG_MODE = BOT_CONFIG.DEBUG_MODE
LOG_LEVEL = BOT_CONFIG.LOG_LEVEL
THREAD_AUTO_ARCHIVE_DURATION = BOT_CONFIG.THREAD_AUTO_ARCHIVE_DURATION
THREAD_NAME_TEMPLATE = BOT_CONFIG.THREAD_NAME_TEMPLATE
TRIGGER_KEYWORDS = BOT_CONFIG.TRIGGER_KEYWORDS
ENABLED_CHANNEL_IDS = BOT_CONFIG.ENABLED_CHANNEL_IDS
KEEP_ALIVE_ENABLED = BOT_CONFIG.KEEP_ALIVE_ENABLED
KEEP_ALIVE_INTERVAL = BOT_CONFIG.KEEP_ALIVE_INTERVAL
BOT_INTENTS = BOT_CONFIG.BOT_INTENTS

# 必須設定の確認
if not DISCORD_BOT_TOKEN:
    logger.error("DISCORD_BOT_TOKENが設定されていません。Botを起動できません。")