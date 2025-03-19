#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スレッド生成と管理のロジック
"""

import discord
from typing import List, Optional

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
    
    # デバッグ情報を追加
    logger.debug(f"トリガーキーワードチェック: {trigger_keywords}")
    
    # メッセージ内容にトリガーキーワードが含まれるかチェック
    for keyword in trigger_keywords:
        if keyword in message.content:
            logger.debug(f"キーワード '{keyword}' が見つかりました: {message.content[:30]}...")
            return True
    
    logger.debug(f"いずれのキーワードも見つかりませんでした: {message.content[:30]}...")
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
        # スレッドを作成
        logger.info(f"スレッド作成開始: メッセージID={message.id}, チャンネルID={message.channel.id}")
        thread = await message.create_thread(
            name=name,
            auto_archive_duration=auto_archive_duration
        )
        
        logger.info(f"メッセージID {message.id} からスレッド '{thread.name}' (ID: {thread.id}) を作成しました")
        return thread
        
    except discord.Forbidden:
        logger.error(f"スレッド作成に必要な権限がありません: チャンネルID={message.channel.id}")
    except discord.HTTPException as e:
        logger.error(f"スレッド作成中にHTTPエラーが発生しました: {e}, チャンネルID={message.channel.id}")
    except Exception as e:
        logger.error(f"スレッド作成中に予期しないエラーが発生しました: {e}, チャンネルID={message.channel.id}")
    
    return None