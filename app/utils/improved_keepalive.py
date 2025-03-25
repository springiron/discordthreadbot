#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
improved_keepalive.py - クロスプラットフォーム対応・nohup最適化版

Koyebなどのクラウドプラットフォームでのインスタンススリープを効果的に防止します。
Windows、Linux、MacOSで動作し、nohup環境でも安定して継続実行します。

改善点：
- nohup環境での安定動作
- クロスプラットフォーム対応
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
import platform
import tempfile
from datetime import datetime
from threading import Thread, Event
import atexit

# OSの種類を判定
IS_WINDOWS = platform.system() == "Windows"

# nohup環境かどうかを検出
RUNNING_WITH_NOHUP = "nohup" in os.environ.get('_', '')

# 一時ディレクトリパスを取得（クロスプラットフォーム対応）
TMP_DIR = tempfile.gettempdir()

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
heartbeat_marker_file = os.path.join(TMP_DIR, "keepalive_heartbeat.txt")
watchdog_file = os.path.join(TMP_DIR, "keepalive_watchdog.txt")

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
            "last_heartbeat": last_heartbeat,
            "nohup_detected": RUNNING_WITH_NOHUP
        }
    
    @app.get("/health")
    async def health():
        """詳細なヘルスチェックエンドポイント"""
        return {
            "status": "healthy",
            "instance_id": instance_id,
            "uptime": get_uptime_info(),
            "memory_info": get_memory_info(),
            "keepalive_status": "running" if not stop_event.is_set() else "stopping",
            "nohup_detected": RUNNING_WITH_NOHUP
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
    """システムのアップタイム情報を取得（クロスプラットフォーム対応）"""
    try:
        # Windowsの場合は代替手段でアップタイムを計算
        if IS_WINDOWS:
            import ctypes
            lib = ctypes.windll.kernel32
            tick_count = lib.GetTickCount64()
            uptime_seconds = tick_count / 1000.0
        else:
            # UNIXシステムの場合は/proc/uptimeを使用
            if os.path.exists('/proc/uptime'):
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.readline().split()[0])
            else:
                # 他の方法も失敗した場合、Pythonプロセスの開始時間を使用
                import psutil
                proc = psutil.Process(os.getpid())
                uptime_seconds = time.time() - proc.create_time()
        
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
    except Exception as e:
        logger.debug(f"アップタイム取得エラー: {e}")
        return {"error": "Unable to get uptime"}

def get_memory_info():
    """システムのメモリ情報を取得（クロスプラットフォーム対応）"""
    try:
        # psutilがインストールされている場合はそれを使用
        import psutil
        vm = psutil.virtual_memory()
        return {
            "total": vm.total,
            "available": vm.available,
            "percent": vm.percent
        }
    except ImportError:
        # psutilがない場合、プラットフォーム固有の方法を試行
        memory_info = {"note": "limited info (psutil not available)"}
        
        if not IS_WINDOWS and os.path.exists('/proc/meminfo'):
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if ':' in line:
                            key, value = line.split(':', 1)
                            memory_info[key.strip()] = value.strip()
            except Exception as e:
                logger.debug(f"meminfo読み取りエラー: {e}")
        
        return memory_info
    except Exception as e:
        logger.debug(f"メモリ情報取得エラー: {e}")
        return {"error": f"Unable to get memory info: {e}"}

def update_heartbeat_file():
    """ハートビートファイルを更新"""
    try:
        current_time = datetime.now().isoformat()
        with open(heartbeat_marker_file, "w") as f:
            f.write(current_time)
        
        # ウォッチドッグファイルも更新
        try:
            with open(watchdog_file, "w") as f:
                f.write(f"{current_time}\n{instance_id}\n{RUNNING_WITH_NOHUP}")
        except Exception as e:
            logger.debug(f"ウォッチドッグファイル更新エラー: {e}")
            
    except Exception as e:
        logger.debug(f"ハートビートファイル更新エラー: {e}")

# アクティビティ生成関数
def generate_file_activity():
    """ファイルI/Oアクティビティを生成（クロスプラットフォーム対応）"""
    try:
        # 一時ディレクトリに書き込む
        filepath = os.path.join(TMP_DIR, "keepalive.txt")
            
        # ファイルに書き込む
        with open(filepath, "w") as f:
            f.write(f"Keepalive timestamp: {time.time()}\n")
            f.write(f"Instance ID: {instance_id}\n")
            f.write(f"Date: {datetime.now().isoformat()}\n")
            f.write(f"OS: {platform.system()} {platform.release()}\n")
            f.write(f"Nohup detected: {RUNNING_WITH_NOHUP}\n")
        
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
    """ネットワークアクティビティを生成（クロスプラットフォーム対応）"""
    try:
        if HAS_SERVER:
            # ローカルサーバーに接続
            import requests
            response = requests.get("http://localhost:8080/", timeout=1)
            result = response.status_code
        else:
            # プリファレンスリストからホストを選択
            hosts = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
            host = random.choice(hosts)
            
            # Windowsとその他で異なるpingコマンド
            if IS_WINDOWS:
                ping_cmd = f"ping -n 1 -w 2000 {host} > nul 2>&1"
            else:
                ping_cmd = f"ping -c 1 -W 2 {host} > /dev/null 2>&1"
                
            res = os.system(ping_cmd)
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
    """HTTPリクエストアクティビティを生成（Koyeb/nohup対応）"""
    try:
        # requestsがインストールされているか確認
        import requests
        
        # 自身のHTTPサーバーにリクエストを送信
        if HAS_SERVER:
            response = requests.get("http://localhost:8080/", timeout=3)
            status_code = response.status_code
        else:
            # サーバーが利用できない場合は外部URLにリクエスト
            urls = [
                "https://httpbin.org/get",
                "https://www.google.com",
                "https://www.cloudflare.com"
            ]
            url = random.choice(urls)
            response = requests.get(url, timeout=5)
            status_code = response.status_code
        
        # 2回に1回詳細ログを出力
        if random.randint(1, 2) == 1:
            msg = f"HTTP活動完了: ステータス {status_code}"
            logger.info(msg)
            print(msg)
            
        return True
    except ImportError:
        logger.debug("requestsライブラリがインストールされていません")
        return False
    except Exception as e:
        logger.debug(f"HTTP活動エラー: {e}")
        return False

def run_keepalive_cycle():
    """1サイクル分のキープアライブアクティビティを実行"""
    # クロスプラットフォーム対応：HTTP、CPU、ファイル、メモリの全てのアクティビティを実行
    results = []
    
    # ファイル活動を実行（最も信頼性が高い）
    results.append(generate_file_activity())
    
    # CPU活動を実行
    results.append(generate_cpu_activity())
    
    # HTTPリクエストを試行（失敗しても続行）
    try:
        results.append(generate_http_request())
    except Exception:
        pass
    
    # メモリ活動を実行（2回に1回）
    if random.randint(1, 2) == 1:
        results.append(generate_memory_activity())
    
    # ネットワーク活動を実行（3回に1回）
    if random.randint(1, 3) == 1:
        results.append(generate_network_activity())
    
    # nohup環境では追加のファイル活動を実行
    if RUNNING_WITH_NOHUP:
        # 追加のウォッチドッグファイルを更新
        try:
            with open(os.path.join(TMP_DIR, f"nohup_keepalive_{instance_id}.txt"), "w") as f:
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"PID: {os.getpid()}\n")
                f.write(f"Instance: {instance_id}\n")
        except Exception:
            pass
    
    return any(results)  # 少なくとも1つ成功すればOK

def keepalive_loop(interval=20):
    """メインのキープアライブループ（クロスプラットフォーム対応版、nohup最適化）"""
    global keep_running
    
    cycle_count = 0
    start_time = time.time()
    short_interval = max(5, interval // 4)  # より短い間隔（最低5秒）
    
    # nohup環境ではより短い間隔を使用
    if RUNNING_WITH_NOHUP:
        short_interval = max(3, interval // 6)  # より短い間隔（最低3秒）
    
    msg = f"キープアライブスレッド[ID:{instance_id}]を開始しました（クロスプラットフォーム対応版, nohup={RUNNING_WITH_NOHUP}）"
    logger.info(msg)
    print(msg)
    
    # 開始直後にアクティビティを実行
    try:
        run_keepalive_cycle()
        logger.info("初期キープアライブアクティビティを実行しました")
    except Exception as e:
        logger.error(f"初期キープアライブエラー: {e}")
    
    # メインループ
    restart_loop = 0  # 復帰用ループカウンタ
    while keep_running and not stop_event.is_set():
        try:
            # 通常のキープアライブアクティビティを実行
            success = run_keepalive_cycle()
            cycle_count += 1
            
            # 5サイクルごとにステータスを出力
            if cycle_count % 5 == 0:
                uptime = time.time() - start_time
                minutes, seconds = divmod(int(uptime), 60)
                hours, minutes = divmod(minutes, 60)
                
                msg = f"キープアライブ状態[ID:{instance_id}]: サイクル {cycle_count}, 稼働時間: {hours}時間{minutes}分{seconds}秒, nohup={RUNNING_WITH_NOHUP}"
                logger.info(msg)
                print(msg)
                
                # ハートビートファイルも更新
                update_heartbeat_file()
            
            # nohup環境では、より短い間隔でアクティビティを実行
            if RUNNING_WITH_NOHUP and cycle_count % 3 == 0:
                # 3サイクルごとに追加のファイル活動
                generate_file_activity()
                
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
                # nohup環境では複数の短い間隔に分割
                if RUNNING_WITH_NOHUP:
                    segments = min(4, max(1, remaining_time // 5))  # 最大4分割、最低5秒
                    segment_time = remaining_time / segments
                    
                    for i in range(segments):
                        if not keep_running or stop_event.is_set():
                            break
                        time.sleep(segment_time)
                        
                        # 分割の間にもアクティビティを実行（ファイルのみ）
                        if i % 2 == 0:  # 2区間ごとに1回
                            try:
                                update_heartbeat_file()
                            except Exception:
                                pass
                else:
                    # 通常環境ではそのまま待機
                    time.sleep(remaining_time)
                
            # エラーからの復帰カウンタをリセット
            restart_loop = 0
                
        except Exception as e:
            # エラーが発生しても続行
            restart_loop += 1
            logger.error(f"キープアライブエラー (試行 {restart_loop}): {e}")
            
            # nohup環境では即時再開を試みる
            if RUNNING_WITH_NOHUP:
                # より短い待機時間でリトライ
                wait_time = 1 if restart_loop < 3 else 2
                logger.info(f"{wait_time}秒後に再開を試みます...")
                time.sleep(wait_time)
            else:
                # 通常環境ではより長い待機時間
                time.sleep(2)  
    
    msg = "キープアライブループを終了します"
    logger.info(msg)
    print(msg)

# シグナルハンドラ
def handle_signal(signum, frame):
    """シグナルハンドラ - 終了プロセスを制御"""
    global keep_running
    
    signals = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM"
    }
    
    # Windowsではない場合はSIGHUPも追加
    if not IS_WINDOWS and hasattr(signal, 'SIGHUP'):
        signals[signal.SIGHUP] = "SIGHUP"
    
    sig_name = signals.get(signum, f"Signal {signum}")
    
    # nohup環境ではSIGHUPを無視
    if sig_name == "SIGHUP" and RUNNING_WITH_NOHUP:
        logger.info("nohup環境でSIGHUP信号を受信しましたが、無視します")
        print("nohup環境でSIGHUP信号を受信しましたが、無視します")
        return
    
    logger.warning(f"{sig_name} シグナルを受信しました - 終了を準備します")
    print(f"{sig_name} シグナルを受信しました - 終了を準備します")
    
    # SIGTERMとSIGINTは常に処理
    if signum in [signal.SIGTERM, signal.SIGINT]:
        logger.info(f"{sig_name}を受信 - 通常終了を実行します")
        keep_running = False
        stop_event.set()
    
    # デバッグ用：シグナル処理の状態を記録
    try:
        with open(os.path.join(TMP_DIR, "keepalive_signal.log"), "a") as f:
            f.write(f"{datetime.now().isoformat()} - Received {sig_name}, nohup={RUNNING_WITH_NOHUP}\n")
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
        
        # nohup環境ではSIGHUPを無視
        if not IS_WINDOWS and hasattr(signal, 'SIGHUP'):
            if RUNNING_WITH_NOHUP:
                # nohup環境ではSIGHUPを無視
                signal.signal(signal.SIGHUP, signal.SIG_IGN)
                logger.info("nohup環境を検出: SIGHUPシグナルを無視するように設定しました")
            else:
                # 通常環境ではSIGHUPを処理
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
    
    logger.info(f"キープアライブスレッドを開始しました (間隔: {interval}秒, ID: {instance_id}, nohup={RUNNING_WITH_NOHUP})")
    return keepalive_thread

def stop_keepalive():
    """キープアライブ機能を停止"""
    global keep_running
    
    logger.info("キープアライブスレッドの停止を要求しました")
    keep_running = False
    stop_event.set()
    
    # ファイナライズ状態を記録
    try:
        with open(os.path.join(TMP_DIR, "keepalive_shutdown.log"), "a") as f:
            f.write(f"{datetime.now().isoformat()} - Shutdown requested (nohup={RUNNING_WITH_NOHUP})\n")
    except Exception:
        pass
    
    return True

# __main__パート部分の修正
if __name__ == "__main__":
    try:
        print("==== 改良版キープアライブモジュールのテスト実行 ====")
        print(f"インスタンスID: {instance_id}")
        print(f"実行環境: {platform.system()} {platform.release()}")
        print(f"nohup検出: {RUNNING_WITH_NOHUP}")
        print(f"一時ファイル保存先: {TMP_DIR}")
        
        # コマンドライン引数の解析
        import argparse
        parser = argparse.ArgumentParser(description="キープアライブモジュールのテスト実行")
        parser.add_argument("--interval", type=int, default=30, help="アクティビティ間隔（秒）")
        parser.add_argument("--port", type=int, default=8080, help="HTTPサーバーのポート")
        parser.add_argument("--no-signals", action="store_true", help="シグナルハンドリングを無効化")
        parser.add_argument("--force-nohup", action="store_true", help="nohup環境と見なして実行")
        args = parser.parse_args()
        
        # nohup環境の強制設定
        if args.force_nohup:
            # globalではなく直接変数に代入
            RUNNING_WITH_NOHUP = True
            print("nohup環境を強制的に有効化しました")
        
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