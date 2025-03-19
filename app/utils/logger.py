#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ロギング設定と機能を提供するモジュール - デバッグ機能強化
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from config import LOG_LEVEL, DEBUG_MODE

# ログファイルの保存先
LOG_DIR = "/app/logs"
LOG_FILE = os.path.join(LOG_DIR, "discord_bot.log")

# ログフォーマット
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

def setup_logger(name: str) -> logging.Logger:
    """
    名前付きロガーをセットアップ
    
    Args:
        name: ロガー名（通常はモジュール名 __name__）
        
    Returns:
        logging.Logger: セットアップされたロガー
    """
    # ロガーを取得
    logger = logging.getLogger(name)
    
    # すでに設定済みの場合は再利用
    if logger.handlers:
        return logger
    
    # ログレベルを設定
    # DEBUG_MODEが有効な場合は強制的にDEBUGレベルに設定
    if DEBUG_MODE:
        log_level = logging.DEBUG
        print(f"デバッグモードが有効です。ロガー {name} のログレベルをDEBUGに設定します。")
    else:
        log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    
    logger.setLevel(log_level)
    
    # コンソールハンドラを追加
    console_handler = logging.StreamHandler(sys.stdout)
    # デバッグモードの場合、詳細なフォーマットを使用
    log_format = DETAILED_LOG_FORMAT if DEBUG_MODE else LOG_FORMAT
    console_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(console_handler)
    
    # ファイルハンドラを追加（ローテーション付き）
    try:
        # ディレクトリが存在しない場合は作成
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # ファイルハンドラを作成
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
        
        if DEBUG_MODE:
            print(f"ログファイルに出力します: {LOG_FILE}")
    except Exception as e:
        # ファイルへのログ出力に失敗してもコンソールには出力できるよう続行
        logger.warning(f"ログファイルの設定に失敗しました: {e}")
    
    # 最初のログメッセージ
    logger.info(f"ロガー '{name}' を初期化しました (レベル: {logging.getLevelName(log_level)})")
    
    return logger