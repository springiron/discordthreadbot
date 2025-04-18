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
    
    async def add_thread_log(self, thread_id: str, username: str, fixed_value: str, status: str = "作成") -> bool:
        """
        スレッドログを非同期で追加
        
        Args:
            thread_id: スレッドID
            username: ユーザー名
            fixed_value: 固定値
            status: 状態（作成/締め切りなど）
            
        Returns:
            bool: 成功時はTrue
        """
        # ロックを取得して同時書き込みを防止
        async with self._lock:
            try:
                # まだ接続していない場合は接続
                if self.agcm is None:
                    if not await self.connect():
                        return False
                
                # 現在時刻を取得
                jst = timezone(timedelta(hours=9))
                now = datetime.now(jst).strftime('%Y/%m/%d %H:%M:%S')
                
                # 行データを作成
                row_data = [str(thread_id), username, now, status, fixed_value]
                
                # *** ここが重要: イベントループ取得と例外処理 ***
                try:
                    # 現在実行中のイベントループを取得
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    # ループが閉じられている場合は新しいループを作成
                    logger.warning("イベントループが閉じられています。新しいループを作成します")
                    current_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(current_loop)
                    
                # 非同期でスプレッドシートに追加
                agc = await self.agcm.authorize()
                spreadsheet = await agc.open_by_key(self.spreadsheet_id)
                worksheet = await spreadsheet.worksheet(self.sheet_name)
                
                # 行の追加（同期的に実行）
                # 現在のイベントループでrun_in_executorを使用
                await current_loop.run_in_executor(
                    thread_executor,
                    functools.partial(
                        self._append_row_sync,
                        worksheet=worksheet,
                        row_data=row_data
                    )
                )
                
                logger.info(f"スレッドログを記録しました: ID={thread_id}, ユーザー={username}, 状態={status}")
                self._reconnect_attempts = 0
                return True
                
            except Exception as e:
                logger.error(f"スレッドログ記録エラー: {e}")
                
                # 認証エラーの場合は再接続を試みる
                error_str = str(e).lower()
                if ("invalid_grant" in error_str or 
                    "token expired" in error_str or 
                    "credentials" in error_str or
                    "different loop" in error_str):
                    
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts <= self._max_reconnect_attempts:
                        logger.info(f"トークンの有効期限切れまたはループエラー。再接続を試みます... (試行 {self._reconnect_attempts}/{self._max_reconnect_attempts})")
                        self.agcm = None
                        
                        # 少し待機してから再接続
                        await asyncio.sleep(1)
                        
                        try:
                            if await self.connect():
                                # 再接続成功したら再度追加を試みる
                                return await self.add_thread_log(thread_id, username, status)
                        except Exception as reconnect_error:
                            logger.error(f"再接続エラー: {reconnect_error}")
                    else:
                        logger.error(f"最大再試行回数を超えました。スプレッドシートログの記録を停止します。")
                
                return False

    def _append_row_sync(self, worksheet, row_data):
        """
        同期的に行を追加する内部メソッド（executor用）
        """
        try:
            # 非同期メソッドではなく、同期的なgspreadのメソッドを使用
            # gspread.worksheetのメソッドを使う必要があります（非asyncio版）
            # GspreadClientManagerのget_clientメソッドを使うか、
            # または別の方法で同期的にワークシートを取得して操作する
            
            # 例えば:
            creds = get_creds(self.credentials_file)
            gc = gspread.authorize(creds)
            spreadsheet = gc.open_by_key(self.spreadsheet_id)
            wks = spreadsheet.worksheet(self.sheet_name)
            wks.append_row(row_data)
            return True
        except Exception as e:
            logger.error(f"行追加エラー: {e}")
            raise