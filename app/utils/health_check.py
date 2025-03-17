#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ヘルスチェック用のシンプルなHTTPサーバーを提供するモジュール
Koyebなどのクラウドプラットフォームでのヘルスチェックに対応する
"""

import threading
import http.server
import socketserver
from typing import Optional
import os

from utils.logger import setup_logger

logger = setup_logger(__name__)

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    """ヘルスチェック用のHTTPリクエストハンドラ"""
    
    def do_GET(self):
        """GETリクエストを処理してステータス200を返す"""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')
    
    def log_message(self, format, *args):
        """アクセスログを標準出力に表示しない（過剰なログを防ぐ）"""
        return


class HealthCheckServer:
    """ヘルスチェック用のHTTPサーバーを管理するクラス"""
    
    def __init__(self, port: int = 8080):
        """
        初期化
        
        Args:
            port: HTTPサーバーが使用するポート番号
        """
        self.port = int(os.getenv("PORT", port))  # 環境変数PORTがあればそれを使用
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
    
    def _run_server(self):
        """HTTPサーバーを実行"""
        handler = HealthCheckHandler
        
        # 'Address already in use' エラーを回避するためのオプション
        socketserver.TCPServer.allow_reuse_address = True
        
        try:
            self.server = socketserver.TCPServer(("", self.port), handler)
            logger.info(f"ヘルスチェックサーバーを開始しました (ポート: {self.port})")
            self.is_running = True
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"ヘルスチェックサーバーの起動中にエラーが発生しました: {e}")
            self.is_running = False
    
    def start(self):
        """ヘルスチェックサーバーをバックグラウンドスレッドで開始"""
        if not self.is_running:
            logger.info(f"ヘルスチェックサーバーを開始しています (ポート: {self.port})...")
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()
    
    def stop(self):
        """ヘルスチェックサーバーを停止"""
        if self.is_running and self.server:
            logger.info("ヘルスチェックサーバーを停止しています...")
            self.server.shutdown()
            self.server.server_close()
            if self.thread:
                self.thread.join(timeout=5.0)  # 最大5秒待機
            self.is_running = False
            logger.info("ヘルスチェックサーバーを停止しました")