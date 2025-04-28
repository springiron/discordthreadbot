#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スプレッドシート操作ユーティリティ - 同期処理版
(非同期エラー修正版)
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import traceback
import time
import threading

from utils.logger import setup_logger

logger = setup_logger(__name__)

# 同時アクセス制御用のロック
spreadsheet_lock = threading.Lock()

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

class SpreadsheetClient:
    """Googleスプレッドシートとの同期連携を行うクライアント"""
    
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
        self._headers = ["ユーザID", "ユーザー名", "ログ記載時間", "種別", "VC接続開始時間", "VC接続終了時間"]
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._client = None
        
    def connect(self) -> bool:
        """
        スプレッドシートに接続
        
        Returns:
            bool: 接続成功時はTrue
        """
        try:
            # 認証情報を取得
            creds = get_creds(self.credentials_file)
            if creds is None:
                return False
                
            # クライアントを作成
            self._client = gspread.authorize(creds)
            
            # スプレッドシートを開く
            spreadsheet = self._client.open_by_key(self.spreadsheet_id)
            
            # シートの存在を確認し、必要なら作成
            try:
                worksheet = spreadsheet.worksheet(self.sheet_name)
                # ヘッダー行を確認し、必要なら追加
                values = worksheet.get_values("A1:F1")
                if not values or values[0] != self._headers:
                    worksheet.update("A1:F1", [self._headers])
                    logger.info(f"シート '{self.sheet_name}' のヘッダーを設定しました")
                
                logger.info(f"シート '{self.sheet_name}' に接続しました")
            except gspread.exceptions.WorksheetNotFound:
                # シートが存在しない場合は作成
                worksheet = spreadsheet.add_worksheet(
                    title=self.sheet_name,
                    rows=1000,
                    cols=10
                )
                worksheet.append_row(self._headers)
                logger.info(f"シート '{self.sheet_name}' を新規作成しました")
            
            self._reconnect_attempts = 0
            return True
            
        except Exception as e:
            logger.error(f"スプレッドシート接続エラー: {e}")
            return False
    
    def add_thread_log(self, user_id: str, username: str, fixed_value: str = "", status: str = "作成") -> bool:
        """
        スレッドログを追加（同期版）
        
        Args:
            user_id: ユーザーID
            username: ユーザー名
            fixed_value: 固定値
            status: 状態（作成/締め切りなど）
                
        Returns:
            bool: 成功時はTrue
        """
        # ロックを取得して同時書き込みを防止
        with spreadsheet_lock:
            start_time = time.time()
            logger.debug(f"add_thread_log開始: ID={user_id}, ユーザー={username}, 状態={status}")
            
            try:
                # まだ接続していない場合は接続
                if self._client is None:
                    connection_result = self.connect()
                    if not connection_result:
                        logger.error("スプレッドシートへの接続に失敗しました")
                        return False
                
                # スプレッドシート・ワークシート取得
                try:
                    spreadsheet = self._client.open_by_key(self.spreadsheet_id)
                    worksheet = spreadsheet.worksheet(self.sheet_name)
                except Exception as e:
                    # 接続エラーが発生した場合は再接続を試みる
                    logger.warning(f"スプレッドシート接続エラー、再接続を試みます: {e}")
                    if self.connect():
                        spreadsheet = self._client.open_by_key(self.spreadsheet_id)
                        worksheet = spreadsheet.worksheet(self.sheet_name)
                    else:
                        logger.error("スプレッドシートへの再接続に失敗しました")
                        return False
                
                # 現在時刻を取得
                jst = timezone(timedelta(hours=9))
                now = datetime.now(jst).strftime('%Y/%m/%d %H:%M:%S')
                
                # 行データを作成
                row_data = [str(user_id), username, now, status, fixed_value]
                
                # 行を追加
                worksheet.append_row(row_data)
                
                elapsed = time.time() - start_time
                logger.info(f"スレッドログを記録しました: ユーザーID={user_id}, ユーザー={username}, 状態={status} (所要時間: {elapsed:.2f}秒)")
                return True
                
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"スレッドログ記録中の予期しないエラー ({elapsed:.2f}秒経過): {e}")
                logger.debug(f"スタックトレース:\n{traceback.format_exc()}")
                return False
                
    def reconnect(self) -> bool:
        """
        スプレッドシートに再接続を試みる
        
        Returns:
            bool: 再接続成功時はTrue
        """
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"再接続試行回数の上限({self._max_reconnect_attempts}回)に達しました")
            return False
            
        self._reconnect_attempts += 1
        logger.info(f"スプレッドシートへの再接続を試みます (試行 {self._reconnect_attempts}/{self._max_reconnect_attempts})")
        
        try:
            self._client = None  # 既存のクライアントをクリア
            return self.connect()
        except Exception as e:
            logger.error(f"スプレッドシート再接続エラー: {e}")
            return False
    
    def get_all_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        すべてのログを取得
        
        Args:
            limit: 取得する最大行数
            
        Returns:
            List[Dict[str, Any]]: ログのリスト
        """
        try:
            # まだ接続していない場合は接続
            if self._client is None:
                connection_result = self.connect()
                if not connection_result:
                    logger.error("スプレッドシートへの接続に失敗しました")
                    return []
            
            # スプレッドシート・ワークシート取得
            try:
                spreadsheet = self._client.open_by_key(self.spreadsheet_id)
                worksheet = spreadsheet.worksheet(self.sheet_name)
            except Exception as e:
                logger.warning(f"スプレッドシート接続エラー、再接続を試みます: {e}")
                if self.reconnect():
                    spreadsheet = self._client.open_by_key(self.spreadsheet_id)
                    worksheet = spreadsheet.worksheet(self.sheet_name)
                else:
                    logger.error("スプレッドシートへの再接続に失敗しました")
                    return []
            
            # すべての値を取得
            all_values = worksheet.get_all_values()
            
            # ヘッダー行と残りのデータに分割
            headers = all_values[0] if all_values else []
            data = all_values[1:] if len(all_values) > 1 else []
            
            # 辞書のリストに変換
            result = []
            for row in data[:limit]:
                # ヘッダーと値を辞書にマッピング
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header] = row[i]
                    else:
                        row_dict[header] = ""
                result.append(row_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"ログ取得エラー: {e}")
            return []