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
        
        async with self._lock:
            try:
                # 現在のイベントループ情報をログ記録
                try:
                    current_loop = asyncio.get_running_loop()
                    logger.debug(f"現在のイベントループ: ID={id(current_loop)}, 閉じている={current_loop.is_closed()}")
                except RuntimeError as e:
                    logger.warning(f"イベントループが存在しないか閉じられています: {e}")
                    # この場合は新しいループを作成せず、呼び出し元に処理を委任
                    return False
                
                # まだ接続していない場合は接続
                if self.agcm is None:
                    connection_result = await self.connect()
                    if not connection_result:
                        logger.error("スプレッドシートへの接続に失敗しました")
                        return False
                    logger.debug("スプレッドシートへの接続に成功しました")
                
                # 現在時刻を取得
                jst = timezone(timedelta(hours=9))
                now = datetime.now(jst).strftime('%Y/%m/%d %H:%M:%S')
                
                # 行データを作成
                row_data = [str(user_id), username, now, status, fixed_value]
                
                # 実際の処理を実行
                logger.debug(f"スプレッドシート書き込み開始: ID={user_id}")
                
                # 認証と書き込み処理を分離して、それぞれエラーハンドリングを追加
                try:
                    # 認証部分
                    agc = await self.agcm.authorize()
                    logger.debug("スプレッドシート認証成功")
                    
                    # スプレッドシート・ワークシート取得部分
                    spreadsheet = await agc.open_by_key(self.spreadsheet_id)
                    worksheet = await spreadsheet.worksheet(self.sheet_name)
                    logger.debug(f"ワークシート '{self.sheet_name}' 取得成功")
                    
                    # 現在のループを使って、スレッドセーフな書き込み
                    current_loop = asyncio.get_running_loop()
                    
                    # 実行前にループが有効か確認
                    if current_loop.is_closed():
                        logger.error("書き込み実行前にイベントループが閉じられています")
                        return False
                    
                    # 書き込み処理をexecutorで実行
                    await current_loop.run_in_executor(
                        thread_executor,
                        functools.partial(
                            self._append_row_sync,
                            worksheet=worksheet,
                            row_data=row_data
                        )
                    )
                    
                    elapsed = time.time() - start_time
                    logger.info(f"スレッドログを記録しました: ユーザーID={user_id}, ユーザー={username}, 状態={status} (所要時間: {elapsed:.2f}秒)")
                    self._reconnect_attempts = 0
                    return True
                    
                except gspread.exceptions.APIError as e:
                    # API固有のエラー
                    error_code = getattr(e, 'response', {}).get('status', None)
                    logger.error(f"スプレッドシートAPI例外: コード={error_code}, エラー={e}")
                    
                    if error_code in [403, 429]:  # 権限エラーや制限エラー
                        logger.warning(f"APIレート制限またはアクセス権限の問題が発生しました: {e}")
                    return False
                    
                except (gspread.exceptions.GSpreadException, asyncio.CancelledError, RuntimeError) as e:
                    error_msg = str(e).lower()
                    
                    # イベントループ関連のエラーを詳細に判別
                    if "loop" in error_msg:
                        logger.error(f"イベントループエラー: {e}")
                    elif "token" in error_msg or "credential" in error_msg or "auth" in error_msg:
                        logger.error(f"認証エラー: {e}")
                    else:
                        logger.error(f"スプレッドシート処理エラー: {e}")
                    
                    # 再接続が必要なエラーかどうか判断
                    if ("invalid_grant" in error_msg or 
                        "token expired" in error_msg or 
                        "credentials" in error_msg or
                        "different loop" in error_msg):
                        
                        # 次回の処理で再接続されるようにクライアントをリセット
                        logger.info("認証/接続問題を検出。次回の呼び出しで再接続します")
                        self.agcm = None
                    
                    return False
                    
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"スレッドログ記録中の予期しないエラー ({elapsed:.2f}秒経過): {e}")
                logger.debug(f"スタックトレース:\n{traceback.format_exc()}")
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