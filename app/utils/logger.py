#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ロギング設定と機能を提供するモジュール - 重複ハンドラ問題を修正
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict

# 設定が遅延インポートされるため、インポート時の config 参照に頼らず、
# 必要に応じて実行時に設定を読み込む
def get_config_values():
    """config から設定値を取得（循環インポートを避けるため遅延インポート）"""
    try:
        from config import LOG_LEVEL, DEBUG_MODE
        return LOG_LEVEL, DEBUG_MODE
    except ImportError:
        return "INFO", False

# ログファイルの保存先
LOG_DIR = "/app/logs"
LOG_FILE = os.path.join(LOG_DIR, "discord_bot.log")

# ログフォーマット
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

# 初期化済みロガーを追跡するグローバル辞書
_initialized_loggers: Dict[str, logging.Logger] = {}

def setup_logger(name: str) -> logging.Logger:
    """
    名前付きロガーをセットアップ（重複初期化を防止）
    
    Args:
        name: ロガー名（通常はモジュール名 __name__）
        
    Returns:
        logging.Logger: セットアップされたロガー
    """
    global _initialized_loggers
    
    # すでに初期化済みの場合は既存のロガーを返す
    if name in _initialized_loggers:
        return _initialized_loggers[name]
    
    # config から設定値を取得
    LOG_LEVEL, DEBUG_MODE = get_config_values()
    
    # ロガーを取得
    logger = logging.getLogger(name)
    
    # ログレベルを設定
    # DEBUG_MODEが有効な場合は強制的にDEBUGレベルに設定
    if DEBUG_MODE:
        log_level = logging.DEBUG
        print(f"デバッグモードが有効です。ロガー {name} のログレベルをDEBUGに設定します。")
    else:
        log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    
    logger.setLevel(log_level)
    
    # 既存のハンドラがあれば削除（安全のため）
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    
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
    
    # 初期化済みとしてマーク
    _initialized_loggers[name] = logger
    
    # 最初のログメッセージ
    logger.info(f"ロガー '{name}' を初期化しました (レベル: {logging.getLevelName(log_level)})")
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    既存のロガーを取得するか、新しいロガーを設定する（別名）
    
    Args:
        name: ロガー名
        
    Returns:
        logging.Logger: 取得または初期化されたロガー
    """
    return setup_logger(name)

# モジュールレベルでのルートロガー設定（他モジュールがlogging直接使用時のフォールバック）
def setup_root_logger():
    """ルートロガーの基本設定（他のモジュールでloggingが直接使用された場合のため）"""
    root_logger = logging.getLogger()
    
    # 既存のハンドラが無い場合のみ設定
    if not root_logger.handlers:
        # 最小限の設定でルートロガーを構成
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

# モジュールロード時にルートロガーを設定
setup_root_logger()