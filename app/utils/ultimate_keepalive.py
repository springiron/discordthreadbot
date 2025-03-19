#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
improved_keepalive.py - 改良されたキープアライブモジュール

Koyebなどのクラウドプラットフォームでのインスタンススリープを効果的に防止します。
以下の改善を含みます：
- シグナル処理の強化
- 自動再接続メカニズム
- 複数種類のアクティビティによるアンチスリープ
- 詳細な診断ログ
"""

import threading
import time
import random
import os
import sys
import logging
import signal
import requests
from datetime import datetime
from threading import Thread, Event
import atexit

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('keepalive')

# グローバル変数
stop_event = Event()
keep_running = True
instance_id = random.randint(1000, 9999)
keepalive_thread = None
server_thread_handle = None
heartbeat_marker_file = "/tmp/keepalive_heartbeat.txt"

# HTTPサーバー部分（FastAPI）- オプション
try:
    from fastapi import FastAPI
    import uvicorn
    
    app = FastAPI()
    
    @app.get("/")
    async def root():
        """基本的なヘルスチェックエンドポイント"""
        # 最終ハートビート時間を読み取り
        last_heartbeat = "Unknown"
        try:
            if os.path.exists(heartbeat_marker_file):
                with open(heartbeat_marker_file, "r") as f:
                    last_heartbeat = f.read().strip()
        except Exception:
            pass
            
        return {
            "status": "healthy",
            "instance_id": instance_id,
            "uptime": get_uptime_info(),
            "last_heartbeat": last_heartbeat
        }
    
    @app.get("/health")
    async def health():
        """詳細なヘルスチェックエンドポイント"""
        return {
            "status": "healthy",
            "instance_id": instance_id,
            "uptime": get_uptime_info(),
            "memory_info": get_memory_info(),
            "keepalive_status": "running" if not stop_event.is_set() else "stopping"
        }
    
    def start_server(port=8080):
        try:
            uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")
        except Exception as e:
            logger.error(f"サーバー起動エラー: {e}")
    
    def server_thread(port=8080):
        t = Thread(target=start_server, args=(port,), daemon=True)
        t.start()
        return t
    
    HAS_SERVER = True
except ImportError:
    HAS_SERVER = False
    logger.warning("FastAPI/uvicornが利用できないため、HTTPサーバーは無効です")

# ユーティリティ関数
def get_uptime_info():
    """システムのアップタイム情報を取得"""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.readline().split()[0])
        
        minutes, seconds = divmod(int(uptime_seconds), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        
        return {
            "days": days,
            "hours": hours,
            "minutes": minutes,
            "seconds": seconds,
            "total_seconds": uptime_seconds
        }
    except Exception:
        return {"error": "Unable to get uptime"}

def get_memory_info():
    """システムのメモリ情報を取得"""
    try:
        memory_info = {}
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        memory_info[key.strip()] = value.strip()
        return memory_info
    except Exception:
        return {"error": "Unable to get memory info"}

def update_heartbeat_file():
    """ハートビートファイルを更新"""
    try:
        with open(heartbeat_marker_file, "w") as f:
            f.write(datetime.now().isoformat())
    except Exception as e:
        logger.debug(f"ハートビートファイル更新エラー: {e}")

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
        
        # ハートビートファイルも更新
        update_heartbeat_file()
        
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

def generate_network_activity():
    """ネットワークアクティビティを生成"""
    try:
        if HAS_SERVER:
            # ローカルサーバーに接続
            import requests
            response = requests.get("http://localhost:8080/", timeout=1)
            result = response.status_code
        else:
            # プリファレンスリストからホストを選択してpingを実行
            hosts = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
            host = random.choice(hosts)
            res = os.system(f"ping -c 1 -W 2 {host} > /dev/null 2>&1")
            result = "成功" if res == 0 else f"失敗 (コード: {res})"
        
        # 3回に1回詳細ログを出力
        if random.randint(1, 3) == 1:
            msg = f"ネットワーク活動完了: {result}"
            logger.info(msg)
            print(msg)
            
        return True
    except Exception as e:
        logger.debug(f"ネットワーク活動エラー: {e}")
        return False

def generate_http_request():
    """HTTPリクエストアクティビティを生成（Koyeb対応）"""
    try:
        # 自身のHTTPサーバーにリクエストを送信
        response = requests.get("http://localhost:8080/", timeout=3)
        status_code = response.status_code
        
        # 2回に1回詳細ログを出力
        if random.randint(1, 2) == 1:
            msg = f"HTTP活動完了: ステータス {status_code}"
            logger.info(msg)
            print(msg)
            
        return True
    except Exception as e:
        logger.debug(f"HTTP活動エラー: {e}")
        return False

def run_keepalive_cycle():
    """1サイクル分のキープアライブアクティビティを実行"""
    # Koyeb対応：HTTP、CPU、ファイル、メモリの全てのアクティビティを実行
    results = []
    
    # 常にHTTPリクエストを試行（Koyeb向け最適化）
    results.append(generate_http_request())
    
    # CPU活動を実行
    results.append(generate_cpu_activity())
    
    # ファイル活動を実行
    results.append(generate_file_activity())
    
    # メモリ活動を実行（2回に1回）
    if random.randint(1, 2) == 1:
        results.append(generate_memory_activity())
    
    # ネットワーク活動を実行（3回に1回）
    if random.randint(1, 3) == 1:
        results.append(generate_network_activity())
    
    return any(results)  # 少なくとも1つ成功すればOK

def keepalive_loop(interval=20):
    """メインのキープアライブループ（Koyeb対応バージョン）"""
    global keep_running
    
    cycle_count = 0
    start_time = time.time()
    short_interval = max(5, interval // 4)  # より短い間隔（最低5秒）
    
    msg = f"キープアライブスレッド[ID:{instance_id}]を開始しました（Koyeb対応版）"
    logger.info(msg)
    print(msg)
    
    # Koyeb対応：開始直後にアクティビティを実行
    try:
        run_keepalive_cycle()
        logger.info("初期キープアライブアクティビティを実行しました")
    except Exception as e:
        logger.error(f"初期キープアライブエラー: {e}")
    
    # メインループ
    while keep_running and not stop_event.is_set():
        try:
            # Koyeb対応：より頻繁にHTTPリクエストを実行
            if cycle_count % 3 == 0:  # 3サイクルごとにHTTPリクエスト
                generate_http_request()
            
            # 通常のキープアライブアクティビティを実行
            success = run_keepalive_cycle()
            cycle_count += 1
            
            # 5サイクルごとにステータスを出力
            if cycle_count % 5 == 0:
                uptime = time.time() - start_time
                minutes, seconds = divmod(int(uptime), 60)
                hours, minutes = divmod(minutes, 60)
                
                msg = f"キープアライブ状態[ID:{instance_id}]: サイクル {cycle_count}, 稼働時間: {hours}時間{minutes}分{seconds}秒"
                logger.info(msg)
                print(msg)
                
                # ハートビートファイルも更新
                update_heartbeat_file()
            
            # Koyeb対応：より短い間隔で待機チェック
            wait_until = time.time() + short_interval
            activity_done = False
            
            # 短いインターバルでループし、停止チェックと時々アクティビティを実行
            while time.time() < wait_until and keep_running and not stop_event.is_set():
                # 半分のタイミングでHTTPリクエストを実行
                if not activity_done and time.time() > wait_until - (short_interval / 2):
                    try:
                        generate_http_request()
                        activity_done = True
                    except Exception:
                        pass
                time.sleep(0.5)  # 短い間隔で停止チェック
            
            # 残りの待機時間
            remaining_time = interval - short_interval
            if remaining_time > 0 and keep_running and not stop_event.is_set():
                time.sleep(remaining_time)
                
        except Exception as e:
            # エラーが発生しても続行
            logger.error(f"キープアライブエラー: {e}")
            # エラー時は少し待機してからリトライ
            time.sleep(2)  # より短い待機時間
    
    msg = "キープアライブループを終了します"
    logger.info(msg)
    print(msg)

# シグナルハンドラ
def handle_signal(signum, frame):
    """シグナルハンドラ - 終了プロセスを制御"""
    global keep_running
    
    signals = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM",
        signal.SIGHUP: "SIGHUP"
    }
    sig_name = signals.get(signum, f"Signal {signum}")
    
    logger.warning(f"{sig_name} シグナルを受信しました - 終了を準備します")
    print(f"{sig_name} シグナルを受信しました - 終了を準備します")
    
    # 自動再起動モードの場合、一部のシグナルを無視
    # SIGTERM対応のみ
    if signum == signal.SIGTERM:
        logger.info("SIGTERMを受信 - 通常終了を実行します")
        keep_running = False
        stop_event.set()
    
    # デバッグ用：シグナル処理の状態を記録
    try:
        with open("/tmp/keepalive_signal.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - Received {sig_name}\n")
    except Exception:
        pass

# 終了時の処理
def cleanup():
    """終了時のクリーンアップ処理"""
    logger.info("終了処理を実行中...")
    
    # 停止イベントを設定
    if not stop_event.is_set():
        stop_event.set()
    
    # 少し待機して、スレッドが正常に終了できるようにする
    logger.info("スレッドの終了を待機中...")
    time.sleep(1)
    
    logger.info("終了処理が完了しました。")

def start_keepalive(interval=30, port=8080, handle_signals=True):
    """キープアライブ機能を開始"""
    global keepalive_thread, server_thread_handle, keep_running
    
    # 初期化
    keep_running = True
    stop_event.clear()
    
    # シグナルハンドラの登録
    if handle_signals:
        logger.info("シグナルハンドラを登録しています...")
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGHUP, handle_signal)
    
    # 終了時の処理を登録
    atexit.register(cleanup)
    
    # HTTPサーバーを起動（利用可能な場合）
    if HAS_SERVER:
        try:
            server_thread_handle = server_thread(port)
            logger.info(f"HTTPサーバーを起動しました（ポート: {port}）")
        except Exception as e:
            logger.error(f"HTTPサーバー起動エラー: {e}")
    
    # 初期ハートビートファイルを作成
    update_heartbeat_file()
    
    # キープアライブスレッドを起動
    keepalive_thread = threading.Thread(
        target=keepalive_loop,
        args=(interval,),
        daemon=True,
        name="keepalive"
    )
    keepalive_thread.start()
    
    logger.info(f"キープアライブスレッドを開始しました (間隔: {interval}秒, ID: {instance_id})")
    return keepalive_thread

def stop_keepalive():
    """キープアライブ機能を停止"""
    global keep_running
    
    logger.info("キープアライブスレッドの停止を要求しました")
    keep_running = False
    stop_event.set()
    
    # ファイナライズ状態を記録
    try:
        with open("/tmp/keepalive_shutdown.log", "a") as f:
            f.write(f"{datetime.now().isoformat()} - Shutdown requested\n")
    except Exception:
        pass
    
    return True

# 直接実行時の処理
if __name__ == "__main__":
    try:
        print("==== 改良版キープアライブモジュールのテスト実行 ====")
        print(f"インスタンスID: {instance_id}")
        
        # コマンドライン引数の解析
        import argparse
        parser = argparse.ArgumentParser(description="キープアライブモジュールのテスト実行")
        parser.add_argument("--interval", type=int, default=30, help="アクティビティ間隔（秒）")
        parser.add_argument("--port", type=int, default=8080, help="HTTPサーバーのポート")
        parser.add_argument("--no-signals", action="store_true", help="シグナルハンドリングを無効化")
        args = parser.parse_args()
        
        # キープアライブ開始
        keepalive_thread = start_keepalive(
            interval=args.interval,
            port=args.port,
            handle_signals=not args.no_signals
        )
        
        # メインスレッドはCtrl+Cで終了するまで待機
        print("Ctrl+Cで終了します...")
        while keep_running and not stop_event.is_set():
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nキーボード割り込みを検知しました。終了します...")
        stop_keepalive()
        # 少し待機してからプログラム終了
        time.sleep(2)
    finally:
        print("キープアライブテストを終了します")