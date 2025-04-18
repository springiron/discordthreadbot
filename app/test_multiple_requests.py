#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_multiple_requests.py - スプレッドシートロガーの並列リクエストテスト
クォータ制限対応・リトライメカニズム追加バージョン
"""

import sys
import os
import time
import threading
import random
import queue
from datetime import datetime

# プロジェクトのルートパスを追加
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, os.pardir))
sys.path.append(project_root)

# 環境変数の設定
os.environ["SPREADSHEET_LOGGING_ENABLED"] = "true"

# スプレッドシートロガーをインポート
from bot.spreadsheet_logger import log_thread_creation, log_thread_close, get_spreadsheet_client
# キューへの参照も取得
from bot.spreadsheet_logger import _log_queue

# レート制限に関する設定
MAX_REQUESTS_PER_MINUTE = 50  # 60より少なく設定して安全マージンを確保
QUOTA_RESET_INTERVAL = 65  # 1分間のクォータをリセットする間隔（少し余裕を持たせる）

# リクエストカウンターとタイムスタンプ
request_timestamps = []
request_lock = threading.Lock()

def track_request():
    """リクエストを追跡し、必要に応じて待機"""
    global request_timestamps
    
    with request_lock:
        # 現在の時間を取得
        current_time = time.time()
        
        # 1分以上前のタイムスタンプを削除
        request_timestamps = [ts for ts in request_timestamps if current_time - ts < 60]
        
        # 過去1分間のリクエスト数を確認
        if len(request_timestamps) >= MAX_REQUESTS_PER_MINUTE:
            # クォータ制限に達した場合、最も古いリクエストから60秒経過するまで待機
            oldest_request = min(request_timestamps)
            wait_time = 60 - (current_time - oldest_request) + 5  # 5秒の余裕
            print(f"⚠️ クォータ制限に近づいています。{wait_time:.1f}秒待機します...")
            time.sleep(wait_time)
            # 待機後に再度チェック（再帰）
            return track_request()
        
        # 新しいリクエストを記録
        request_timestamps.append(current_time)
        return True

def safe_log_creation(thread_id, username, max_retries=3):
    """リトライメカニズム付きでスレッド作成ログを記録"""
    retry_count = 0
    backoff_time = 1  # 初期待機時間（秒）
    
    while retry_count < max_retries:
        try:
            # リクエスト頻度を管理
            track_request()
            
            # ログを記録
            result = log_thread_creation(thread_id, username)
            return result
        except Exception as e:
            retry_count += 1
            
            # クォータ制限エラーの場合
            if "RATE_LIMIT_EXCEEDED" in str(e) or "Quota exceeded" in str(e):
                # 指数バックオフで待機時間を計算
                wait_time = backoff_time * (2 ** (retry_count - 1))
                print(f"⚠️ クォータ制限エラー: ID={thread_id}, リトライ {retry_count}/{max_retries} - {wait_time}秒待機...")
                time.sleep(wait_time)
            else:
                print(f"❌ エラー: {e}, ID={thread_id}, リトライ {retry_count}/{max_retries}")
                time.sleep(1)
    
    # 最大リトライ回数を超えた場合
    print(f"❌ 最大リトライ回数を超えました: ID={thread_id}")
    return False

def safe_log_close(thread_id, username, max_retries=3):
    """リトライメカニズム付きでスレッド締め切りログを記録"""
    retry_count = 0
    backoff_time = 1  # 初期待機時間（秒）
    
    while retry_count < max_retries:
        try:
            # リクエスト頻度を管理
            track_request()
            
            # ログを記録
            result = log_thread_close(thread_id, username)
            return result
        except Exception as e:
            retry_count += 1
            
            # クォータ制限エラーの場合
            if "RATE_LIMIT_EXCEEDED" in str(e) or "Quota exceeded" in str(e):
                # 指数バックオフで待機時間を計算
                wait_time = backoff_time * (2 ** (retry_count - 1))
                print(f"⚠️ クォータ制限エラー: ID={thread_id}, リトライ {retry_count}/{max_retries} - {wait_time}秒待機...")
                time.sleep(wait_time)
            else:
                print(f"❌ エラー: {e}, ID={thread_id}, リトライ {retry_count}/{max_retries}")
                time.sleep(1)
    
    # 最大リトライ回数を超えた場合
    print(f"❌ 最大リトライ回数を超えました: ID={thread_id}")
    return False

def simulate_requests(worker_id, request_count=20, delay_factor=1.0):
    """複数のスレッド作成ログリクエストをシミュレート（レート制限考慮版）"""
    print(f"ワーカー{worker_id}：{request_count}件のリクエストを開始します")
    
    for i in range(request_count):
        # ユニークなスレッドIDを生成
        thread_id = 1000000 + (worker_id * 1000) + i
        username = f"テストユーザー{worker_id}-{i}"
        
        # ランダムに作成と締め切りのログを記録（安全なバージョン）
        if random.choice([True, False]):
            print(f"ワーカー{worker_id}：作成ログ #{i} - ID={thread_id}, ユーザー={username}")
            safe_log_creation(thread_id, username)
        else:
            print(f"ワーカー{worker_id}：締め切りログ #{i} - ID={thread_id}, ユーザー={username}")
            safe_log_close(thread_id, username)
        
        # ランダムな待機時間（delay_factorで調整可能）
        base_delay = random.uniform(0.3, 0.8) * delay_factor
        time.sleep(base_delay)
        
        # 5回に1回、ランダムに長い待機を入れる
        if i % 5 == 0:
            time.sleep(random.uniform(1.0, 2.0) * delay_factor)

def wait_for_queue_completion(max_wait_seconds=120):
    """キューが空になるか、タイムアウトするまで待機"""
    wait_start = time.time()
    initial_queue_size = _log_queue.qsize()
    
    print(f"キューの処理完了を待機中... 初期キューサイズ: {initial_queue_size}")
    
    # キューが空になるか、タイムアウトするまで待機
    last_remaining = initial_queue_size
    
    while not _log_queue.empty() and time.time() - wait_start < max_wait_seconds:
        remaining = _log_queue.qsize()
        
        # キューサイズが変化した場合のみログ出力（ノイズ削減）
        if remaining != last_remaining:
            print(f"残りキュー: {remaining}件 (経過時間: {int(time.time() - wait_start)}秒)")
            last_remaining = remaining
        
        time.sleep(2)
    
    if _log_queue.empty():
        print(f"キューの処理が完了しました！ 経過時間: {int(time.time() - wait_start)}秒")
    else:
        print(f"タイムアウト: まだ {_log_queue.qsize()}件 のキューが残っています")

def get_processed_count():
    """ワーカーが処理したリクエスト数を概算で取得"""
    try:
        from bot.spreadsheet_logger import _logging_status
        return len(_logging_status)
    except:
        return 0

def main():
    """メイン関数：複数のスレッドで同時実行"""
    # 引数からワーカー数とリクエスト数を取得
    worker_count = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    request_count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    wait_time = int(sys.argv[3]) if len(sys.argv) > 3 else 120  # デフォルト120秒
    delay_factor = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0  # 遅延係数
    
    # スプレッドシートクライアントの初期化
    client = get_spreadsheet_client()
    if client is None:
        print("エラー：スプレッドシートクライアントの初期化に失敗しました")
        return
    
    print(f"テスト開始：ワーカー数={worker_count}, リクエスト数/ワーカー={request_count}, 遅延係数={delay_factor}")
    print(f"クォータ制限：{MAX_REQUESTS_PER_MINUTE}リクエスト/分")
    
    # 各ワーカーの開始前に少し待機（初期化完了のため）
    time.sleep(2)
    
    # 開始時間を記録
    start_time = time.time()
    
    # 複数のスレッドで同時実行
    threads = []
    for i in range(worker_count):
        t = threading.Thread(
            target=simulate_requests,
            args=(i+1, request_count, delay_factor),
            name=f"TestWorker-{i+1}"
        )
        threads.append(t)
        t.start()
        
        # ワーカー間の開始時間をずらす（完全な同時開始を避ける）
        time.sleep(0.5)
    
    # すべてのスレッドが終了するのを待つ
    for t in threads:
        t.join()
    
    total_requests = worker_count * request_count
    elapsed_time = time.time() - start_time
    print(f"テスト完了：合計{total_requests}件のリクエストをキューに追加しました（所要時間：{elapsed_time:.2f}秒）")
    
    # キューが空になるまで待機（または指定した時間）
    wait_for_queue_completion(wait_time)
    
    # 処理されたリクエスト数を取得（近似値）
    processed_count = get_processed_count()
    success_rate = processed_count / total_requests * 100 if total_requests > 0 else 0
    
    print(f"処理完了：約{processed_count}件のリクエストが処理されました")
    print(f"成功率：約{success_rate:.1f}%")
    
    # テスト実行時間の情報
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"テスト終了時刻: {now}")
    print("テストが完了しました。スプレッドシートを確認してください。")

if __name__ == "__main__":
    main()