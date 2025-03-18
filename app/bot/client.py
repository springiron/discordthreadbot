#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Botクライアント実装
"""

import discord
from discord.ext import commands
import asyncio
from typing import Optional, List, Union

from config import BOT_CONFIG, TRIGGER_KEYWORDS, THREAD_AUTO_ARCHIVE_DURATION, THREAD_NAME_TEMPLATE, ENABLED_CHANNEL_IDS
from bot.thread_handler import should_create_thread, create_thread_from_message
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ThreadBot(commands.Bot):
    """
    スレッド自動生成Bot
    """
    
    def __init__(self):
        """
        Botの初期化
        """
        # Botの意図を設定
        intents = discord.Intents.default()
        intents.message_content = BOT_CONFIG.BOT_INTENTS["message_content"] 
        intents.guilds = BOT_CONFIG.BOT_INTENTS["guilds"]
        intents.guild_messages = BOT_CONFIG.BOT_INTENTS["guild_messages"]
        
        # Botを初期化
        super().__init__(command_prefix="!", intents=intents)
        logger.info("ThreadBotを初期化しました")
        
    async def on_ready(self):
        """
        Bot準備完了時のイベントハンドラ
        """
        logger.info(f"{self.user.name} としてログインしました (ID: {self.user.id})")
        
        # 有効なチャンネルの情報をログに記録
        if ENABLED_CHANNEL_IDS:
            channel_count = len(ENABLED_CHANNEL_IDS)
            logger.info(f"有効なチャンネル数: {channel_count}")
            logger.info(f"有効なチャンネルID: {', '.join(str(id) for id in ENABLED_CHANNEL_IDS)}")
        else:
            logger.info("有効なチャンネルが指定されていません。すべてのチャンネルで動作します。")
        
        # ステータスを設定
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="メッセージをスレッド化"
        )
        await self.change_presence(activity=activity)
        
    async def on_message(self, message: discord.Message):
        """
        メッセージ受信時のイベントハンドラ
        
        Args:
            message: 受信したDiscordメッセージ
        """
        # 自分自身のメッセージは無視
        if message.author == self.user:
            return
            
        # DMは無視
        if not isinstance(message.channel, discord.TextChannel):
            return
            
        # すでにスレッド内のメッセージは無視
        if isinstance(message.channel, discord.Thread):
            return
        
        # メッセージを処理
        await self.process_message(message)
            
    async def process_message(self, message: discord.Message):
        """
        メッセージを処理し、必要に応じてスレッドを作成
        
        Args:
            message: 処理するDiscordメッセージ
        """
        # 指定されたチャンネルIDのリストが存在し、かつ現在のチャンネルがリストに含まれていない場合は処理をスキップ
        if ENABLED_CHANNEL_IDS and message.channel.id not in ENABLED_CHANNEL_IDS:
            return
            
        # スレッド作成条件をチェック
        if should_create_thread(message, TRIGGER_KEYWORDS):
            try:
                # スレッドを作成
                thread = await create_thread_from_message(
                    message=message,
                    name=THREAD_NAME_TEMPLATE.format(username=message.author.display_name),
                    auto_archive_duration=THREAD_AUTO_ARCHIVE_DURATION
                )
                
                if thread:
                    # スレッドからBotを退出
                    await asyncio.sleep(1)  # スレッド作成後、少し待機
                    await thread.leave()
                    logger.info(f"スレッド '{thread.name}' から退出しました")
                    
            except discord.Forbidden:
                logger.error("スレッド作成に必要な権限がありません")
            except discord.HTTPException as e:
                logger.error(f"スレッド作成中にエラーが発生しました: {e}")
            except Exception as e:
                logger.error(f"予期しないエラーが発生しました: {e}")