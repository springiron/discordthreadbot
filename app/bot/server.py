import threading
import time
import logging
from threading import Thread
import requests
from fastapi import FastAPI
import uvicorn

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('koyeb_server')

# FastAPIアプリケーションの作成
app = FastAPI()

# スレッド停止用イベント
stop_event = threading.Event()

@app.get("/")
async def root():
    """ヘルスチェックエンドポイント"""
    return {"message": "Server is Online.", "timestamp": time.time()}

@app.get("/health")
async def health():
    """詳細なヘルスチェックエンドポイント"""
    return {
        "status": "running", 
        "uptime": time.time(),
        "version": "1.0.0"
    }

def start_server():
    """UvicornサーバーをFastAPIアプリで起動する関数"""
    uvicorn.run(app, host="0.0.0.0", port=8080)

def keep_alive():
    """
    Koyebインスタンスがスリープしないようにキープアライブ信号を送信するスレッド関数
    """
    minutes = 0
    while not stop_event.is_set():
        try:
            # 定期的なログ出力
            if minutes % 15 == 0:  # 15分ごと
                logger.info(f"Keepalive: {minutes} minutes elapsed - Koyeb instance active")
            
            # HTTPサーバーにリクエストを送信
            if minutes % 5 == 0:  # 5分ごと
                requests.get("http://localhost:8080/health", timeout=5)
                logger.info("Keepalive: Health check request sent")
                
            # ファイルシステムに書き込み
            if minutes % 10 == 0:  # 10分ごと
                with open("keepalive.txt", "w") as f:
                    f.write(f"Keepalive timestamp: {time.time()}")
                logger.info("Keepalive: Wrote to filesystem")
                
            # CPU負荷を少し発生
            if minutes % 5 == 0:  # 5分ごと
                _ = [i * i for i in range(10000)]  # 簡単な計算
                logger.info("Keepalive: Generated CPU activity")
            
            # 30秒待機
            time.sleep(30)
            minutes += 0.5
            
        except Exception as e:
            logger.error(f"Keepalive error: {e}")
            time.sleep(60)  # エラー時は1分待機

def server_thread():
    """
    サーバーとキープアライブスレッドを起動する関数
    """
    # サーバースレッド起動
    server_t = Thread(target=start_server, daemon=True)
    server_t.start()
    logger.info("Server thread started")
    
    # キープアライブスレッド起動
    keepalive_t = Thread(target=keep_alive, daemon=True)
    keepalive_t.start()
    logger.info("Keepalive thread started")
    
    return server_t, keepalive_t

# スレッド停止関数（終了時に呼び出す）
def stop_threads():
    """すべてのスレッドを停止するための関数"""
    stop_event.set()
    logger.info("Stopping all threads...")
    time.sleep(2)  # スレッドが終了するのを少し待つ