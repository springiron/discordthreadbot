#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spreadsheet_logger_test.py - スプレッドシートロガーのテスト
"""

import sys
import os
import time
import threading
import random
from datetime import datetime

# テスト用の.env設定を読み込む
os.environ["DOTENV_FILE"] = "app/.env"
os.environ["SPREADSHEET_LOGGING_ENABLED"] = "true"

# スプレッドシートログ機能をインポート
from bot.spreadsheet_logger import log_thread_creation, log_thread_close, get_spreadsheet_client, queue_thread_log

def test_single_log():
    """単一のログ記録をテスト"""
    user_id = 12345
    username = "テストユーザー"
    
    print(f"単一ログテスト開始: ID={user_id}, ユーザー={username}")
    result = log_thread_creation(user_id, username)
    print(f"ログ記録結果: {result}")
    
    # 処理完了を待機
    time.sleep(5)

def test_multiple_logs(count=5, delay=1.0):
    """複数のログ記録をテスト"""
    print(f"{count}件の連続ログテスト開始")
    
    for i in range(count):
        user_id = 10000 + i
        username = f"テストユーザー{i}"
        
        if i % 2 == 0:
            result = log_thread_creation(user_id, username)
            log_type = "作成"
        else:
            result = log_thread_close(user_id, username)
            log_type = "終了"
            
        print(f"ログ #{i+1}: ID={user_id}, ユーザー={username}, 種別={log_type}, 結果={result}")
        time.sleep(delay)
    
    # すべての処理完了を待機
    time.sleep(10)
    print("テスト完了")

def test_parallel_logs(thread_count=3, logs_per_thread=5):
    """並列ログ記録をテスト"""
    print(f"{thread_count}スレッドで並列テスト開始 (スレッドあたり{logs_per_thread}件)")
    
    def worker(worker_id):
        for i in range(logs_per_thread):
            user_id = (worker_id * 1000) + i
            username = f"並列テスト{worker_id}-{i}"
            
            if random.choice([True, False]):
                result = log_thread_creation(user_id, username)
                log_type = "作成"
            else:
                result = log_thread_close(user_id, username)
                log_type = "終了"
                
            print(f"ワーカー{worker_id} ログ #{i}: ID={user_id}, ユーザー={username}, 種別={log_type}, 結果={result}")
            time.sleep(random.uniform(0.5, 1.5))
    
    # 複数スレッドで実行
    threads = []
    for i in range(thread_count):
        t = threading.Thread(target=worker, args=(i+1,))
        threads.append(t)
        t.start()
    
    # すべてのスレッドが終了するのを待つ
    for t in threads:
        t.join()
    
    # 処理完了を待機
    time.sleep(15)
    print("並列テスト完了")

def main():
    """テストメイン関数"""
    print("===== スプレッドシートロガーテスト開始 =====")
    
    # クライアントを初期化
    client = get_spreadsheet_client()
    if client is None:
        print("エラー: スプレッドシートクライアントの初期化に失敗しました")
        return
    
    print(f"テスト実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 単一ログテスト
    test_single_log()
    
    # 複数ログテスト (5件)
    test_multiple_logs(5, 1.0)
    
    # 並列ログテスト (3スレッド×4ログ)
    test_parallel_logs(3, 4)
    
    print("===== すべてのテスト完了 =====")
    print("スプレッドシートを確認してください")

if __name__ == "__main__":
    main()