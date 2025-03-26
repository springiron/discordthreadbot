#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot設定を管理するモジュール
"""

import os
import logging
import json
from typing import List, Dict, Any, Set, Optional, Union
import sys

# 基本的なロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("config")

# 設定ファイルのパス
CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "config.json")

# 設定値の定義
DEFAULT_CONFIG = {
    "DISCORD_BOT_TOKEN": "",  # 必須、環境変数から取得
    "DEBUG_MODE": False,
    "LOG_LEVEL": "INFO",
    "THREAD_AUTO_ARCHIVE_DURATION": 10080,  # 1週間（分）
    "THREAD_NAME_TEMPLATE": "{username}の募集",
    "TRIGGER_KEYWORDS": ["募集"],
    "ENABLED_CHANNEL_IDS": set(),
    "ADMIN_USER_IDS": set(),
    "BOT_INTENTS": {
        "message_content": True,
        "guilds": True,
        "messages": True,
        "guild_messages": True,
    }
}

# 編集可能な設定と説明
EDITABLE_SETTINGS = {
    "TRIGGER_KEYWORDS": {
        "description": "スレッド作成のトリガーとなるキーワード（カンマ区切り）",
        "type": "list",
        "options": [],
        "help_text": "スレッド作成のトリガーとなるキーワードを設定します。複数指定する場合はカンマ区切りで入力してください。"
    },
    "ENABLED_CHANNEL_IDS": {
        "description": "有効なチャンネルIDのリスト（カンマ区切り）",
        "type": "set",
        "options": [],
        "help_text": "Botが動作するチャンネルIDを設定します。複数指定する場合はカンマ区切りで入力してください。空の場合は全チャンネルで動作します。"
    },
    "THREAD_AUTO_ARCHIVE_DURATION": {
        "description": "スレッド自動アーカイブ時間（分）",
        "type": "int",
        "options": [60, 1440, 4320, 10080],  # 1時間, 24時間, 3日, 7日
        "help_text": "スレッドの自動アーカイブ時間を設定します。指定可能な値: 60(1時間), 1440(1日), 4320(3日), 10080(1週間)"
    },
    "THREAD_NAME_TEMPLATE": {
        "description": "スレッド名のテンプレート（{username}は投稿者名に置換）",
        "type": "str",
        "options": [],
        "help_text": "スレッド名のテンプレートを設定します。{username}は投稿者名に置き換えられます。"
    },
    "ADMIN_USER_IDS": {
        "description": "Bot管理者のユーザーID（カンマ区切り）",
        "type": "set",
        "options": [],
        "help_text": "Bot設定を変更できる管理者のユーザーIDを設定します。複数指定する場合はカンマ区切りで入力してください。"
    }
}

# 設定値を保持する辞書
config_values = {}

def load_config():
    """設定を読み込む"""
    global config_values
    
    # デフォルト値でconfig_valuesを初期化
    config_values = DEFAULT_CONFIG.copy()
    
    # .envファイルの読み込み
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info(".envファイルから環境変数を読み込みました")
    except ImportError:
        pass
    
    # 設定ファイルがあれば読み込む
    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                
            # 読み込んだ設定をconfig_valuesに適用
            for key, value in saved_config.items():
                if key in config_values:
                    # setはJSONで直接表現できないためリストから変換
                    if key in ["ENABLED_CHANNEL_IDS", "ADMIN_USER_IDS"] and isinstance(value, list):
                        config_values[key] = set(value)
                    else:
                        config_values[key] = value
            
            logger.info(f"設定ファイルから設定を読み込みました: {CONFIG_FILE_PATH}")
        except Exception as e:
            logger.error(f"設定ファイルの読み込み中にエラーが発生しました: {e}")
    
    # 環境変数から設定を上書き
    env_overrides = {
        "DISCORD_BOT_TOKEN": os.environ.get("DISCORD_BOT_TOKEN") or os.environ.get("BOT_TOKEN"),
        "DEBUG_MODE": os.environ.get("DEBUG_MODE", "").lower() == "true",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL"),
        "THREAD_AUTO_ARCHIVE_DURATION": os.environ.get("THREAD_AUTO_ARCHIVE_DURATION"),
        "THREAD_NAME_TEMPLATE": os.environ.get("THREAD_NAME_TEMPLATE"),
        "TRIGGER_KEYWORDS": os.environ.get("TRIGGER_KEYWORDS"),
        "ENABLED_CHANNEL_IDS": os.environ.get("ENABLED_CHANNEL_IDS"),
        "ADMIN_USER_IDS": os.environ.get("ADMIN_USER_IDS")
    }
    
    # 環境変数の値が存在する場合のみ上書き
    for key, value in env_overrides.items():
        if value is not None:
            if key == "TRIGGER_KEYWORDS" and isinstance(value, str):
                config_values[key] = [kw.strip() for kw in value.split(",") if kw.strip()]
            elif key in ["ENABLED_CHANNEL_IDS", "ADMIN_USER_IDS"] and isinstance(value, str):
                try:
                    # カンマ区切りの場合とカンマ区切りでない場合を処理
                    if "," in value:
                        config_values[key] = {int(x.strip()) for x in value.split(",") if x.strip() and x.strip().isdigit()}
                    else:
                        # 単一の値の場合
                        value = value.strip()
                        if value.isdigit():
                            config_values[key] = {int(value)}
                except ValueError:
                    logger.error(f"環境変数 {key} の値が不正です: {value}")
            elif key == "THREAD_AUTO_ARCHIVE_DURATION" and isinstance(value, str):
                try:
                    config_values[key] = int(value)
                except ValueError:
                    logger.error(f"環境変数 {key} の値が不正です: {value}")
            else:
                config_values[key] = value
    
    # 環境変数から読み込んだ設定値をconfig.jsonに保存
    # これにより.envの設定値が保持される
    save_config()
    
    # DISCORD_BOT_TOKENが設定されていない場合は警告
    if not config_values["DISCORD_BOT_TOKEN"]:
        logger.warning("DISCORD_BOT_TOKENが設定されていません。Botを起動できません。")
    
    # データディレクトリの作成
    ensure_data_dir()

def ensure_data_dir():
    """データディレクトリが存在することを確認"""
    data_dir = os.path.dirname(CONFIG_FILE_PATH)
    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir, exist_ok=True)
            logger.info(f"データディレクトリを作成しました: {data_dir}")
        except Exception as e:
            logger.error(f"データディレクトリの作成に失敗しました: {e}")

def save_config():
    """現在の設定をJSONファイルに保存"""
    try:
        # 保存用の辞書を作成
        save_dict = {}
        
        for key, value in config_values.items():
            # setはJSONに直接保存できないためリストに変換
            if isinstance(value, set):
                save_dict[key] = list(value)
            else:
                save_dict[key] = value
        
        # JSONファイルに保存
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(save_dict, f, ensure_ascii=False, indent=2)
            
        logger.info(f"設定を保存しました: {CONFIG_FILE_PATH}")
        return True
    except Exception as e:
        logger.error(f"設定の保存中にエラーが発生しました: {e}")
        return False

def update_setting(name, value):
    """
    設定値を更新
    
    Args:
        name: 設定名
        value: 新しい値
        
    Returns:
        bool: 更新成功時はTrue
    """
    # 編集可能な設定か確認
    if name not in EDITABLE_SETTINGS:
        logger.error(f"設定 {name} は編集不可能または存在しません")
        return False
    
    # 設定の型を取得して変換
    setting_type = EDITABLE_SETTINGS[name]["type"]
    try:
        if setting_type == "list" and isinstance(value, str):
            # カンマで区切られた文字列をリストに変換
            if "," in value:
                value = [item.strip() for item in value.split(",") if item.strip()]
            else:
                # カンマがない場合は単一の値としてリストに
                value = [value.strip()] if value.strip() else []
            logger.info(f"キーワード変換結果: {value}")
        elif setting_type == "set" and isinstance(value, str):
            # カンマで区切られた文字列をsetに変換（数値のみ）
            if "," in value:
                value = {int(item.strip()) for item in value.split(",") if item.strip() and item.strip().isdigit()}
            else:
                # 単一の値の場合
                value = value.strip()
                if value.isdigit():
                    value = {int(value)}
                else:
                    logger.error(f"設定 {name} の値が数値ではありません: {value}")
                    return False
            logger.info(f"ID変換結果: {value}")
        elif setting_type == "int" and isinstance(value, str):
            value = int(value)
            # THREAD_AUTO_ARCHIVE_DURATIONは特定の値のみ許可
            if name == "THREAD_AUTO_ARCHIVE_DURATION" and value not in [60, 1440, 4320, 10080]:
                logger.error(f"THREAD_AUTO_ARCHIVE_DURATIONの値が不正です: {value}")
                return False
    except ValueError:
        logger.error(f"設定 {name} の値変換に失敗しました: {value}")
        return False
    
    # 値を更新
    config_values[name] = value
    logger.info(f"設定 {name} を更新しました: {value}")
    
    # 設定を保存
    save_config()
    
    return True


def get_editable_settings():
    """
    編集可能な設定を取得
    
    Returns:
        dict: 編集可能な設定とその情報
    """
    result = {}
    
    for name, info in EDITABLE_SETTINGS.items():
        result[name] = info.copy()
        result[name]["current_value"] = config_values.get(name)
    
    return result

# 初期化
load_config()

# グローバル変数として設定値をエクスポート
DISCORD_BOT_TOKEN = config_values["DISCORD_BOT_TOKEN"]
DEBUG_MODE = config_values["DEBUG_MODE"]
LOG_LEVEL = config_values["LOG_LEVEL"]
THREAD_AUTO_ARCHIVE_DURATION = config_values["THREAD_AUTO_ARCHIVE_DURATION"]
THREAD_NAME_TEMPLATE = config_values["THREAD_NAME_TEMPLATE"]
TRIGGER_KEYWORDS = config_values["TRIGGER_KEYWORDS"]
ENABLED_CHANNEL_IDS = config_values["ENABLED_CHANNEL_IDS"]
ADMIN_USER_IDS = config_values["ADMIN_USER_IDS"]
BOT_INTENTS = config_values["BOT_INTENTS"]

# Bot設定の辞書形式
BOT_CONFIG = {
    "BOT_INTENTS": BOT_INTENTS
}