#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スレッド生成と管理のロジック
"""

import discord
from typing import List, Optional
import re

from utils.logger import setup_logger

logger = setup_logger(__name__)

def should_create_thread(message: discord.Message, trigger_keywords: List[str]) -> bool:
    """
    メッセージがスレッド作成条件を満たすかチェック
    
    Args:
        message: チェック対象のDiscordメッセージ
        trigger_keywords: トリガーとなるキーワードのリスト
        
    Returns:
        bool: スレッドを作成すべき場合はTrue
    """
    # メッセージ内容が空の場合は無視
    if not message.content:
        return False
    
    # @[数値]パターンのチェック（例: @1, @123, ＠１, ＠１２３など、半角・全角両対応）
    at_number_pattern = re.compile(r'[@＠][0-9０-９]+')
    if at_number_pattern.search(message.content):
        return True
    
    # メッセージ内容にトリガーキーワードが含まれるかチェック
    for keyword in trigger_keywords:
        # 大文字小文字を区別せずにキーワードを検索
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        if pattern.search(message.content):
            return True
    
    return False

async def create_thread_from_message(
    message: discord.Message, 
    name: str, 
    auto_archive_duration: int = 10080
) -> Optional[discord.Thread]:
    """
    メッセージからスレッドを作成
    
    Args:
        message: スレッド作成元のDiscordメッセージ
        name: スレッド名
        auto_archive_duration: 自動アーカイブ時間（分）
        
    Returns:
        Optional[discord.Thread]: 作成されたスレッド。失敗した場合はNone
    """
    try:
        # スレッド作成を試みる
        thread = await message.create_thread(
            name=name,
            auto_archive_duration=auto_archive_duration
        )
        
        logger.info(f"スレッド '{name}' を作成しました (ID: {thread.id})")
        return thread
        
    except discord.Forbidden:
        logger.error(f"スレッド作成に必要な権限がありません: チャンネル={message.channel.name}")
        
    except discord.HTTPException as e:
        logger.error(f"スレッド作成中にHTTPエラーが発生しました: {e.status}/{e.code}")
        
    except Exception as e:
        logger.error(f"スレッド作成中にエラーが発生しました: {e}")
    
    return None