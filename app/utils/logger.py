#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ロギング設定と機能を提供するモジュール - 重複ハンドラ問題を修正
Unicode絵文字処理問題を修正
"""

import logging
import os
import sys
import re
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

# Unicode絵文字を処理するための正規表現パターン
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # 絵文字
    "\U0001F300-\U0001F5FF"  # シンボル
    "\U0001F680-\U0001F6FF"  # 交通機関や地図
    "\U0001F700-\U0001F77F"  # 追加絵文字
    "\U0001F780-\U0001F7FF"  # 追加絵文字
    "\U0001F800-\U0001F8FF"  # 追加絵文字
    "\U0001F900-\U0001F9FF"  # 追加絵文字
    "\U0001FA00-\U0001FA6F"  # 追加絵文字
    "\U0001FA70-\U0001FAFF"  # 追加絵文字
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251" 
    "\u2600-\u26FF"          # ミスケラニアスシンボル - ⛔や✅を含む
    "]+", 
    flags=re.UNICODE
)

class SafeUnicodeStreamHandler(logging.StreamHandler):
    """
    Unicodeエンコーディングエラーを安全に処理するStreamHandler
    """
    def __init__(self, stream=None):
        super().__init__(stream)
        self.encoding = getattr(stream, 'encoding', sys.getdefaultencoding()) or 'utf-8'
        
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            
            # Windowsでcp932を使用している場合は特殊処理
            if 'cp932' in self.encoding.lower():
                # 絵文字と特殊文字を置換
                msg = EMOJI_PATTERN.sub('□', msg)
                
                # さらに、エンコードできない可能性のある文字を安全に処理
                try:
                    # エンコードできるか試してみる
                    msg.encode(self.encoding, errors='replace')
                except UnicodeEncodeError:
                    # 完全に失敗した場合は、バックアップとしてASCIIに変換
                    msg = msg.encode(self.encoding, errors='replace').decode(self.encoding)
            
            # ストリームにメッセージを書き込む
            stream.write(msg + self.terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

class SafeFormatter(logging.Formatter):
    """安全なフォーマッタ - Unicodeエラーを処理"""
    def format(self, record):
        try:
            message = super().format(record)
            return message
        except UnicodeEncodeError:
            # エンコードエラーが発生した場合は、文字を置換
            try:
                # エンコードエラーの場合、置換文字を使用
                encoding = getattr(sys.stdout, 'encoding', sys.getdefaultencoding()) or 'utf-8'
                return message.encode(encoding, errors='replace').decode(encoding)
            except:
                # 最終手段として、純粋なASCIIに変換
                return repr(message)

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
    
    # コンソールハンドラを追加（改良版）
    console_handler = SafeUnicodeStreamHandler(sys.stdout)

    # デバッグモードの場合、詳細なフォーマットを使用
    log_format = DETAILED_LOG_FORMAT if DEBUG_MODE else LOG_FORMAT
    console_handler.setFormatter(SafeFormatter(log_format))
    logger.addHandler(console_handler)
    
    # ファイルハンドラを追加（ローテーション付き）
    try:
        # ディレクトリが存在しない場合は作成
        os.makedirs(LOG_DIR, exist_ok=True)
        
        # ファイルハンドラを作成
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding='utf-8'  # 明示的にUTF-8を指定
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
        # 最小限の設定でルートロガーを構成 - 安全なハンドラを使用
        handler = SafeUnicodeStreamHandler(sys.stdout)
        handler.setFormatter(SafeFormatter(LOG_FORMAT))
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

# モジュールロード時にルートロガーを設定
setup_root_logger()