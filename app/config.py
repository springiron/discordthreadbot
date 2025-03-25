#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot設定を一元管理するモジュール
環境変数の読み込みと設定値の検証・変換を担当
Discordコマンドによる動的設定変更機能を追加
"""

import os
import logging
import json
from typing import List, Dict, Any, Set, Optional, Union, Callable
import sys

# 基本的なロギング設定（config.pyが最初に読み込まれる可能性があるため）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("config")

# 設定ファイルのパス
CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "config.json")

# 設定値のスキーマ定義
class ConfigSchema:
    """設定値のスキーマ定義（型情報、デフォルト値、検証ルール、編集可否など）"""
    
    def __init__(self):
        # Bot設定
        self.DISCORD_BOT_TOKEN = {
            "type": str,
            "default": "",
            "env_var": ["DISCORD_BOT_TOKEN", "BOT_TOKEN"],  # 複数の環境変数名をサポート
            "required": True,
            "description": "Discord Bot APIトークン",
            "editable": False  # コマンドで編集不可
        }
        
        # デバッグモード
        self.DEBUG_MODE = {
            "type": bool,
            "default": False,
            "env_var": "DEBUG_MODE",
            "converter": lambda x: str(x).lower() == "true" if isinstance(x, str) else bool(x),
            "description": "デバッグモードの有効/無効",
            "editable": False  # コマンドで編集不可
        }
        
        # ロギングレベル
        self.LOG_LEVEL = {
            "type": str,
            "default": "INFO",
            "env_var": "LOG_LEVEL",
            "validator": lambda x: x in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
            "description": "ロギングレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）",
            "editable": False  # コマンドで編集不可
        }
        
        # スレッド設定
        self.THREAD_AUTO_ARCHIVE_DURATION = {
            "type": int,
            "default": 10080,  # 1週間（分）
            "env_var": "THREAD_AUTO_ARCHIVE_DURATION",
            "description": "スレッド自動アーカイブ時間（分）",
            "options": [60, 1440, 4320, 10080],  # Discordの制限に合わせた選択肢
            "validator": lambda x: int(x) in [60, 1440, 4320, 10080],  # 1時間, 24時間, 3日, 7日
            "editable": True,  # コマンドで編集可能
            "help_text": "スレッドの自動アーカイブ時間を設定します。指定可能な値: 60(1時間), 1440(1日), 4320(3日), 10080(1週間)"
        }
        
        self.THREAD_NAME_TEMPLATE = {
            "type": str,
            "default": "{username}の募集",
            "env_var": "THREAD_NAME_TEMPLATE",
            "description": "スレッド名のテンプレート（{username}は投稿者名に置換）",
            "editable": True,  # コマンドで編集可能
            "help_text": "スレッド名のテンプレートを設定します。{username}は投稿者名に置き換えられます。"
        }
        
        # トリガーキーワード
        self.TRIGGER_KEYWORDS = {
            "type": list,
            "default": ["募集"],
            "env_var": "TRIGGER_KEYWORDS",
            "converter": lambda x: x.split(",") if isinstance(x, str) else x,
            "description": "スレッド作成のトリガーとなるキーワード（カンマ区切り）",
            "editable": True,  # コマンドで編集可能
            "help_text": "スレッド作成のトリガーとなるキーワードを設定します。複数指定する場合はカンマ区切りで入力してください。"
        }
        
        # 有効なチャンネル
        self.ENABLED_CHANNEL_IDS = {
            "type": set,
            "default": set(),
            "env_var": "ENABLED_CHANNEL_IDS",
            "converter": lambda x: {int(channel_id.strip()) for channel_id in x.split(",") if channel_id.strip() and channel_id.strip().isdigit()} if isinstance(x, str) else x,
            "description": "有効なチャンネルIDのリスト（カンマ区切り）",
            "editable": True,  # コマンドで編集可能
            "help_text": "Botが動作するチャンネルIDを設定します。複数指定する場合はカンマ区切りで入力してください。空の場合は全チャンネルで動作します。"
        }
        
        # Bot管理者ID
        self.ADMIN_USER_IDS = {
            "type": set,
            "default": set(),
            "env_var": "ADMIN_USER_IDS",
            "converter": lambda x: {int(user_id.strip()) for user_id in x.split(",") if user_id.strip() and user_id.strip().isdigit()} if isinstance(x, str) else x,
            "description": "Bot管理者のユーザーID（カンマ区切り）",
            "editable": True,  # コマンドで編集可能
            "help_text": "Bot設定を変更できる管理者のユーザーIDを設定します。複数指定する場合はカンマ区切りで入力してください。"
        }
        
        # キープアライブ設定
        self.KEEP_ALIVE_ENABLED = {
            "type": bool,
            "default": True,
            "env_var": "KEEP_ALIVE_ENABLED",
            "converter": lambda x: str(x).lower() == "true" if isinstance(x, str) else bool(x),
            "description": "キープアライブ機能の有効/無効",
            "editable": False  # コマンドで編集不可
        }
        
        self.KEEP_ALIVE_INTERVAL = {
            "type": int,
            "default": 30,
            "env_var": "KEEP_ALIVE_INTERVAL",
            "converter": lambda x: int(x) if isinstance(x, str) and x.isdigit() else 30,
            "description": "キープアライブ間隔（分）",
            "editable": False  # コマンドで編集不可
        }
        
        # HTTPサーバーポート
        self.PORT = {
            "type": int,
            "default": 8080,
            "env_var": "PORT",
            "converter": lambda x: int(x) if isinstance(x, str) and x.isdigit() else 8080,
            "description": "ヘルスチェックサーバーのポート番号",
            "editable": False  # コマンドで編集不可
        }
        
        # Botの意図設定
        self.BOT_INTENTS = {
            "type": dict,
            "default": {
                "message_content": True,
                "guilds": True,
                "messages": True,
                "guild_messages": True,
            },
            "description": "Botの意図（intents）設定",
            "editable": False  # コマンドで編集不可
        }

class ConfigDict(dict):
    """
    Config値へのアクセスを辞書形式で提供するラッパークラス
    後方互換性を維持するために使用
    """
    def __init__(self, config_obj):
        """
        Configオブジェクトから辞書を初期化
        
        Args:
            config_obj: Configオブジェクト
        """
        self._config = config_obj
        self._dict = {}
        
        # Configオブジェクトの属性を辞書に変換
        for attr_name in dir(config_obj):
            if not attr_name.startswith('_') and not callable(getattr(config_obj, attr_name)):
                value = getattr(config_obj, attr_name)
                self._dict[attr_name] = value
                
    def __getitem__(self, key):
        """
        辞書形式のアクセスを提供
        
        Args:
            key: アクセスするキー
            
        Returns:
            設定値
        """
        if key in self._dict:
            return self._dict[key]
        raise KeyError(f"設定 '{key}' が見つかりません")
        
    def __contains__(self, key):
        """
        キーの存在確認
        """
        return key in self._dict

class Config:
    """設定管理クラス - 設定のロード、保存、動的更新機能を提供"""
    
    def __init__(self):
        # スキーマの取得
        self._schema = ConfigSchema()
        
        # 環境変数から読み込んだ値を保持する辞書
        self._values = {}
        
        # 辞書形式アクセス用のプロパティ
        self._dict_interface = None
        
        # .envファイルの読み込み（あれば）
        self._load_env_file()
        
        # 保存された設定ファイルの読み込み（あれば）
        self._load_saved_config()
        
        # 全ての設定値を環境変数から読み込む（保存された設定より優先）
        self._load_all_settings()
        
        # PORTの設定を読み込む
        self.PORT = self._get_setting_value("PORT", self._schema.PORT)
        
        # データディレクトリの作成
        self._ensure_data_dir()
        
    def _ensure_data_dir(self):
        """データディレクトリが存在することを確認"""
        data_dir = os.path.dirname(CONFIG_FILE_PATH)
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir, exist_ok=True)
                logger.info(f"データディレクトリを作成しました: {data_dir}")
            except Exception as e:
                logger.error(f"データディレクトリの作成に失敗しました: {e}")
        
    def _load_saved_config(self):
        """JSONファイルから保存された設定を読み込む"""
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                
                # 読み込んだ設定を_values辞書に適用
                for key, value in saved_config.items():
                    # スキーマに存在する設定のみ適用
                    if hasattr(self._schema, key):
                        schema_def = getattr(self._schema, key)
                        
                        # 型変換が必要な場合は適用
                        if 'converter' in schema_def and callable(schema_def['converter']):
                            try:
                                value = schema_def['converter'](value)
                            except Exception as e:
                                logger.error(f"設定 '{key}' の値変換中にエラーが発生しました: {e}")
                                continue
                        
                        # バリデーションがある場合は実行
                        if 'validator' in schema_def and callable(schema_def['validator']):
                            if not schema_def['validator'](value):
                                logger.warning(f"設定 '{key}' の値 '{value}' が有効ではありません。")
                                continue
                                
                        # 値を設定
                        self._values[key] = value
                        
                logger.info(f"設定ファイルから設定を読み込みました: {CONFIG_FILE_PATH}")
            except Exception as e:
                logger.error(f"設定ファイルの読み込み中にエラーが発生しました: {e}")
        else:
            logger.info(f"設定ファイルが見つかりません。環境変数およびデフォルト値を使用します: {CONFIG_FILE_PATH}")
    
    def save_config(self):
        """現在の設定をJSONファイルに保存"""
        try:
            # 保存用の辞書を作成
            save_dict = {}
            
            # スキーマに定義されている設定のみ保存
            for attr_name in dir(self._schema):
                if attr_name.startswith('_') or callable(getattr(self._schema, attr_name)):
                    continue
                    
                # 値が存在する場合のみ保存
                if attr_name in self._values:
                    value = self._values[attr_name]
                    
                    # setをリストに変換（JSON対応）
                    if isinstance(value, set):
                        value = list(value)
                        
                    save_dict[attr_name] = value
            
            # JSONファイルに保存
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(save_dict, f, ensure_ascii=False, indent=2)
                
            logger.info(f"設定を保存しました: {CONFIG_FILE_PATH}")
            return True
        except Exception as e:
            logger.error(f"設定の保存中にエラーが発生しました: {e}")
            return False
            
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
            if (env_var in os.environ):
                value = os.environ[env_var]
                break
        
        # 値が見つからない場合は、すでに_valuesに設定されている値があればそれを使用
        # それもなければデフォルト値を使用
        if value is None:
            if name in self._values:
                return self._values[name]
                
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
    
    def update_setting(self, name: str, value: Any) -> bool:
        """
        設定値を動的に更新
        
        Args:
            name: 設定名
            value: 新しい設定値
            
        Returns:
            bool: 更新に成功した場合はTrue
        """
        # スキーマに存在するか確認
        if not hasattr(self._schema, name):
            logger.error(f"設定 '{name}' はスキーマに存在しません")
            return False
            
        # スキーマ定義を取得
        schema_def = getattr(self._schema, name)
        
        # 編集可能か確認
        if not schema_def.get('editable', False):
            logger.error(f"設定 '{name}' は編集不可です")
            return False
            
        # 型変換
        try:
            if 'converter' in schema_def and callable(schema_def['converter']):
                value = schema_def['converter'](value)
            elif schema_def['type'] == bool and isinstance(value, str):
                value = value.lower() in ('true', 'yes', '1', 'on')
            elif schema_def['type'] == int and isinstance(value, str):
                value = int(value)
            elif schema_def['type'] == float and isinstance(value, str):
                value = float(value)
            elif schema_def['type'] == list and isinstance(value, str):
                value = [item.strip() for item in value.split(',') if item.strip()]
            elif schema_def['type'] == set and isinstance(value, str):
                value = {item.strip() for item in value.split(',') if item.strip()}
        except Exception as e:
            logger.error(f"設定 '{name}' の値変換中にエラーが発生しました: {e}")
            return False
            
        # バリデーション
        if 'validator' in schema_def and callable(schema_def['validator']):
            if not schema_def['validator'](value):
                logger.error(f"設定 '{name}' の値 '{value}' は有効ではありません")
                return False
                
        # 値を更新
        self._values[name] = value
        logger.info(f"設定 '{name}' を '{value}' に更新しました")
        
        # 設定を保存
        self.save_config()
        
        return True
    
    def get_editable_settings(self) -> Dict[str, Dict]:
        """
        コマンドで編集可能な設定のリストを取得
        
        Returns:
            Dict[str, Dict]: 編集可能な設定の辞書
        """
        editable_settings = {}
        
        for attr_name in dir(self._schema):
            if attr_name.startswith('_') or callable(getattr(self._schema, attr_name)):
                continue
                
            schema_def = getattr(self._schema, attr_name)
            if schema_def.get('editable', False):
                # 現在の値を取得
                current_value = self._values.get(attr_name, schema_def.get('default'))
                
                # 設定情報を辞書に追加
                editable_settings[attr_name] = {
                    'description': schema_def.get('description', ''),
                    'help_text': schema_def.get('help_text', ''),
                    'type': schema_def['type'].__name__,
                    'current_value': current_value,
                    'options': schema_def.get('options', [])
                }
                
        return editable_settings
    
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
    
    def __getitem__(self, key: str) -> Any:
        """
        辞書形式でのアクセスをサポート
        
        Args:
            key: 設定名
            
        Returns:
            Any: 設定値
            
        Raises:
            KeyError: 設定が見つからない場合
        """
        if key in self._values:
            return self._values[key]
        raise KeyError(f"設定 '{key}' が見つかりません")
    
    def get_dict(self):
        """
        設定を辞書として取得
        
        Returns:
            Dict: 設定値の辞書
        """
        if self._dict_interface is None:
            self._dict_interface = ConfigDict(self)
        return self._dict_interface
        
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
config_instance = Config()

# 後方互換性のために辞書形式でもアクセスできるようにする
BOT_CONFIG = {
    "BOT_INTENTS": {
        "message_content": True,
        "guilds": True,
        "messages": True,
        "guild_messages": True
    },
    "intents": config_instance.BOT_INTENTS,
    # 他の必要な設定も追加
}

# 後方互換性のためのエイリアス
DISCORD_BOT_TOKEN = config_instance.DISCORD_BOT_TOKEN
DEBUG_MODE = config_instance.DEBUG_MODE
LOG_LEVEL = config_instance.LOG_LEVEL
THREAD_AUTO_ARCHIVE_DURATION = config_instance.THREAD_AUTO_ARCHIVE_DURATION
THREAD_NAME_TEMPLATE = config_instance.THREAD_NAME_TEMPLATE
TRIGGER_KEYWORDS = config_instance.TRIGGER_KEYWORDS
ENABLED_CHANNEL_IDS = config_instance.ENABLED_CHANNEL_IDS
KEEP_ALIVE_ENABLED = config_instance.KEEP_ALIVE_ENABLED
KEEP_ALIVE_INTERVAL = config_instance.KEEP_ALIVE_INTERVAL
PORT = config_instance.PORT
BOT_INTENTS = config_instance.BOT_INTENTS

# 管理者IDの取得（なければ空のセット）
try:
    ADMIN_USER_IDS = config_instance.ADMIN_USER_IDS
except AttributeError:
    ADMIN_USER_IDS = set()

# 必須設定の確認
if not DISCORD_BOT_TOKEN:
    logger.error("DISCORD_BOT_TOKENが設定されていません。Botを起動できません。")

# 設定更新関数（他のモジュールから呼び出し用）
def update_setting(name: str, value: Any) -> bool:
    """
    設定値を更新する関数
    
    Args:
        name: 設定名
        value: 新しい値
        
    Returns:
        bool: 更新成功時はTrue
    """
    return config_instance.update_setting(name, value)

# 編集可能な設定取得関数
def get_editable_settings() -> Dict[str, Dict]:
    """
    編集可能な設定一覧を取得
    
    Returns:
        Dict: 編集可能な設定情報
    """
    return config_instance.get_editable_settings()