#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot設定を管理するモジュール
"""

import os
from typing import List, Dict, Any, Set

# Discord Bot Token (環境変数から取得)
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# スレッド自動アーカイブ時間 (単位: 分)
THREAD_AUTO_ARCHIVE_DURATION = 10080  # 1週間 = 60分 × 24時間 × 7日 = 10080分

# スレッド作成のトリガーとなる文言のリスト
TRIGGER_KEYWORDS = [
    "募集"
]

# デバッグモード (環境変数から取得、デフォルトはFalse)
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

# ロギングレベル
LOG_LEVEL = "DEBUG" if DEBUG_MODE else "INFO"

# スレッド名テンプレート
THREAD_NAME_TEMPLATE = "{username}の募集"

# 有効なチャンネルIDのリスト (環境変数から取得)
# 複数のチャンネルIDはカンマ区切りで指定する
# 例: "123456789,987654321"
ENABLED_CHANNEL_IDS_STR = os.getenv("ENABLED_CHANNEL_IDS", "")
ENABLED_CHANNEL_IDS: Set[int] = set()

# チャンネルIDの文字列が存在する場合、整数のセットに変換
if ENABLED_CHANNEL_IDS_STR:
    try:
        ENABLED_CHANNEL_IDS = {int(channel_id.strip()) for channel_id in ENABLED_CHANNEL_IDS_STR.split(",")}
    except ValueError:
        print("警告: ENABLED_CHANNEL_IDSの形式が正しくありません。数値のカンマ区切りリストを指定してください。")

# キープアライブの設定
# キープアライブ機能の有効/無効 (環境変数から取得、デフォルトは有効)
KEEP_ALIVE_ENABLED = os.getenv("KEEP_ALIVE_ENABLED", "True").lower() == "true"
# キープアライブの間隔（分）(環境変数から取得、デフォルトは30分)
try:
    KEEP_ALIVE_INTERVAL = int(os.getenv("KEEP_ALIVE_INTERVAL", "30"))
except ValueError:
    print("警告: KEEP_ALIVE_INTERVALの形式が正しくありません。デフォルト値の30分を使用します。")
    KEEP_ALIVE_INTERVAL = 30

# Botの設定
BOT_CONFIG: Dict[str, Any] = {
    "intents": {
        "message_content": True,
        "guilds": True,
        "guild_messages": True,
    }
}