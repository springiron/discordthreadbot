#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スプレッドシートログ記録モジュール - 同期処理対応版
(イベントループ問題修正版)
"""

import threading
import discord
from typing import Optional, Dict
import queue
import time
from datetime import datetime
import random
import traceback
from config import (
    SPREADSHEET_LOGGING_ENABLED, SPREADSHEET_CREDENTIALS_FILE,
    SPREADSHEET_ID, SPREADSHEET_SHEET_NAME, SPREADSHEET_LOG_QUEUE_SIZE,
    THREAD_STATUS_CREATION, THREAD_STATUS_CLOSING
)
from utils.spreadsheet_utils import SpreadsheetClient
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

def get_spreadsheet_client() -> Optional[SpreadsheetClient]:
    """
    スプレッドシートクライアントのシングルトンインスタンスを取得
    
    Returns:
        Optional[SpreadsheetClient]: スプレッドシートクライアント、無効な場合はNone
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
            _spreadsheet_client = SpreadsheetClient(
                credentials_file=SPREADSHEET_CREDENTIALS_FILE,
                spreadsheet_id=SPREADSHEET_ID,
                sheet_name=SPREADSHEET_SHEET_NAME
            )
            
            # 初期接続を試みる
            try:
                connection_success = _spreadsheet_client.connect()
                
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
        return
    
    # 既存のスレッドが存在しないか、停止している場合は新しいスレッドを開始
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
    retry_count = 0
    max_retries = 3
    
    while not _stop_worker.is_set():
        try:
            # キューからログエントリを取得（タイムアウト付き）
            try:
                log_entry = _log_queue.get(timeout=1.0)
            except queue.Empty:
                # キューが空の場合は次のループへ
                continue
            
            # 終了シグナルを検出
            if log_entry is None:
                logger.info("終了シグナルを受信しました。ワーカーを終了します。")
                break
                
            # ログエントリを処理
            user_id = log_entry.get("user_id")
            username = log_entry.get("username", "不明")
            fixed_value = log_entry.get("fixed_value", "")
            status = log_entry.get("status", "募集作成")
            
            logger.debug(f"ログエントリ処理開始: ID={user_id}, ユーザー={username}, 状態={status}")
            
            # クライアントを取得
            client = get_spreadsheet_client()
            if client is None:
                logger.error(f"スプレッドシートクライアントが利用できません: {log_entry}")
                _log_queue.task_done()
                continue
            
            # 処理成功フラグとリトライカウンタをリセット
            processing_success = False
            retry_count = 0
            
            # スプレッドシートに記録（同期処理）
            try:
                # 同期処理を実行
                result = client.add_thread_log(
                    user_id=str(user_id),
                    username=username,
                    fixed_value=fixed_value,
                    status=status
                )
                
                # 成功
                processing_success = True
                
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
                # エラー処理
                logger.error(f"ログ記録処理エラー: {e}")
                with _client_lock:
                    _logging_status[user_id] = {
                        "status": "error",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                        "username": username,
                        "log_type": status,
                        "retries": retry_count
                    }
            
            # タスク完了を通知
            _log_queue.task_done()
                
        except Exception as e:
            # ワーカーループの最上位例外ハンドラ
            logger.error(f"ワーカースレッドでの予期しないエラー: {e}")
            logger.debug(f"エラー詳細:\n{traceback.format_exc()}")
            # エラーが発生しても処理を継続するため短時間待機
            time.sleep(1)
    
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
    
    # ワーカースレッドの状態確認と再開
    global _worker_thread, _stop_worker
    
    if _worker_thread is None or not _worker_thread.is_alive():
        logger.info("ワーカースレッドが停止しています。再起動します。")
        _stop_worker.clear()
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
        # キューが満杯の場合、古いエントリを削除して空きを作る
        try:
            try:
                # まず古いエントリを取り出す
                old_entry = _log_queue.get(block=False)
                logger.warning(f"キューが満杯のため古いエントリを削除: ID={old_entry.get('user_id')}")
                _log_queue.task_done()  # タスク完了を通知
            except queue.Empty:
                # 競合状態によりキューが空の場合は無視
                pass
            
            # 再度追加を試みる
            _log_queue.put(log_entry, block=False)
            logger.debug(f"スレッドログをキューに追加しました(2回目の試行): ID={user_id}, ユーザー={username}")
            return True
        except Exception as e:
            logger.error(f"キュー操作中にエラー: {e}")
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