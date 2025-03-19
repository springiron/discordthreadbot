#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
robust_keepalive.py - シンプルで堅牢なキープアライブモジュール

Koyebなどのクラウドサービスでのインスタンスのスリープを防止するための
シンプルかつ効果的なキープアライブ機能を提供します。

特徴:
- 30秒間隔での高頻度キープアライブ
- 複数タイプのアクティビティ（HTTP、ファイルI/O、CPU、メモリ）
- 標準出力とログファイルへのダブル出力
- 堅牢なエラーハンドリング
- シンプルで専用のモジュール設計
"""

import threading
import time
import logging
import os
import sys
import random
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

# 必要に応じてHTTPリクエスト用のライブラリをインポート
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("警告: requestsライブラリがインストールされていません。HTTP活動は無効化されます。")

# ロギングの設定
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("keepalive.log")
    ]
)
logger = logging.getLogger('robust_keepalive')

# スレッド停止用イベント
stop_event = threading.Event()

# アクティビティ状態の追跡
activity_state = {
    "start_time": time.time(),
    "cycle_count": 0,
    "http_requests": 0,
    "file_operations": 0,
    "cpu_activities": 0,
    "memory_activities": 0,
    "errors": {
        "http": 0,
        "file": 0,
        "cpu": 0,
        "memory": 0
    },
    "last_activity": None,
    "instance_id": random.randint(1000, 9999)
}

def generate_http_activity(port: int = 8080) -> bool:
    """
    HTTPリクエストを送信してネットワークアクティビティを生成
    
    Args:
        port: ローカルサーバーのポート番号
        
    Returns:
        bool: 成功した場合はTrue
    """
    if not REQUESTS_AVAILABLE:
        return False
    
    try:
        # 自身のローカルサーバーにアクセス
        response = requests.get(f"http://localhost:{port}/", timeout=3)
        success = response.status_code == 200
        
        # 状態を更新
        activity_state["http_requests"] += 1
        activity_state["last_activity"] = "http"
        
        # 5回ごとに詳細ログを出力
        if activity_state["http_requests"] % 5 == 0:
            output_msg = f"キープアライブ: HTTP活動 #{activity_state['http_requests']} 実行 (ステータス: {response.status_code})"
            logger.info(output_msg)
            print(output_msg)  # 標準出力にも表示
            
        return success
    except Exception as e:
        activity_state["errors"]["http"] += 1
        logger.error(f"HTTP活動中にエラーが発生: {e}")
        return False

def generate_file_activity() -> bool:
    """
    ファイル操作を実行してディスクI/Oアクティビティを生成
    
    Returns:
        bool: 成功した場合はTrue
    """
    try:
        # キープアライブ情報をファイルに書き込み
        keepalive_dir = "keepalive_data"
        os.makedirs(keepalive_dir, exist_ok=True)
        
        # タイムスタンプを含むファイル名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{keepalive_dir}/keepalive_{timestamp}.json"
        
        # ステータス情報を記録
        data = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "cycle": activity_state["cycle_count"],
            "instance_id": activity_state["instance_id"],
            "uptime_seconds": time.time() - activity_state["start_time"]
        }
        
        # 定期的に古いファイルをクリーンアップ（10回ごと）
        if activity_state["file_operations"] % 10 == 0:
            try:
                files = [f for f in os.listdir(keepalive_dir) if f.startswith("keepalive_")]
                if len(files) > 20:  # 20ファイル以上あれば古いものを削除
                    files.sort()
                    for old_file in files[:len(files)-20]:
                        os.remove(os.path.join(keepalive_dir, old_file))
                    logger.info(f"古いキープアライブファイルをクリーンアップしました ({len(files)-20}件)")
            except Exception as cleanup_error:
                logger.warning(f"ファイルクリーンアップでエラー: {cleanup_error}")
        
        # 新しいファイルを書き込み
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
            
        # メインのステータスファイルも更新
        with open(f"{keepalive_dir}/keepalive_current.json", "w") as f:
            activity_state["file_operations"] += 1
            activity_state["last_activity"] = "file"
            json.dump(activity_state, f, indent=2)
        
        # 3回ごとに詳細ログを出力
        if activity_state["file_operations"] % 3 == 0:
            output_msg = f"キープアライブ: ファイル活動 #{activity_state['file_operations']} 実行"
            logger.info(output_msg)
            print(output_msg)  # 標準出力にも表示
            
        return True
    except Exception as e:
        activity_state["errors"]["file"] += 1
        logger.error(f"ファイル活動中にエラーが発生: {e}")
        return False

def generate_cpu_activity() -> bool:
    """
    CPU計算を実行してCPUアクティビティを生成
    
    Returns:
        bool: 成功した場合はTrue
    """
    try:
        # 素数計算によるCPU負荷の生成（計算量を調整可能）
        def is_prime(n):
            """素数判定関数"""
            if n <= 1:
                return False
            if n <= 3:
                return True
            if n % 2 == 0 or n % 3 == 0:
                return False
            i = 5
            while i * i <= n:
                if n % i == 0 or n % (i + 2) == 0:
                    return False
                i += 6
            return True
        
        # 現在のサイクル数に基づいて計算量を変える
        calculation_size = 1000 + (activity_state["cycle_count"] % 10) * 100
        
        # 素数を計算
        count = 0
        for num in range(calculation_size):
            if is_prime(num):
                count += 1
        
        activity_state["cpu_activities"] += 1
        activity_state["last_activity"] = "cpu"
        
        # 4回ごとに詳細ログを出力
        if activity_state["cpu_activities"] % 4 == 0:
            output_msg = f"キープアライブ: CPU活動 #{activity_state['cpu_activities']} 実行 (素数: {count}個)"
            logger.info(output_msg)
            print(output_msg)  # 標準出力にも表示
            
        return True
    except Exception as e:
        activity_state["errors"]["cpu"] += 1
        logger.error(f"CPU活動中にエラーが発生: {e}")
        return False

def generate_memory_activity() -> bool:
    """
    メモリ操作を実行してメモリアクティビティを生成
    
    Returns:
        bool: 成功した場合はTrue
    """
    try:
        # メモリ使用によるアクティビティ生成
        # サイズはサイクルごとに変化させる（メモリリークを防ぐため解放も確実に行う）
        size = 100000 + (activity_state["cycle_count"] % 5) * 50000
        
        # 一時的な大きなリストを作成
        memory_data = [random.random() for _ in range(size)]
        
        # データに対して何らかの操作を実行
        result = sum(memory_data) / len(memory_data)
        
        # 明示的に解放
        del memory_data
        
        activity_state["memory_activities"] += 1
        activity_state["last_activity"] = "memory"
        
        # 6回ごとに詳細ログを出力
        if activity_state["memory_activities"] % 6 == 0:
            output_msg = f"キープアライブ: メモリ活動 #{activity_state['memory_activities']} 実行 (平均値: {result:.4f})"
            logger.info(output_msg)
            print(output_msg)  # 標準出力にも表示
            
        return True
    except Exception as e:
        activity_state["errors"]["memory"] += 1
        logger.error(f"メモリ活動中にエラーが発生: {e}")
        return False

def run_keepalive_cycle(port: int = 8080) -> None:
    """
    1サイクルのキープアライブアクティビティを実行
    
    Args:
        port: ローカルサーバーのポート番号
    """
    cycle_start = time.time()
    activity_state["cycle_count"] += 1
    
    # サイクル数に基づいてアクティビティを選択
    cycle = activity_state["cycle_count"]
    
    # すべてのサイクルでステータスを更新して表示（5サイクルごとに詳細表示）
    if cycle % 5 == 0:
        uptime = time.time() - activity_state["start_time"]
        minutes, seconds = divmod(int(uptime), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        
        uptime_str = ""
        if days > 0:
            uptime_str += f"{days}日 "
        if hours > 0 or days > 0:
            uptime_str += f"{hours}時間 "
        uptime_str += f"{minutes}分 {seconds}秒"
        
        output_msg = (
            f"キープアライブ状態 [ID:{activity_state['instance_id']}]: "
            f"サイクル {cycle}, 稼働時間: {uptime_str}, "
            f"HTTP: {activity_state['http_requests']}, "
            f"ファイル: {activity_state['file_operations']}, "
            f"CPU: {activity_state['cpu_activities']}, "
            f"メモリ: {activity_state['memory_activities']}"
        )
        logger.info(output_msg)
        print(output_msg)  # 標準出力にも表示
    
    # すべてのサイクルで少なくとも1つのアクティビティを実行
    activity_executed = False
    
    # サイクルに基づいたアクティビティ選択ロジック
    if cycle % 2 == 0:  # 偶数サイクル
        generate_http_activity(port)
        activity_executed = True
    
    if cycle % 3 == 0:  # 3の倍数サイクル
        generate_file_activity()
        activity_executed = True
    
    if cycle % 4 == 0:  # 4の倍数サイクル
        generate_cpu_activity()
        activity_executed = True
    
    if cycle % 5 == 0:  # 5の倍数サイクル
        generate_memory_activity()
        activity_executed = True
    
    # どのアクティビティも実行されなかった場合はデフォルトのCPUアクティビティを実行
    if not activity_executed:
        generate_cpu_activity()
    
    # サイクル実行時間を計測して記録
    cycle_duration = time.time() - cycle_start
    
    # 異常に長いサイクルの場合は警告
    if cycle_duration > 2.0:  # 2秒以上かかったら警告
        logger.warning(f"キープアライブサイクル {cycle} の実行に {cycle_duration:.2f}秒かかりました（通常より長い）")

def keep_alive_loop(port: int = 8080, interval: int = 30) -> None:
    """
    メインのキープアライブループ関数
    
    Args:
        port: ローカルサーバーのポート番号
        interval: キープアライブサイクルの間隔（秒）
    """
    logger.info(f"ロバストキープアライブスレッド [ID:{activity_state['instance_id']}] を開始しました")
    print(f"ロバストキープアライブスレッド [ID:{activity_state['instance_id']}] を開始しました")
    
    while not stop_event.is_set():
        try:
            # 1回のキープアライブサイクルを実行
            run_keepalive_cycle(port)
            
            # 次のサイクルまで待機
            # 長いスリープを避けるために複数の短いスリープに分割
            for _ in range(interval):
                if stop_event.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            # 予期せぬエラーが発生しても停止せず継続
            logger.error(f"キープアライブループでエラーが発生: {e}")
            try:
                # スタックトレースをログに記録
                import traceback
                logger.error(traceback.format_exc())
            except:
                pass
            
            # エラー発生後は少し待機してから次のサイクルへ
            time.sleep(5)
    
    logger.info("キープアライブループを終了します")
    print("キープアライブループを終了します")

def start_keepalive(port: int = 8080, interval: int = 30) -> threading.Thread:
    """
    キープアライブスレッドを起動する関数
    
    Args:
        port: ローカルサーバーのポート番号
        interval: キープアライブサイクルの間隔（秒）
        
    Returns:
        threading.Thread: 起動したスレッド
    """
    thread = threading.Thread(
        target=keep_alive_loop, 
        args=(port, interval), 
        daemon=True,
        name="robust-keepalive"
    )
    thread.start()
    
    # 短い待機でスレッドが正常に開始されたことを確認
    time.sleep(1)
    
    if thread.is_alive():
        logger.info(f"ロバストキープアライブスレッドを開始しました (間隔: {interval}秒)")
        print(f"ロバストキープアライブスレッドを開始しました (間隔: {interval}秒)")
    else:
        logger.error("キープアライブスレッドの起動に失敗しました")
        print("キープアライブスレッドの起動に失敗しました")
    
    return thread

def stop_keepalive() -> None:
    """
    キープアライブスレッドを停止する関数
    """
    stop_event.set()
    logger.info("キープアライブスレッドの停止を要求しました")
    print("キープアライブスレッドの停止を要求しました")

# 単体テスト用のコード
if __name__ == "__main__":
    print("ロバストキープアライブモジュールの単体テスト開始")
    
    # キープアライブスレッドを起動
    keepalive_thread = start_keepalive(port=8080, interval=30)
    
    try:
        # テスト用にメインスレッドで少し待機
        print("Ctrl+Cで終了します...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nキーボード割り込みを検知しました。終了します...")
    finally:
        # キープアライブスレッドを停止
        stop_keepalive()
        
        # スレッドの終了を最大10秒待機
        keepalive_thread.join(timeout=10)
        
        print("テスト終了")