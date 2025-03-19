#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client.py の修正版 - 詳細なデバッグ出力を追加
"""

import discord
from discord.ext import commands
import asyncio
from typing import Optional, List, Union

from config import BOT_CONFIG, TRIGGER_KEYWORDS, THREAD_AUTO_ARCHIVE_DURATION, THREAD_NAME_TEMPLATE, ENABLED_CHANNEL_IDS, DEBUG_MODE
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
        intents.message_content = BOT_CONFIG["BOT_INTENTS"]["message_content"]
        intents.guilds = BOT_CONFIG["BOT_INTENTS"]["guilds"]
        intents.messages = BOT_CONFIG["BOT_INTENTS"]["messages"]
        intents.guild_messages = BOT_CONFIG["BOT_INTENTS"]["guild_messages"]
        
        # Botを初期化
        super().__init__(command_prefix="!", intents=intents)
        logger.info("ThreadBotを初期化しました")
        
        # 設定情報をログに出力
        logger.info(f"トリガーキーワード: {TRIGGER_KEYWORDS}")
        logger.info(f"THREAD_AUTO_ARCHIVE_DURATION: {THREAD_AUTO_ARCHIVE_DURATION}")
        logger.info(f"THREAD_NAME_TEMPLATE: {THREAD_NAME_TEMPLATE}")
        
    async def on_ready(self):
        """
        Bot準備完了時のイベントハンドラ
        """
        logger.info(f"{self.user.name} としてログインしました (ID: {self.user.id})")
        
        # サーバー情報をログに出力
        guild_count = len(self.guilds)
        logger.info(f"参加しているサーバー数: {guild_count}")
        for guild in self.guilds:
            logger.info(f"サーバー: {guild.name} (ID: {guild.id})")
            text_channels = len(guild.text_channels)
            logger.info(f"  テキストチャンネル数: {text_channels}")
            
            # 各チャンネルの情報とBotの権限を表示
            for channel in guild.text_channels:
                permissions = channel.permissions_for(guild.me)
                can_read = permissions.read_messages
                can_send = permissions.send_messages
                can_create_thread = permissions.create_public_threads
                logger.info(f"  チャンネル: {channel.name} (ID: {channel.id})")
                logger.info(f"    権限 - 読み取り: {can_read}, 送信: {can_send}, スレッド作成: {can_create_thread}")
                
                # 有効なチャンネルかどうかを確認
                is_enabled = not ENABLED_CHANNEL_IDS or channel.id in ENABLED_CHANNEL_IDS
                logger.info(f"    有効なチャンネル: {is_enabled}")
        
        # 有効なチャンネルの情報をログに記録
        if ENABLED_CHANNEL_IDS:
            channel_count = len(ENABLED_CHANNEL_IDS)
            logger.info(f"有効なチャンネル数: {channel_count}")
            # 各IDを個別に表示し、重複を防ぐ
            channel_ids_str = ", ".join([str(channel_id) for channel_id in ENABLED_CHANNEL_IDS])
            logger.info(f"有効なチャンネルID: {channel_ids_str}")
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
        # メッセージの基本情報をログに出力
        logger.info(f"メッセージ受信: ID={message.id}, チャンネル={message.channel.name} (ID={message.channel.id}), 著者={message.author.name}")
        logger.info(f"メッセージ内容: {message.content[:50]}...")
        
        # 自分自身のメッセージは無視
        if message.author == self.user:
            logger.debug("自分自身のメッセージのため無視します")
            return
            
        # DMは無視
        if not isinstance(message.channel, discord.TextChannel):
            logger.debug("DMメッセージのため無視します")
            return
            
        # すでにスレッド内のメッセージは無視
        if isinstance(message.channel, discord.Thread):
            logger.debug("すでにスレッド内のメッセージのため無視します")
            return
        
        # メッセージを処理
        logger.info(f"メッセージを処理します: ID={message.id}")
        await self.process_message(message)
            
    async def process_message(self, message: discord.Message):
        """
        メッセージを処理し、必要に応じてスレッドを作成
        
        Args:
            message: 処理するDiscordメッセージ
        """
        # デバッグ情報を追加
        channel_id = message.channel.id
        logger.info(f"メッセージ処理: チャンネルID={channel_id}, チャンネル名={message.channel.name}, 内容={message.content[:50]}...")
        
        # 指定されたチャンネルIDのリストが存在し、かつ現在のチャンネルがリストに含まれていない場合は処理をスキップ
        if ENABLED_CHANNEL_IDS:
            logger.info(f"有効なチャンネルIDs: {ENABLED_CHANNEL_IDS} (型: {type(ENABLED_CHANNEL_IDS)})")
            logger.info(f"現在のチャンネルID: {channel_id} (型: {type(channel_id)})")
            
            if channel_id in ENABLED_CHANNEL_IDS:
                logger.info(f"チャンネル {channel_id} は有効リスト内です")
            else:
                logger.info(f"チャンネル {channel_id} は有効リスト外のため無視します")
                return
        else:
            logger.info("有効なチャンネルIDリストが指定されていないため、すべてのチャンネルを処理します")
            
        # トリガーキーワードの情報をログに出力
        logger.info(f"トリガーキーワード: {TRIGGER_KEYWORDS}")
        
        # スレッド作成条件をチェック
        should_create = should_create_thread(message, TRIGGER_KEYWORDS)
        logger.info(f"スレッド作成条件の結果: {should_create}")
        
        if should_create:
            logger.info(f"スレッド作成条件を満たしているため、スレッドを作成します: メッセージID={message.id}")
            try:
                # スレッド名を生成
                thread_name = THREAD_NAME_TEMPLATE.format(username=message.author.display_name)
                logger.info(f"生成されたスレッド名: {thread_name}")
                
                # スレッドを作成
                logger.info(f"スレッド作成を開始します: メッセージID={message.id}, スレッド名={thread_name}")
                thread = await create_thread_from_message(
                    message=message,
                    name=thread_name,
                    auto_archive_duration=THREAD_AUTO_ARCHIVE_DURATION
                )
                
                if thread:
                    logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) が正常に作成されました")
                    # スレッドからBotを退出
                    await asyncio.sleep(1)  # スレッド作成後、少し待機
                    logger.info(f"スレッド '{thread.name}' から退出を試みます")
                    await thread.leave()
                    logger.info(f"スレッド '{thread.name}' から退出しました")
                else:
                    logger.error(f"スレッド作成に失敗しました: メッセージID={message.id}")
                    
            except discord.Forbidden as e:
                logger.error(f"スレッド作成に必要な権限がありません: {e}")
                logger.error(f"対象チャンネル: {message.channel.name} (ID: {message.channel.id})")
                # 権限の詳細を確認
                if message.guild:
                    permissions = message.channel.permissions_for(message.guild.me)
                    logger.error(f"Botの権限 - スレッド作成: {permissions.create_public_threads}, メッセージ送信: {permissions.send_messages}")
            except discord.HTTPException as e:
                logger.error(f"スレッド作成中にHTTPエラーが発生しました: {e}")
                logger.error(f"HTTPステータス: {e.status}, コード: {e.code}, テキスト: {e.text}")
            except Exception as e:
                logger.error(f"予期しないエラーが発生しました: {e}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.info(f"スレッド作成条件を満たしていないため、スレッドは作成しません: メッセージID={message.id}")