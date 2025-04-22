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
    SPREADSHEET_ID, SPREADSHEET_SHEET_NAME, SPREADSHEET_LOG_QUEUE_SIZE,
    THREAD_STATUS_CREATION, THREAD_STATUS_CLOSING
)
from utils.spreadsheet_utils import AsyncSpreadsheetClient
from utils.logger import setup_logger

logger = setup_logger(__name__)

# スプレッドシートクライアントのシングルトンインスタンス
_spreadsheet_client = None
_client_lock = threading.Lock()

# バックグラウンド処理用のキュー
# 設定値からキューサイズを取得
queue_size = SPREADSHEET_LOG_QUEUE_SIZE if isinstance(SPREADSHEET_LOG_QUEUE_SIZE, int) and SPREADSHEET_LOG_QUEUE_SIZE > 0 else 100

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
    
    # 初期化
    worker_loop = None
    retry_count = 0
    max_retries = 3
    
    while not _stop_worker.is_set():
        try:
            # イベントループ確認・作成
            if worker_loop is None or worker_loop.is_closed():
                # 以前のループが閉じられていたら新しいループを作成
                if worker_loop is not None:
                    logger.info("イベントループが閉じられているため、新しいループを作成します")
                
                worker_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(worker_loop)
                logger.debug("ワーカー用の新しいイベントループを作成しました")
            
            # キューからログエントリを取得（タイムアウト付き）
            try:
                log_entry = _log_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            # 終了シグナルを検出
            if log_entry is None:
                break
                
            # ログエントリを処理
            user_id = log_entry.get("user_id")
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
                retry_count = 0
                max_backoff_time = 5  # 最大バックオフ時間（秒）
                
                while retry_count <= max_retries:
                    try:
                        # イベントループ状態を再確認
                        if worker_loop.is_closed():
                            logger.warning("実行直前にイベントループが閉じられました。再作成します")
                            worker_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(worker_loop)
                        
                        # 非同期処理を実行
                        result = worker_loop.run_until_complete(
                            client.add_thread_log(
                                user_id=str(user_id),
                                username=username,
                                fixed_value=fixed_value,
                                status=status
                            )
                        )
                        
                        # 成功したらループを抜ける
                        break
                        
                    except RuntimeError as e:
                        if "Event loop is closed" in str(e):
                            # ループが閉じられていたら新しいループを作成
                            retry_count += 1
                            logger.warning(f"イベントループエラーが発生しました (再試行 {retry_count}/{max_retries}): {e}")
                            
                            # 古いループを閉じる（まだ閉じられていない場合）
                            try:
                                if not worker_loop.is_closed():
                                    worker_loop.close()
                            except Exception:
                                pass
                            
                            # 新しいループを作成
                            worker_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(worker_loop)
                            
                            # バックオフ待機（指数バックオフ）
                            backoff_time = min(max_backoff_time, (2 ** retry_count) / 2)
                            logger.info(f"再試行前に {backoff_time:.1f}秒待機します...")
                            time.sleep(backoff_time)
                        else:
                            # 他のエラーは上位レベルで処理
                            raise
                    
                    except Exception as e:
                        retry_count += 1
                        logger.error(f"ログ記録処理エラー (再試行 {retry_count}/{max_retries}): {e}")
                        
                        if retry_count <= max_retries:
                            # バックオフ待機
                            backoff_time = min(max_backoff_time, (2 ** retry_count) / 2)
                            logger.info(f"再試行前に {backoff_time:.1f}秒待機します...")
                            time.sleep(backoff_time)
                        else:
                            # 最大再試行回数を超えた
                            logger.error(f"最大再試行回数に達しました: {e}")
                            break
                
                # 最大再試行回数を超えても失敗した場合
                if retry_count > max_retries:
                    result = False
                
                # 結果を保存
                with _client_lock:
                    _logging_status[user_id] = {
                        "status": "success" if result else "failed",
                        "timestamp": datetime.now().isoformat(),
                        "username": username,
                        "log_type": status,
                        "retries": retry_count
                    }
                
                logger.info(f"スレッドログを記録しました: ID={user_id}, ユーザー={username}, 状態={status}, 結果={result}")
                
            except Exception as e:
                logger.error(f"ログ記録処理エラー: {e}")
                # 状態を保存
                with _client_lock:
                    _logging_status[user_id] = {
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
    if worker_loop is not None and not worker_loop.is_closed():
        try:
            worker_loop.close()
        except Exception as e:
            logger.error(f"イベントループ終了エラー: {e}")
    
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

def queue_thread_log(user_id: int, username: str, status: str = THREAD_STATUS_CREATION) -> bool:
    """
    スレッドログをキューに追加（非ブロッキング）
    
    Args:
        user_id: ユーザーID
        username: ユーザー名
        status: 状態（募集開始/募集終了など）
        
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
        "user_id": user_id,
        "username": username,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }
    
    # キューに追加（非ブロッキング）
    try:
        _log_queue.put(log_entry, block=False)
        logger.debug(f"スレッドログをキューに追加しました: ID={user_id}, ユーザー={username}, 状態={status}")
        return True
    except queue.Full:
        logger.warning(f"ログキューがいっぱいです。ログを破棄します: ID={user_id}, ユーザー={username}")
        return False

def log_thread_creation(user_id: int, username: str) -> bool:
    """
    スレッド作成をログ記録キューに追加
    
    Args:
        user_id: ユーザーID
        username: ユーザー名
        
    Returns:
        bool: キューへの追加成功時はTrue
    """
    return queue_thread_log(user_id, username, THREAD_STATUS_CREATION)

def log_thread_close(user_id: int, username: str) -> bool:
    """
    スレッド締め切りをログ記録キューに追加
    
    Args:
        user_id: ユーザーID
        username: ユーザー名
        
    Returns:
        bool: キューへの追加成功時はTrue
    """
    return queue_thread_log(user_id, username, THREAD_STATUS_CLOSING)

def get_log_status(user_id: int) -> Optional[Dict]:
    """
    特定のスレッドのログ記録状態を取得
    
    Args:
        thread_id: スレッドID
        
    Returns:
        Optional[Dict]: ログ記録状態の辞書、存在しない場合はNone
    """
    with _client_lock:
        return _logging_status.get(user_id)

def cleanup():
    """終了時のクリーンアップ処理"""
    stop_worker()
    logger.info("スプレッドシートログ記録モジュールをクリーンアップしました")

# モジュールロード時にワーカースレッドを開始
if SPREADSHEET_LOGGING_ENABLED:
    _start_worker_thread()