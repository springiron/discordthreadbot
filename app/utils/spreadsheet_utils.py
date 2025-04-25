#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スプレッドシート操作ユーティリティ - 非同期処理対応版
(イベントループ問題修正版)
"""

import os
import asyncio
import gspread
import gspread_asyncio
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import random
import traceback
import time
import functools
from concurrent.futures import ThreadPoolExecutor

from utils.logger import setup_logger

logger = setup_logger(__name__)

# グローバル非同期処理用のエグゼキューター
thread_executor = ThreadPoolExecutor(max_workers=2)

def get_creds(credentials_file_path: str):
    """
    サービスアカウント認証情報を取得する関数
    
    Args:
        credentials_file_path: 認証情報JSONファイルのパス
        
    Returns:
        Credentials: 認証情報オブジェクト
    """
    # 認証情報ファイルのパスを解決
    creds_path = os.path.abspath(credentials_file_path)
    if not os.path.exists(creds_path):
        logger.error(f"認証情報ファイルが見つかりません: {creds_path}")
        return None
        
    # 認証スコープ
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    return Credentials.from_service_account_file(creds_path, scopes=scopes)

class AsyncSpreadsheetClient:
    """Googleスプレッドシートとの非同期連携を行うクライアント"""
    
    def __init__(self, credentials_file: str, spreadsheet_id: str, sheet_name: str):
        """
        初期化
        
        Args:
            credentials_file: 認証情報JSONファイルのパス
            spreadsheet_id: スプレッドシートID
            sheet_name: シート名
        """
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.agcm = None  # 非同期クライアントマネージャー
        self._headers = ["ユーザID", "ユーザー名", "ログ記載時間", "種別", "VC接続開始時間", "VC接続終了時間"]
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._lock = asyncio.Lock()  # 同時書き込み防止用ロック
        
    async def connect(self) -> bool:
        """
        スプレッドシートに非同期で接続
        
        Returns:
            bool: 接続成功時はTrue
        """
        try:
            # 既に初期化済みの場合は再利用
            if self.agcm is not None:
                return True
                
            # 非同期クライアントマネージャーの作成
            self.agcm = gspread_asyncio.AsyncioGspreadClientManager(
                lambda: get_creds(self.credentials_file)
            )
            
            # 接続テスト
            agc = await self.agcm.authorize()
            spreadsheet = await agc.open_by_key(self.spreadsheet_id)
            
            # シートの存在を確認し、必要なら作成
            try:
                worksheet = await spreadsheet.worksheet(self.sheet_name)
                # ヘッダー行を確認し、必要なら追加
                values = await worksheet.get_values("A1:F1")
                if not values or values[0] != self._headers:
                    await worksheet.update("A1:E1", [self._headers])
                    logger.info(f"シート '{self.sheet_name}' のヘッダーを設定しました")
                
                logger.info(f"シート '{self.sheet_name}' に接続しました")
            except gspread.exceptions.WorksheetNotFound:
                # シートが存在しない場合は作成（非同期関数でラップ）
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    thread_executor,
                    functools.partial(
                        self._create_worksheet_sync,
                        spreadsheet_id=self.spreadsheet_id,
                        sheet_name=self.sheet_name
                    )
                )
                logger.info(f"シート '{self.sheet_name}' を新規作成しました")
            
            self._reconnect_attempts = 0
            return True
            
        except Exception as e:
            logger.error(f"スプレッドシート接続エラー: {e}")
            return False
    
    def _create_worksheet_sync(self, spreadsheet_id, sheet_name):
        """
        同期的にワークシートを作成する内部メソッド（executor用）
        """
        try:
            creds = get_creds(self.credentials_file)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=10
            )
            # ヘッダー行を追加
            worksheet.append_row(self._headers)
            return worksheet
        except Exception as e:
            logger.error(f"ワークシート作成エラー: {e}")
            raise
    
    async def add_thread_log(self, user_id: str, username: str, fixed_value: str, status: str = "作成") -> bool:
        """
        スレッドログを非同期で追加（改善版）
        
        Args:
            user_id: ユーザーID
            username: ユーザー名
            fixed_value: 固定値
            status: 状態（作成/締め切りなど）
                
        Returns:
            bool: 成功時はTrue
        """
        # ロックを取得して同時書き込みを防止
        start_time = time.time()
        logger.debug(f"add_thread_log開始: ID={user_id}, ユーザー={username}, 状態={status}")
        
        try:
            # 現在のイベントループを取得（または作成）
            try:
                current_loop = asyncio.get_running_loop()
                if current_loop.is_closed():
                    logger.warning("現在のイベントループが閉じられています")
                    return False
            except RuntimeError:
                logger.warning("実行中のイベントループがありません")
                return False
            
            # まだ接続していない場合は接続
            if self.agcm is None:
                connection_result = await self.connect()
                if not connection_result:
                    logger.error("スプレッドシートへの接続に失敗しました")
                    return False
            
            # 認証
            agc = await self.agcm.authorize()
            
            # スプレッドシート・ワークシート取得
            spreadsheet = await agc.open_by_key(self.spreadsheet_id)
            worksheet = await spreadsheet.worksheet(self.sheet_name)
            
            # 現在時刻を取得
            jst = timezone(timedelta(hours=9))
            now = datetime.now(jst).strftime('%Y/%m/%d %H:%M:%S')
            
            # 行データを作成
            row_data = [str(user_id), username, now, status, fixed_value]
            
            # 同期操作を実行するためのexecutorを使用
            await current_loop.run_in_executor(
                thread_executor,
                functools.partial(
                    self._append_row_sync,
                    spreadsheet_id=self.spreadsheet_id,
                    sheet_name=self.sheet_name,
                    row_data=row_data
                )
            )
            
            elapsed = time.time() - start_time
            logger.info(f"スレッドログを記録しました: ユーザーID={user_id}, ユーザー={username}, 状態={status} (所要時間: {elapsed:.2f}秒)")
            return True
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"スレッドログ記録中の予期しないエラー ({elapsed:.2f}秒経過): {e}")
            logger.debug(f"スタックトレース:\n{traceback.format_exc()}")
            return False

    def _append_row_sync(self, spreadsheet_id, sheet_name, row_data):
        """
        同期的に行を追加する内部メソッド（executor用）
        
        重要な変更: worksheet引数の代わりにspreadsheet_idとsheet_nameを受け取る
        新しい接続を毎回作成する
        """
        try:
            # 常に新しい接続を作成
            creds = get_creds(self.credentials_file)
            gc = gspread.authorize(creds)
            spreadsheet = gc.open_by_key(spreadsheet_id)
            wks = spreadsheet.worksheet(sheet_name)
            wks.append_row(row_data)
            return True
        except Exception as e:
            logger.error(f"行追加エラー: {e}")
            raise