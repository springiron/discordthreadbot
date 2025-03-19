#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
improved_http_server.py - Koyeb対応HTTPサーバー
スリープ防止とヘルスチェック用の最適化されたHTTPサーバー
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime
import signal
import json

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('http_server')

# グローバル変数
server_start_time = datetime.now()
instance_id = os.environ.get('INSTANCE_ID', 'unknown')
heartbeat_file = '/tmp/server_heartbeat.txt'
request_count = 0
keep_running = True

# FastAPIのインポートを試行
try:
    from fastapi import FastAPI, Response
    import uvicorn
    from pydantic import BaseModel

    # FastAPIアプリの作成
    app = FastAPI(title="Discord Bot Server")

    # ルートエンドポイント - 単純なヘルスチェック
    @app.get("/")
    async def root():
        """基本的なヘルスチェックエンドポイント"""
        global request_count
        request_count += 1
        
        # ハートビート更新
        update_heartbeat()
        
        return {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "instance_id": instance_id,
            "request_count": request_count
        }

    # 詳細なヘルスチェックエンドポイント
    @app.get("/health")
    async def health():
        """詳細なヘルスチェックエンドポイント"""
        global request_count
        request_count += 1
        
        # システム情報を取得
        uptime = datetime.now() - server_start_time
        memory_info = get_memory_info()
        
        # ハートビート更新
        update_heartbeat()
        
        return {
            "status": "healthy",
            "uptime": {
                "days": uptime.days,
                "hours": uptime.seconds // 3600,
                "minutes": (uptime.seconds % 3600) // 60,
                "seconds": uptime.seconds % 60,
                "total_seconds": uptime.total_seconds()
            },
            "memory": memory_info,
            "instance_id": instance_id,
            "request_count": request_count,
            "heartbeat": get_last_heartbeat()
        }

    # ポート取得関数
    def get_port():
        """環境変数からポート番号を取得するか、デフォルト値を使用"""
        try:
            return int(os.environ.get("PORT", 8080))
        except (TypeError, ValueError):
            return 8080

    # メモリ情報取得
    def get_memory_info():
        """利用可能なメモリ情報を取得"""
        try:
            import psutil
            vm = psutil.virtual_memory()
            return {
                "total": vm.total,
                "available": vm.available,
                "used": vm.used,
                "percent": vm.percent
            }
        except ImportError:
            return {"status": "psutil not available"}
        except Exception as e:
            return {"error": str(e)}

    # ハートビート更新
    def update_heartbeat():
        """ハートビートファイルを更新"""
        try:
            with open(heartbeat_file, "w") as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logger.error(f"ハートビート更新エラー: {e}")

    # 最終ハートビート取得
    def get_last_heartbeat():
        """最終ハートビート時間を取得"""
        try:
            if os.path.exists(heartbeat_file):
                with open(heartbeat_file, "r") as f:
                    return f.read().strip()
            return "No heartbeat recorded"
        except Exception as e:
            return f"Error reading heartbeat: {e}"

    # UvicornサーバーのUNIXシグナルハンドラ設定
    class UvicornServer(uvicorn.Server):
        """カスタムUvicornサーバー - グレースフルシャットダウン対応"""
        
        def handle_exit(self, sig, frame):
            """終了シグナルハンドラ"""
            logger.info(f"Received exit signal {sig}")
            # 状態を保存
            try:
                with open("/tmp/server_shutdown.json", "w") as f:
                    json.dump({
                        "time": datetime.now().isoformat(),
                        "signal": sig,
                        "request_count": request_count
                    }, f)
            except Exception as e:
                logger.error(f"終了状態保存エラー: {e}")
                
            # UVicornのデフォルト処理を実行
            super().handle_exit(sig, frame)

    # サーバー起動関数
    def start_server(port=None):
        """UVicornサーバーを起動"""
        if port is None:
            port = get_port()
            
        logger.info(f"HTTPサーバーを起動します (ポート: {port})")
        
        # Koyeb向け: 環境変数ログ
        env_vars = {k: v for k, v in os.environ.items() if k.startswith(('PORT', 'KOYEB', 'DISCORD', 'BOT'))}
        logger.info(f"環境変数: {env_vars}")
        
        # UVicornの設定
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_level="warning"
        )
        
        # UVicornサーバーの起動
        server = UvicornServer(config=config)
        try:
            server.run()
        except Exception as e:
            logger.error(f"サーバー実行エラー: {e}")
        
    # サーバースレッド関数
    def server_thread(port=None):
        """サーバーをバックグラウンドスレッドで起動"""
        thread = threading.Thread(
            target=start_server,
            args=(port,),
            daemon=True,
            name="http_server"
        )
        thread.start()
        return thread

except ImportError:
    logger.warning("FastAPI/uvicornがインストールされていないため、HTTPサーバーは無効です")
    
    def server_thread(port=None):
        """HTTPサーバーが利用できない場合のダミー関数"""
        logger.warning("HTTPサーバーは利用できません")
        return None

# 単体実行時のメイン処理
if __name__ == "__main__":
    # シグナルハンドラの設定
    def handle_signal(sig, frame):
        """シグナルハンドラ - 終了処理"""
        global keep_running
        logger.info(f"シグナル {sig} を受信しました。終了します...")
        keep_running = False
        
    # SIGTERMとSIGINTのハンドラを設定
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    try:
        # サーバーを直接実行（非デーモンスレッド）
        logger.info("HTTPサーバーをフォアグラウンドで起動します")
        start_server()
    except KeyboardInterrupt:
        logger.info("キーボード割り込みにより終了します")
    except Exception as e:
        logger.error(f"サーバー実行中にエラーが発生しました: {e}")
    finally:
        logger.info("HTTPサーバーを終了します")