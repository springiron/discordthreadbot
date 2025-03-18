#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
統一されたキープアライブとヘルスチェック機能

このモジュールは以下の機能を提供します：
1. FastAPIベースのヘルスチェックサーバー
2. Koyebなどのプラットフォームでのスリープ防止機能
3. スレッドの統合的な管理
"""

import threading
import time
import logging
import os
import sys
from typing import Dict, Any, Optional, List, Tuple
import json
import random
from threading import Thread, Event

# Web関連のインポート
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import requests

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("system.keepalive")

# FastAPIアプリケーションの作成
app = FastAPI(title="Bot Health API", version="1.0.0")

# スレッド停止用イベント
stop_event = threading.Event()

# 起動時間の記録
start_time = time.time()

# アプリケーション状態の追跡
app_state = {
    "status": "initializing",
    "start_time": start_time,
    "last_activity": start_time,
    "keepalive_count": 0,
    "errors": [],
    "version": "1.0.0"
}

@app.get("/")
async def root():
    """
    基本的なヘルスチェックエンドポイント
    """
    return {"status": "ok", "message": "Server is online."}

@app.get("/health")
async def health():
    """
    詳細なヘルスチェックエンドポイント
    システム状態の詳細情報を提供
    """
    uptime = time.time() - start_time
    
    return {
        "status": app_state["status"],
        "uptime_seconds": uptime,
        "uptime_formatted": format_uptime(uptime),
        "last_activity": time.time() - app_state["last_activity"],
        "keepalive_count": app_state["keepalive_count"],
        "version": app_state["version"],
        "errors": app_state["errors"][-5:] if app_state["errors"] else []
    }

@app.get("/metrics")
async def metrics():
    """
    監視用のメトリクスエンドポイント
    """
    memory_usage = get_memory_usage()
    cpu_info = get_cpu_info()
    
    return {
        "memory": memory_usage,
        "cpu": cpu_info,
        "uptime_seconds": time.time() - start_time,
        "status": app_state["status"]
    }

def format_uptime(seconds: float) -> str:
    """
    秒単位の稼働時間を人間が読める形式に変換
    
    Args:
        seconds: 秒単位の稼働時間
        
    Returns:
        str: 人間が読める形式の稼働時間（例: "3日 12時間 5分 2秒"）
    """
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}日")
    if hours > 0 or days > 0:
        parts.append(f"{hours}時間")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}分")
    parts.append(f"{seconds}秒")
    
    return " ".join(parts)

def get_memory_usage() -> Dict[str, Any]:
    """
    現在のメモリ使用状況を取得
    
    Returns:
        Dict[str, Any]: メモリ使用状況の辞書
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "percent": process.memory_percent()
        }
    except ImportError:
        return {"error": "psutilライブラリが利用できません"}
    except Exception as e:
        return {"error": str(e)}

def get_cpu_info() -> Dict[str, Any]:
    """
    現在のCPU使用状況を取得
    
    Returns:
        Dict[str, Any]: CPU使用状況の辞書
    """
    try:
        import psutil
        process = psutil.Process(os.getpid())
        
        return {
            "percent": process.cpu_percent(interval=0.1),
            "system_percent": psutil.cpu_percent(interval=0.1)
        }
    except ImportError:
        return {"error": "psutilライブラリが利用できません"}
    except Exception as e:
        return {"error": str(e)}

def start_server(host: str = "0.0.0.0", port: int = 8080):
    """
    UvicornサーバーでFastAPIアプリを起動
    
    Args:
        host: ホスト名または IP アドレス（デフォルト: "0.0.0.0"）
        port: ポート番号（デフォルト: 8080）
    """
    try:
        # 環境変数PORTがあればそちらを優先
        port = int(os.getenv("PORT", port))
        
        # Uvicornサーバーを起動
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        app_state["status"] = "running"
        
        # サーバーの実行（ブロッキング呼び出し）
        server.run()
    except Exception as e:
        logger.error(f"ヘルスチェックサーバーの起動中にエラーが発生しました: {e}")
        app_state["status"] = "error"
        app_state["errors"].append(f"Server error: {str(e)}")

def keep_alive(interval_seconds: int = 30):
    """
    キープアライブ処理を実行するスレッド関数
    定期的にアクティビティを発生させてインスタンスのスリープを防止
    
    Args:
        interval_seconds: アクティビティ間の間隔（秒）
    """
    # 最終アクティビティ時間を記録（稼働確認に使用）
    last_log_time = 0
    last_file_write = 0
    last_http_request = 0
    last_cpu_activity = 0
    
    # 一意のIDを生成（ログの識別用）
    instance_id = random.randint(1000, 9999)
    logger.info(f"キープアライブスレッド [ID:{instance_id}] を開始しました")
    
    # メインループ
    while not stop_event.is_set():
        try:
            current_time = time.time()
            app_state["last_activity"] = current_time
            app_state["keepalive_count"] += 1
            
            # 15分ごとにログを出力
            if current_time - last_log_time >= 900:  # 900秒 = 15分
                uptime = current_time - start_time
                logger.info(
                    f"キープアライブ信号 #{app_state['keepalive_count']} "
                    f"[ID:{instance_id}] - "
                    f"稼働時間: {format_uptime(uptime)}"
                )
                last_log_time = current_time
            
            # 5分ごとにHTTPリクエストを送信
            if current_time - last_http_request >= 300:  # 300秒 = 5分
                try:
                    # 自身のヘルスエンドポイントにリクエスト
                    response = requests.get("http://localhost:8080/health", timeout=5)
                    if response.status_code == 200:
                        logger.debug("ヘルスチェックリクエスト成功")
                except Exception as e:
                    logger.debug(f"ヘルスチェックリクエスト失敗: {e}")
                last_http_request = current_time
            
            # 10分ごとにファイルシステムに書き込み
            if current_time - last_file_write >= 600:  # 600秒 = 10分
                try:
                    # キープアライブ情報をJSONで書き込み
                    with open("keepalive_status.json", "w") as f:
                        json.dump({
                            "timestamp": current_time,
                            "instance_id": instance_id,
                            "uptime": current_time - start_time,
                            "status": app_state["status"]
                        }, f, indent=2)
                    logger.debug("キープアライブファイル書き込み成功")
                except Exception as e:
                    logger.debug(f"ファイル書き込み失敗: {e}")
                last_file_write = current_time
            
            # 5分ごとに軽いCPU負荷を発生
            if current_time - last_cpu_activity >= 300:  # 300秒 = 5分
                # 軽い計算を実行
                _ = [i * i for i in range(10000)]
                logger.debug("CPU活動生成完了")
                last_cpu_activity = current_time
            
            # インターバル待機
            time.sleep(interval_seconds)
            
        except Exception as e:
            logger.error(f"キープアライブ処理中にエラーが発生しました: {e}")
            app_state["errors"].append(f"Keepalive error: {str(e)}")
            
            # エラー発生時は少し長めに待機
            time.sleep(60)

class SystemMonitor:
    """
    システム監視と管理のための統合クラス
    """
    
    def __init__(self, port: int = 8080, keep_alive_interval: int = 30):
        """
        初期化
        
        Args:
            port: ヘルスチェックサーバーのポート番号
            keep_alive_interval: キープアライブの間隔（秒）
        """
        self.port = port
        self.keep_alive_interval = keep_alive_interval
        self.threads: List[Thread] = []
        self.stop_event = stop_event  # モジュールレベルのイベントを使用
    
    def start(self):
        """
        すべてのモニタリングスレッドを開始
        """
        logger.info("システムモニタリングを開始します")
        
        # ヘルスチェックサーバースレッド
        server_thread = Thread(
            target=start_server,
            args=("0.0.0.0", self.port),
            daemon=True,
            name="health-server"
        )
        server_thread.start()
        self.threads.append(server_thread)
        
        # キープアライブスレッド
        keepalive_thread = Thread(
            target=keep_alive,
            args=(self.keep_alive_interval,),
            daemon=True,
            name="keep-alive"
        )
        keepalive_thread.start()
        self.threads.append(keepalive_thread)
        
        logger.info(f"システムモニタリングを開始しました (ポート: {self.port}, 間隔: {self.keep_alive_interval}秒)")
        return self.threads
    
    def stop(self):
        """
        すべてのモニタリングスレッドを停止
        """
        logger.info("システムモニタリングを停止しています...")
        self.stop_event.set()
        
        # スレッドが終了するのを待機
        for thread in self.threads:
            thread.join(timeout=5.0)
        
        logger.info("システムモニタリングを停止しました")

# モジュールレベルの関数として公開
def start_system_monitor(port: int = 8080, keep_alive_interval: int = 30) -> SystemMonitor:
    """
    システムモニター（ヘルスチェックサーバーとキープアライブ）を開始
    
    Args:
        port: ヘルスチェックサーバーのポート番号
        keep_alive_interval: キープアライブの間隔（秒）
        
    Returns:
        SystemMonitor: 作成されたモニタリングインスタンス
    """
    monitor = SystemMonitor(port=port, keep_alive_interval=keep_alive_interval)
    monitor.start()
    return monitor

def stop_system_monitor(monitor: Optional[SystemMonitor] = None):
    """
    システムモニターを停止
    
    Args:
        monitor: 停止するモニターインスタンス（Noneの場合はグローバルイベントを設定）
    """
    if monitor:
        monitor.stop()
    else:
        # モニターインスタンスが提供されない場合は、グローバルイベントを設定
        stop_event.set()
        logger.info("システムモニタリングの停止信号を送信しました")