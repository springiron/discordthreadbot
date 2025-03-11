#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ロギング設定と機能を提供するモジュール
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from config import LOG_LEVEL

# ログファイルの保存先
LOG_DIR = "/app/logs"
LOG_FILE = os.path.join(LOG_DIR, "discord_bot.log")

# ログフォーマット
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

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
    log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(log_level)
    
    # コンソールハンドラを追加
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
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
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)
    except Exception as e:
        # ファイルへのログ出力に失敗してもコンソールには出力できるよう続行
        logger.warning(f"ログファイルの設定に失敗しました: {e}")
    
    return logger