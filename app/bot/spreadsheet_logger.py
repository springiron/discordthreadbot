#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スプレッドシートログ記録モジュール - 非同期処理対応版
(イベントループ問題修正版)
"""

import asyncio
import discord
from typing import Optional, Dict
import concurrent.futures
import threading
import queue
import time
from datetime import datetime

from config import (
    SPREADSHEET_LOGGING_ENABLED, SPREADSHEET_CREDENTIALS_FILE,
    SPREADSHEET_ID, SPREADSHEET_SHEET_NAME, SPREADSHEET_FIXED_VALUE
)
from utils.spreadsheet_utils import AsyncSpreadsheetClient
from utils.logger import setup_logger

logger = setup_logger(__name__)

# スプレッドシートクライアントのシングルトンインスタンス
_spreadsheet_client = None
_client_lock = threading.Lock()

# バックグラウンド処理用のキュー
# 設定値からキューサイズを取得、または100をデフォルト値として使用
queue_size = 100
try:
    from config import SPREADSHEET_LOG_QUEUE_SIZE
    if isinstance(SPREADSHEET_LOG_QUEUE_SIZE, int) and SPREADSHEET_LOG_QUEUE_SIZE > 0:
        queue_size = SPREADSHEET_LOG_QUEUE_SIZE
except (ImportError, AttributeError):
    pass

_log_queue = queue.Queue(maxsize=queue_size)
_worker_thread = None
_stop_worker = threading.Event()

# ログ記録状態管理（スレッドIDをキーとするステータス追跡）
_logging_status: Dict[int, Dict] = {}

def get_spreadsheet_client() -> Optional[AsyncSpreadsheetClient]:
    """
    スプレッドシートクライアントのシングルトンインスタンスを取得
    
    Returns:
        Optional[AsyncSpreadsheetClient]: スプレッドシートクライアント、無効な場合はNone
    """
    global _spreadsheet_client
    
    # ログ記録が無効な場合はNoneを返す
    if not SPREADSHEET_LOGGING_ENABLED:
        return None
    
    # IDやファイルパスが設定されていない場合もNoneを返す
    if not SPREADSHEET_ID or not SPREADSHEET_CREDENTIALS_FILE:
        logger.warning("スプレッドシートのIDまたは認証情報ファイルが設定されていません")
        return None
    
    # スレッドセーフな初期化
    with _client_lock:
        # インスタンスがまだ作成されていない場合は新規作成
        if _spreadsheet_client is None:
            _spreadsheet_client = AsyncSpreadsheetClient(
                credentials_file=SPREADSHEET_CREDENTIALS_FILE,
                spreadsheet_id=SPREADSHEET_ID,
                sheet_name=SPREADSHEET_SHEET_NAME
            )
            
            # 初期接続を試みる（非同期操作を同期的に実行）
            try:
                # 新しいイベントループを作成して接続を実行
                connection_loop = asyncio.new_event_loop()
                try:
                    connection_success = connection_loop.run_until_complete(_spreadsheet_client.connect())
                finally:
                    connection_loop.close()
                
                if not connection_success:
                    logger.error("スプレッドシートへの初期接続に失敗しました")
                    _spreadsheet_client = None
                    
            except Exception as e:
                logger.error(f"スプレッドシートクライアント初期化エラー: {e}")
                _spreadsheet_client = None
    
    return _spreadsheet_client

def _start_worker_thread():
    """バックグラウンドワーカースレッドを開始"""
    global _worker_thread, _stop_worker
    
    if _worker_thread is not None and _worker_thread.is_alive():
        return  # すでに実行中
    
    _stop_worker.clear()
    _worker_thread = threading.Thread(
        target=_log_worker,
        daemon=True,
        name="spreadsheet_logger_worker"
    )
    _worker_thread.start()
    logger.info("スプレッドシートログ記録ワーカースレッドを開始しました")

def _log_worker():
    """キューからログエントリを処理するワーカー関数"""
    logger.info("スプレッドシートログ記録ワーカーを開始しました")
    
    # ワーカー専用のイベントループを作成
    worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(worker_loop)
    
    while not _stop_worker.is_set():
        try:
            # キューからログエントリを取得（タイムアウト付き）
            try:
                log_entry = _log_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            # 終了シグナルを検出
            if log_entry is None:
                break
                
            # ログエントリを処理
            thread_id = log_entry.get("thread_id")
            username = log_entry.get("username")
            fixed_value = log_entry.get("fixed_value")
            status = log_entry.get("status", "募集作成")
            
            # クライアントを取得
            client = get_spreadsheet_client()
            if client is None:
                logger.error(f"スプレッドシートクライアントが利用できません: {log_entry}")
                _log_queue.task_done()
                continue
            
            # ワーカー専用ループで非同期関数を実行
            try:
                # スプレッドシートにログを記録
                result = worker_loop.run_until_complete(
                    client.add_thread_log(
                        thread_id=str(thread_id),
                        username=username,
                        fixed_value=fixed_value,
                        status=status
                    )
                )
                
                # 結果を保存
                with _client_lock:
                    _logging_status[thread_id] = {
                        "status": "success" if result else "failed",
                        "timestamp": datetime.now().isoformat(),
                        "username": username,
                        "log_type": status
                    }
                
                logger.info(f"スレッドログを記録しました: ID={thread_id}, ユーザー={username}, 状態={status}, 結果={result}")
                
            except Exception as e:
                logger.error(f"ログ記録処理エラー: {e}")
                # 状態を保存
                with _client_lock:
                    _logging_status[thread_id] = {
                        "status": "error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                        "username": username,
                        "log_type": status
                    }
            finally:
                _log_queue.task_done()
                
        except Exception as e:
            logger.error(f"ワーカースレッドエラー: {e}")
            # エラーが発生しても継続
            time.sleep(1)
    
    # ループを閉じてリソースを解放
    worker_loop.close()
    logger.info("スプレッドシートログ記録ワーカーを終了しました")

def stop_worker():
    """ワーカースレッドを停止"""
    global _stop_worker
    
    logger.info("スプレッドシートログ記録ワーカーの停止を要求しました")
    _stop_worker.set()
    
    # 終了シグナルをキューに送信
    try:
        _log_queue.put(None, block=False)
    except queue.Full:
        pass
    
    # ワーカースレッドが存在し、実行中なら終了を待機
    if _worker_thread is not None and _worker_thread.is_alive():
        _worker_thread.join(timeout=5.0)
        logger.info("スプレッドシートログ記録ワーカーが終了しました")

def queue_thread_log(thread_id: int, username: str, status: str = "募集作成") -> bool:
    """
    スレッドログをキューに追加（非ブロッキング）
    
    Args:
        thread_id: スレッドID
        username: ユーザー名
        status: 状態（作成/締め切りなど）
        
    Returns:
        bool: キューへの追加成功時はTrue
    """
    # ログ記録が無効な場合は何もせずにTrueを返す
    if not SPREADSHEET_LOGGING_ENABLED:
        return True
    
    # ワーカースレッドが実行中でなければ開始
    if _worker_thread is None or not _worker_thread.is_alive():
        _start_worker_thread()
    
    # ログエントリを作成
    log_entry = {
        "thread_id": thread_id,
        "username": username,
        "fixed_value": SPREADSHEET_FIXED_VALUE,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }
    
    # キューに追加（非ブロッキング）
    try:
        _log_queue.put(log_entry, block=False)
        logger.debug(f"スレッドログをキューに追加しました: ID={thread_id}, ユーザー={username}, 状態={status}")
        return True
    except queue.Full:
        logger.warning(f"ログキューがいっぱいです。ログを破棄します: ID={thread_id}, ユーザー={username}")
        return False

def log_thread_creation(thread_id: int, username: str) -> bool:
    """
    スレッド作成をログ記録キューに追加
    
    Args:
        thread_id: スレッドID
        username: ユーザー名
        
    Returns:
        bool: キューへの追加成功時はTrue
    """
    return queue_thread_log(thread_id, username, "募集作成")

def log_thread_close(thread_id: int, username: str) -> bool:
    """
    スレッド締め切りをログ記録キューに追加
    
    Args:
        thread_id: スレッドID
        username: ユーザー名
        
    Returns:
        bool: キューへの追加成功時はTrue
    """
    return queue_thread_log(thread_id, username, "締め切り")

def get_log_status(thread_id: int) -> Optional[Dict]:
    """
    特定のスレッドのログ記録状態を取得
    
    Args:
        thread_id: スレッドID
        
    Returns:
        Optional[Dict]: ログ記録状態の辞書、存在しない場合はNone
    """
    with _client_lock:
        return _logging_status.get(thread_id)

def cleanup():
    """終了時のクリーンアップ処理"""
    stop_worker()
    logger.info("スプレッドシートログ記録モジュールをクリーンアップしました")

# モジュールロード時にワーカースレッドを開始
if SPREADSHEET_LOGGING_ENABLED:
    _start_worker_thread()