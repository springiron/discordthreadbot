#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ultimate_keepalive.py - 最適化されたキープアライブモジュール

Koyebなどのクラウドプラットフォームでのインスタンススリープを効果的に防止します。
両プロジェクトの最も効果的な部分を組み合わせた最小限の実装です。
"""

import threading
import time
import random
import os
import sys
import logging
from datetime import datetime
from threading import Thread

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('keepalive')

# グローバル変数
stop_event = threading.Event()
instance_id = random.randint(1000, 9999)

# HTTPサーバー部分（FastAPI）- オプション
try:
    from fastapi import FastAPI
    import uvicorn
    
    app = FastAPI()
    
    @app.get("/")
    async def root():
        return {"message": "Server is Online."}
    
    def start_server():
        try:
            uvicorn.run(app, host="0.0.0.0", port=8080, log_level="error")
        except Exception as e:
            logger.error(f"サーバー起動エラー: {e}")
    
    def server_thread():
        t = Thread(target=start_server, daemon=True)
        t.start()
        return t
    
    HAS_SERVER = True
except ImportError:
    HAS_SERVER = False
    logger.warning("FastAPI/uvicornが利用できないため、HTTPサーバーは無効です")

# アクティビティ生成関数
def generate_file_activity():
    """ファイルI/Oアクティビティを生成"""
    try:
        # 書き込み可能なディレクトリを見つける
        if os.path.exists('/tmp') and os.access('/tmp', os.W_OK):
            filepath = "/tmp/keepalive.txt"
        else:
            filepath = "keepalive.txt"
            
        # ファイルに書き込む
        with open(filepath, "w") as f:
            f.write(f"Keepalive timestamp: {time.time()}\n")
            f.write(f"Instance ID: {instance_id}\n")
            f.write(f"Date: {datetime.now().isoformat()}\n")
        
        # 5回に1回詳細ログを出力
        if random.randint(1, 5) == 1:
            msg = f"ファイル活動完了: {filepath}"
            logger.info(msg)
            print(msg)
            
        return True
    except Exception as e:
        logger.debug(f"ファイル活動エラー: {e}")
        return False

def generate_cpu_activity():
    """CPU計算アクティビティを生成"""
    try:
        # 素数判定関数
        def is_prime(n):
            if n <= 1: return False
            if n <= 3: return True
            if n % 2 == 0 or n % 3 == 0: return False
            i = 5
            while i * i <= n:
                if n % i == 0 or n % (i + 2) == 0: return False
                i += 6
            return True
        
        # 計算量を毎回少し変える（パターン検出を避ける）
        size = 1000 + random.randint(0, 1000)
        
        # CPU使用するための計算
        count = sum(1 for num in range(size) if is_prime(num))
        
        # 4回に1回詳細ログを出力
        if random.randint(1, 4) == 1:
            msg = f"CPU活動完了: 素数{count}個"
            logger.info(msg)
            print(msg)
            
        return True
    except Exception as e:
        logger.debug(f"CPU活動エラー: {e}")
        return False

def generate_memory_activity():
    """メモリ使用アクティビティを生成"""
    try:
        # サイズを毎回変える（パターン検出を避ける）
        size = 10000 + random.randint(0, 90000)
        
        # メモリ割り当て
        data = [random.random() for _ in range(size)]
        result = sum(data) / len(data)
        
        # 明示的に解放
        del data
        
        # 6回に1回詳細ログを出力
        if random.randint(1, 6) == 1:
            msg = f"メモリ活動完了: 平均値 {result:.4f}"
            logger.info(msg)
            print(msg)
            
        return True
    except Exception as e:
        logger.debug(f"メモリ活動エラー: {e}")
        return False

def generate_http_activity():
    """HTTPリクエスト送信アクティビティを生成"""
    try:
        import requests
        response = requests.get("http://localhost:8080/", timeout=1)
        
        # 3回に1回詳細ログを出力
        if random.randint(1, 3) == 1:
            msg = f"HTTP活動完了: ステータス {response.status_code}"
            logger.info(msg)
            print(msg)
            
        return True
    except Exception:
        # エラーは無視（HTTPは追加的なアクティビティ）
        return False

def run_keepalive_cycle():
    """1サイクル分のキープアライブアクティビティを実行"""
    # 常に実行する基本アクティビティ
    cpu_result = generate_cpu_activity()
    file_result = generate_file_activity()
    
    # 一定の確率で追加アクティビティを実行
    if random.randint(1, 3) == 1:
        generate_memory_activity()
    
    if HAS_SERVER and random.randint(1, 4) == 1:
        generate_http_activity()
    
    return cpu_result or file_result  # 少なくとも1つ成功すればOK

def keepalive_loop(interval=30):
    """メインのキープアライブループ"""
    cycle_count = 0
    start_time = time.time()
    
    msg = f"キープアライブスレッド[ID:{instance_id}]を開始しました"
    logger.info(msg)
    print(msg)
    
    while not stop_event.is_set():
        try:
            # キープアライブアクティビティを実行
            success = run_keepalive_cycle()
            cycle_count += 1
            
            # 10サイクルごとにステータスを出力
            if cycle_count % 10 == 0:
                uptime = time.time() - start_time
                minutes, seconds = divmod(int(uptime), 60)
                hours, minutes = divmod(minutes, 60)
                
                msg = f"キープアライブ状態[ID:{instance_id}]: サイクル {cycle_count}, 稼働時間: {hours}時間{minutes}分{seconds}秒"
                logger.info(msg)
                print(msg)
            
            # 次のサイクルまで待機（短い間隔で停止チェック）
            for _ in range(interval):
                if stop_event.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            # エラーが発生しても続行
            logger.error(f"キープアライブエラー: {e}")
            # エラー時は少し待機してからリトライ
            time.sleep(5)
    
    msg = "キープアライブループを終了します"
    logger.info(msg)
    print(msg)

def start_keepalive(interval=30):
    """キープアライブ機能を開始"""
    # HTTPサーバーを起動（利用可能な場合）
    server_thread_handle = None
    if HAS_SERVER:
        try:
            server_thread_handle = server_thread()
            logger.info("HTTPサーバーを起動しました")
        except Exception as e:
            logger.error(f"HTTPサーバー起動エラー: {e}")
    
    # キープアライブスレッドを起動
    thread = threading.Thread(
        target=keepalive_loop,
        args=(interval,),
        daemon=True,
        name="keepalive"
    )
    thread.start()
    
    logger.info(f"キープアライブスレッドを開始しました (間隔: {interval}秒)")
    return thread

def stop_keepalive():
    """キープアライブ機能を停止"""
    stop_event.set()
    logger.info("キープアライブスレッドの停止を要求しました")

# 直接実行時の処理
if __name__ == "__main__":
    try:
        print("キープアライブモジュールのテスト実行を開始します")
        keepalive_thread = start_keepalive(interval=30)
        
        # メインスレッドはCtrl+Cで終了するまで待機
        print("Ctrl+Cで終了します...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nキーボード割り込みを検知しました。終了します...")
        stop_keepalive()
        # 少し待機してからプログラム終了
        time.sleep(2)