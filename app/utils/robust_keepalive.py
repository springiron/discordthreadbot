#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
robust_keepalive.py - シンプルで堅牢なキープアライブモジュール

Koyebなどのクラウドサービスでのインスタンスのスリープを防止するための
シンプルかつ効果的なキープアライブ機能を提供します。
"""

import threading
import time
import logging
import os
import sys
import random
from datetime import datetime

# ロギングの設定 - 標準出力のみ使用
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('robust_keepalive')

# スレッド停止用イベント
stop_event = threading.Event()

# インスタンスID（起動ごとにランダム）
INSTANCE_ID = random.randint(1000, 9999)

# HTTPエラーを減らすための設定
HTTP_ENABLED = False
HTTP_ERROR_COUNT = 0
MAX_HTTP_ERRORS = 3  # この回数HTTPエラーが連続したらHTTPアクティビティを無効化

def generate_file_activity() -> bool:
    """ファイル操作によるアクティビティ生成"""
    try:
        # 書き込み可能なディレクトリを見つける
        if os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
            filepath = "/tmp/keepalive.txt"
        else:
            filepath = "keepalive.txt"
            
        # ファイルに現在時刻を書き込む
        with open(filepath, "w") as f:
            f.write(f"Keepalive timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Instance ID: {INSTANCE_ID}\n")
        
        return True
    except Exception as e:
        logger.debug(f"ファイル活動エラー: {e}")
        return False

def generate_cpu_activity() -> bool:
    """CPU計算によるアクティビティ生成"""
    try:
        # 素数を計算してCPUを使用
        def is_prime(n):
            if n <= 1: return False
            if n <= 3: return True
            if n % 2 == 0 or n % 3 == 0: return False
            i = 5
            while i * i <= n:
                if n % i == 0 or n % (i + 2) == 0: return False
                i += 6
            return True
        
        # ある程度負荷のかかる計算を実行
        count = sum(1 for num in range(2000) if is_prime(num))
        return True
    except Exception as e:
        logger.debug(f"CPU活動エラー: {e}")
        return False

def generate_memory_activity() -> bool:
    """メモリ操作によるアクティビティ生成"""
    try:
        # 一時的にメモリを使用
        data = [random.random() for _ in range(100000)]
        result = sum(data) / len(data)
        del data  # 明示的に解放
        return True
    except Exception as e:
        logger.debug(f"メモリ活動エラー: {e}")
        return False

def generate_http_activity() -> bool:
    """HTTPリクエスト送信によるアクティビティ生成"""
    global HTTP_ENABLED, HTTP_ERROR_COUNT
    
    # HTTPが無効化されている場合はスキップ
    if not HTTP_ENABLED:
        return False
        
    try:
        # requestsがインストールされているか確認
        import requests
        
        # 自分自身にリクエスト送信（成功しなくてもOK、アクティビティが目的）
        response = requests.get("http://localhost:8080/", timeout=1)
        HTTP_ERROR_COUNT = 0  # 成功したらエラーカウントをリセット
        return True
    except ImportError:
        # requestsがインストールされていない
        HTTP_ENABLED = False
        return False
    except Exception as e:
        # HTTPリクエストが失敗した場合
        HTTP_ERROR_COUNT += 1
        if HTTP_ERROR_COUNT >= MAX_HTTP_ERRORS:
            # 規定回数エラーが続いたらHTTPを無効化
            logger.info(f"HTTP活動を無効化します (連続エラー: {HTTP_ERROR_COUNT}回)")
            HTTP_ENABLED = False
        return False

def run_keepalive_cycle():
    """1サイクル分のキープアライブアクティビティを実行"""
    # 最低でも常に2種類のアクティビティを実行
    cpu_result = generate_cpu_activity()
    file_result = generate_file_activity()
    
    # 5サイクルに1回はメモリアクティビティも追加
    if random.randint(1, 5) == 1:
        memory_result = generate_memory_activity()
    
    # HTTPはオプション（失敗してもOK）
    if HTTP_ENABLED and random.randint(1, 3) == 1:
        http_result = generate_http_activity()

def keep_alive_loop(interval: int = 30):
    """メインのキープアライブループ"""
    cycle_count = 0
    start_time = time.time()
    
    logger.info(f"キープアライブスレッド [ID:{INSTANCE_ID}] を開始しました")
    print(f"キープアライブスレッド [ID:{INSTANCE_ID}] を開始しました")
    
    while not stop_event.is_set():
        try:
            # キープアライブアクティビティを実行
            run_keepalive_cycle()
            cycle_count += 1
            
            # 10サイクルごとにステータスを出力
            if cycle_count % 10 == 0:
                uptime = time.time() - start_time
                minutes, seconds = divmod(int(uptime), 60)
                hours, minutes = divmod(minutes, 60)
                days, hours = divmod(hours, 24)
                
                uptime_str = ""
                if days > 0: uptime_str += f"{days}日 "
                if hours > 0 or days > 0: uptime_str += f"{hours}時間 "
                uptime_str += f"{minutes}分 {seconds}秒"
                
                print(f"キープアライブ状態 [ID:{INSTANCE_ID}]: サイクル {cycle_count}, 稼働時間: {uptime_str}")
            
            # 次のサイクルまで待機（1秒間隔で停止チェック）
            for _ in range(interval):
                if stop_event.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            # エラーが発生しても継続
            logger.error(f"キープアライブエラー: {e}")
            time.sleep(5)  # エラー時は少し待機
    
    logger.info("キープアライブループを終了します")
    print("キープアライブループを終了します")

def start_keepalive(port: int = 8080, interval: int = 30) -> threading.Thread:
    """キープアライブスレッドを開始"""
    global HTTP_ENABLED
    
    # ポート番号を設定
    HTTP_ENABLED = True  # 最初は有効化してみる
    
    # スレッドを起動
    thread = threading.Thread(
        target=keep_alive_loop,
        args=(interval,),
        daemon=True,
        name="keepalive"
    )
    thread.start()
    
    if thread.is_alive():
        logger.info(f"キープアライブスレッドを開始しました (間隔: {interval}秒)")
    
    return thread

def stop_keepalive() -> None:
    """キープアライブスレッドを停止"""
    stop_event.set()
    logger.info("キープアライブスレッドの停止を要求しました")