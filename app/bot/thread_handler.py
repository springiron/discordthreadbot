#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スレッド生成と管理のロジック - デバッグ出力を強化
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
    # メッセージ内容を取得
    content = message.content
    
    # メッセージ内容が空の場合は無視
    if not content:
        logger.debug(f"メッセージ内容が空のため無視します: メッセージID={message.id}")
        return False
    
    # メッセージ内容のデバッグ出力
    logger.info(f"メッセージ内容: {content}")
    logger.info(f"トリガーキーワード: {trigger_keywords}")
    
    # メッセージ内容にトリガーキーワードが含まれるかチェック
    for keyword in trigger_keywords:
        # 大文字小文字を区別せずにキーワードを検索
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        if pattern.search(content):
            logger.info(f"キーワード '{keyword}' が見つかりました: {content[:100]}...")
            return True
        else:
            logger.debug(f"キーワード '{keyword}' はメッセージ内に見つかりませんでした")
    
    logger.info(f"いずれのキーワードも見つかりませんでした: {content[:100]}...")
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
    logger.info(f"スレッド作成開始: メッセージID={message.id}, チャンネルID={message.channel.id}, チャンネル名={message.channel.name}")
    logger.info(f"スレッド名: {name}, 自動アーカイブ時間: {auto_archive_duration}分")
    
    # チャンネルおよびサーバーの情報をログに出力
    if message.guild:
        logger.info(f"サーバー: {message.guild.name} (ID: {message.guild.id})")
        
        # Botの権限を確認
        permissions = message.channel.permissions_for(message.guild.me)
        logger.info(f"権限 - 読み取り: {permissions.read_messages}, 送信: {permissions.send_messages}, スレッド作成: {permissions.create_public_threads}")
    
    try:
        # スレッド作成を試みる
        logger.info(f"message.create_thread()を呼び出します: {name}, {auto_archive_duration}")
        thread = await message.create_thread(
            name=name,
            auto_archive_duration=auto_archive_duration
        )
        
        logger.info(f"メッセージID {message.id} からスレッド '{thread.name}' (ID: {thread.id}) を作成しました")
        return thread
        
    except discord.Forbidden as e:
        logger.error(f"スレッド作成に必要な権限がありません: {e}")
        
        # 権限の詳細を確認
        if message.guild:
            permissions = message.channel.permissions_for(message.guild.me)
            logger.error(f"Botの権限 - スレッド作成: {permissions.create_public_threads}, メッセージ送信: {permissions.send_messages}")
            logger.error(f"チャンネル設定を確認してください: {message.channel.name} (ID: {message.channel.id})")
    except discord.HTTPException as e:
        logger.error(f"スレッド作成中にHTTPエラーが発生しました: エラーコード={e.code}, ステータス={e.status}")
        logger.error(f"HTTPエラー詳細: {e.text}")
    except Exception as e:
        logger.error(f"スレッド作成中に予期しないエラーが発生しました: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return None