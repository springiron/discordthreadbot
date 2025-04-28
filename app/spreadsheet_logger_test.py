#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_spreadsheet_logger.py - スプレッドシートロガーの動作確認
イベントループを使わない同期版の動作確認
"""

import os
import time
import threading
import random
from datetime import datetime

# 環境変数の設定
os.environ["SPREADSHEET_LOGGING_ENABLED"] = "true"

# スプレッドシートログ機能をインポート
from bot.spreadsheet_logger import (
    log_thread_creation, log_thread_close, 
    get_log_status, queue_thread_log
)

def test_simple():
    """シンプルなログテスト"""
    user_id = int(time.time()) % 10000
    username = f"テストユーザー{user_id}"
    
    print(f"テスト開始: ID={user_id}, ユーザー={username}")
    
    # 作成ログ
    creation_result = log_thread_creation(user_id, username)
    print(f"作成ログ結果: {creation_result}")
    
    # 少し待機
    time.sleep(5)
    
    # 締め切りログ
    close_result = log_thread_close(user_id, username)
    print(f"締め切りログ結果: {close_result}")
    
    # 処理完了を待機
    time.sleep(5)
    
    # 状態確認
    status = get_log_status(user_id)
    print(f"最終状態: {status}")
    
    print("テスト完了")

if __name__ == "__main__":
    print("===== スプレッドシートロガーテスト開始 =====")
    print(f"テスト時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # シンプルテスト実行
    test_simple()
    
    print("===== テスト終了 =====")