#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シンプルな設定管理 - .envファイル中心の設計
"""

import os
import logging
from typing import List, Set, Union
from dotenv import load_dotenv

# ロガー設定
logger = logging.getLogger("config")

# .envファイルを読み込み
load_dotenv()

def get_env_bool(key: str, default: bool = False) -> bool:
    """環境変数をboolとして取得"""
    return os.getenv(key, str(default)).lower() in ['true', '1', 'yes', 'on']

def get_env_int(key: str, default: int) -> int:
    """環境変数をintとして取得"""
    try:
        return int(os.getenv(key, default))
    except ValueError:
        logger.warning(f"環境変数 {key} の値が不正です。デフォルト値 {default} を使用します")
        return default

def get_env_list(key: str, default: List[str] = None) -> List[str]:
    """環境変数をリストとして取得（カンマ区切り）"""
    if default is None:
        default = []
    value = os.getenv(key, "")
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]

def get_env_set(key: str, default: Set[int] = None) -> Set[int]:
    """環境変数をintのsetとして取得（カンマ区切り）"""
    if default is None:
        default = set()
    value = os.getenv(key, "")
    if not value:
        return default
    try:
        return {int(item.strip()) for item in value.split(",") if item.strip().isdigit()}
    except ValueError:
        logger.warning(f"環境変数 {key} の値が不正です。デフォルト値を使用します")
        return default

# =============================================================================
# 基本設定（必須項目）
# =============================================================================
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not DISCORD_BOT_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN が設定されていません")

# =============================================================================
# ログ設定
# =============================================================================
DEBUG_MODE = get_env_bool("DEBUG_MODE")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# =============================================================================
# Discord Bot設定
# =============================================================================
# チャンネル・ユーザー設定
ENABLED_CHANNEL_IDS = get_env_set("ENABLED_CHANNEL_IDS")
ADMIN_USER_IDS = get_env_set("ADMIN_USER_IDS")
IGNORED_BOT_IDS = get_env_set("IGNORED_BOT_IDS")

# スレッド設定
TRIGGER_KEYWORDS = get_env_list("TRIGGER_KEYWORDS", ["募集"])
THREAD_AUTO_ARCHIVE_DURATION = get_env_int("THREAD_AUTO_ARCHIVE_DURATION", 60)
THREAD_NAME_TEMPLATE = os.getenv("THREAD_NAME_TEMPLATE", "[✅ 募集中]{username}の募集")
THREAD_MONITORING_DURATION = get_env_int("THREAD_MONITORING_DURATION", 60)

# スレッド締め切り設定
THREAD_CLOSE_KEYWORDS = get_env_list("THREAD_CLOSE_KEYWORDS", 
    ["〆", "締め", "しめ", "〆切", "締切", "しめきり", "closed", "close"])
THREAD_CLOSED_NAME_TEMPLATE = os.getenv("THREAD_CLOSED_NAME_TEMPLATE", "[⛔ 募集終了]{original_name}")

# =============================================================================
# スプレッドシート設定
# =============================================================================
SPREADSHEET_LOGGING_ENABLED = get_env_bool("SPREADSHEET_LOGGING_ENABLED")
SPREADSHEET_CREDENTIALS_FILE = os.getenv("SPREADSHEET_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SPREADSHEET_SHEET_NAME = os.getenv("SPREADSHEET_SHEET_NAME", "スレッドログ")
SPREADSHEET_LOG_QUEUE_SIZE = get_env_int("SPREADSHEET_LOG_QUEUE_SIZE", 100)

# スレッド状態
THREAD_STATUS_CREATION = os.getenv("THREAD_STATUS_CREATION", "募集開始")
THREAD_STATUS_CLOSING = os.getenv("THREAD_STATUS_CLOSING", "募集終了")

# 1日1回制限設定
SPREADSHEET_DAILY_LIMIT_ENABLED = get_env_bool("SPREADSHEET_DAILY_LIMIT_ENABLED", True)
SPREADSHEET_DAILY_RESET_HOUR = get_env_int("SPREADSHEET_DAILY_RESET_HOUR", 6)
SPREADSHEET_TIMEZONE_OFFSET = get_env_int("SPREADSHEET_TIMEZONE_OFFSET", 9)

# =============================================================================
# サーバー設定
# =============================================================================
PORT = get_env_int("PORT", 8080)
KEEP_ALIVE_ENABLED = get_env_bool("KEEP_ALIVE_ENABLED", True)
KEEP_ALIVE_INTERVAL = get_env_int("KEEP_ALIVE_INTERVAL", 30)

# =============================================================================
# Discord Bot Intents
# =============================================================================
BOT_INTENTS = {
    "message_content": True,
    "guilds": True,
    "messages": True,
    "guild_messages": True,
    "guild_reactions": True,
}

BOT_CONFIG = {
    "BOT_INTENTS": BOT_INTENTS
}

# =============================================================================
# 設定検証
# =============================================================================
def validate_config():
    """設定値の検証"""
    errors = []
    
    # 必須チェック
    if not DISCORD_BOT_TOKEN:
        errors.append("DISCORD_BOT_TOKEN が設定されていません")
    
    # 値の範囲チェック
    if THREAD_AUTO_ARCHIVE_DURATION not in [60, 1440, 4320, 10080]:
        errors.append(f"THREAD_AUTO_ARCHIVE_DURATION の値が不正です: {THREAD_AUTO_ARCHIVE_DURATION}")
    
    if not (0 <= SPREADSHEET_DAILY_RESET_HOUR <= 23):
        errors.append(f"SPREADSHEET_DAILY_RESET_HOUR の値が不正です: {SPREADSHEET_DAILY_RESET_HOUR}")
    
    if not (-12 <= SPREADSHEET_TIMEZONE_OFFSET <= 12):
        errors.append(f"SPREADSHEET_TIMEZONE_OFFSET の値が不正です: {SPREADSHEET_TIMEZONE_OFFSET}")
    
    # スプレッドシート設定チェック
    if SPREADSHEET_LOGGING_ENABLED:
        if not SPREADSHEET_ID:
            errors.append("SPREADSHEET_LOGGING_ENABLED=true ですが SPREADSHEET_ID が設定されていません")
        if not os.path.exists(SPREADSHEET_CREDENTIALS_FILE):
            errors.append(f"認証情報ファイルが見つかりません: {SPREADSHEET_CREDENTIALS_FILE}")
    
    if errors:
        for error in errors:
            logger.error(error)
        raise ValueError("設定エラーが発生しました")
    
    logger.info("設定検証が完了しました")

# =============================================================================
# 設定情報の表示
# =============================================================================
def print_config_summary():
    """設定の概要を表示"""
    if DEBUG_MODE:
        logger.info("=== Bot設定情報 ===")
        logger.info(f"デバッグモード: {DEBUG_MODE}")
        logger.info(f"トリガーキーワード: {TRIGGER_KEYWORDS}")
        logger.info(f"有効チャンネル数: {len(ENABLED_CHANNEL_IDS)}")
        logger.info(f"スレッド監視時間: {THREAD_MONITORING_DURATION}分")
        logger.info(f"スプレッドシートログ: {SPREADSHEET_LOGGING_ENABLED}")
        if SPREADSHEET_LOGGING_ENABLED and SPREADSHEET_DAILY_LIMIT_ENABLED:
            tz_name = "JST" if SPREADSHEET_TIMEZONE_OFFSET == 9 else f"UTC{SPREADSHEET_TIMEZONE_OFFSET:+d}"
            logger.info(f"1日1回制限: 有効 ({tz_name} {SPREADSHEET_DAILY_RESET_HOUR}:00リセット)")
        logger.info("==================")

# 初期化時に実行
validate_config()
print_config_summary()