#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
キープアライブ機能を提供するモジュール
定期的にアクティビティを発生させてサーバーのスリープを防止する
"""

import asyncio
import threading
import time
from typing import Optional
import random

from utils.logger import setup_logger

logger = setup_logger(__name__)

class KeepAlive:
    """
    サーバーがスリープしないようにキープアライブ信号を送るクラス
    """
    
    def __init__(self, interval_minutes: int = 30):
        """
        初期化
        
        Args:
            interval_minutes: キープアライブ信号を送る間隔（分）
        """
        self.interval_minutes = interval_minutes
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.counter = 0
        self.random_id = random.randint(1000, 9999)  # ユニークなIDを生成
        
    def _keep_alive_task(self):
        """
        キープアライブタスク
        定期的にログを出力してサーバーをアクティブに保つ
        """
        logger.info(f"キープアライブスレッド [ID:{self.random_id}] を開始しました (間隔: {self.interval_minutes}分)")
        
        while not self.stop_event.is_set():
            self.counter += 1
            logger.info(f"キープアライブ信号 #{self.counter} [ID:{self.random_id}] - サーバーをアクティブに保っています")
            
            # 指定された間隔（分）をセカンドに変換
            sleep_interval = self.interval_minutes * 60
            
            # 一度に長時間スリープすると、プログラムの終了時に
            # スレッドがすぐに終了できない可能性があるため、
            # 1分単位で分割してチェックする
            for _ in range(sleep_interval // 60):
                if self.stop_event.is_set():
                    break
                time.sleep(60)
                
            # 残りの秒数をスリープ
            remaining_seconds = sleep_interval % 60
            if remaining_seconds > 0 and not self.stop_event.is_set():
                time.sleep(remaining_seconds)
    
    def start(self):
        """
        キープアライブスレッドを開始する
        """
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._keep_alive_task, daemon=True)
            self.thread.start()
            logger.info("キープアライブ機能を開始しました")
    
    def stop(self):
        """
        キープアライブスレッドを停止する
        """
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=5.0)  # 最大5秒待機
            logger.info("キープアライブ機能を停止しました")