#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client.py - Discord スレッド自動生成 Bot
"""

import discord
from discord.ext import commands
import asyncio
from typing import Optional, List, Union, Dict, Any
import re

from config import (
    BOT_CONFIG, TRIGGER_KEYWORDS, THREAD_AUTO_ARCHIVE_DURATION, 
    THREAD_NAME_TEMPLATE, ENABLED_CHANNEL_IDS, ADMIN_USER_IDS, 
    update_setting, get_editable_settings
)
from bot.thread_handler import should_create_thread, create_thread_from_message
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ThreadBot(commands.Bot):
    """スレッド自動生成Bot"""
    
    def __init__(self):
        """Botの初期化"""
        # Botの意図を設定
        intents = discord.Intents.default()
        intents.message_content = BOT_CONFIG["BOT_INTENTS"]["message_content"]
        intents.guilds = BOT_CONFIG["BOT_INTENTS"]["guilds"]
        intents.messages = BOT_CONFIG["BOT_INTENTS"]["messages"]
        intents.guild_messages = BOT_CONFIG["BOT_INTENTS"]["guild_messages"]
        
        # Botを初期化
        super().__init__(command_prefix="!", intents=intents)
        logger.info("ThreadBotを初期化しました")
        
        # コマンドの登録
        self.add_commands()
        
    async def process_message(self, message: discord.Message):
        """
        メッセージを処理し、必要に応じてスレッドを作成
        """
        channel_id = message.channel.id
        
        # 指定されたチャンネルIDのリストがある場合、そのチャンネルでのみ動作
        if ENABLED_CHANNEL_IDS and channel_id not in ENABLED_CHANNEL_IDS:
            return
            
        # スレッド作成条件をチェック
        if should_create_thread(message, TRIGGER_KEYWORDS):
            logger.info(f"スレッド作成: メッセージID={message.id}")
            try:
                # スレッド名を生成
                thread_name = THREAD_NAME_TEMPLATE.format(username=message.author.display_name)
                
                # スレッドを作成
                thread = await create_thread_from_message(
                    message=message,
                    name=thread_name,
                    auto_archive_duration=THREAD_AUTO_ARCHIVE_DURATION
                )
                
                if thread:
                    logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) 作成完了")
                    # スレッドからBotを退出
                    await asyncio.sleep(1)
                    await thread.leave()
                    
            except Exception as e:
                logger.error(f"スレッド作成エラー: {e}")
            
    def add_commands(self):
        """コマンドを登録"""
        
        @self.command(name="config", help="Bot設定を表示・変更します")
        async def config_command(ctx, setting_name: str = None, *, new_value: str = None):
            # 管理者権限チェック
            if not self.is_admin(ctx.author):
                await ctx.send("⚠️ このコマンドは管理者のみ使用できます。")
                return
            
            # 設定名が指定されていない場合は一覧を表示
            if setting_name is None:
                await self.show_config_list(ctx)
                return
                
            # 設定名を正規化して編集可能な設定を取得
            setting_name = setting_name.upper()
            editable_settings = get_editable_settings()
            
            # 存在しない設定の場合
            if setting_name not in editable_settings:
                valid_settings = ", ".join(f"`{k}`" for k in editable_settings.keys())
                await ctx.send(f"⚠️ 無効な設定名です。有効な設定: {valid_settings}")
                return
            
            # 設定情報を取得
            setting_info = editable_settings[setting_name]
            
            # 値表示モード
            if new_value is None:
                embed = discord.Embed(
                    title=f"設定: {setting_name}",
                    description=setting_info['description'],
                    color=discord.Color.blue()
                )
                
                # 現在の値をフォーマット
                value_str = self._format_setting_value(setting_info['current_value'])
                embed.add_field(name="型", value=setting_info['type'], inline=True)
                embed.add_field(name="現在の値", value=value_str, inline=True)
                
                # 選択肢と説明を追加
                if setting_info['options']:
                    embed.add_field(name="選択肢", value=", ".join(str(opt) for opt in setting_info['options']), inline=False)
                if setting_info.get('help_text'):
                    embed.add_field(name="ヘルプ", value=setting_info['help_text'], inline=False)
                
                await ctx.send(embed=embed)
                return
            
            # 設定更新モード
            if update_setting(setting_name, new_value):
                self._update_global_settings(setting_name, new_value)
                await self._send_config_update_message(ctx, setting_name, new_value)
            else:
                await ctx.send(f"❌ 設定 `{setting_name}` の更新に失敗しました。")
        
        @self.command(name="bothelp", help="コマンドのヘルプを表示します")
        async def bothelp_command(ctx, command_name: str = None):
            if command_name is None:
                # 基本ヘルプ
                embed = discord.Embed(
                    title="スレッド自動生成Bot",
                    description="キーワードを含むメッセージに対して自動的にスレッドを作成します。",
                    color=discord.Color.blue()
                )
                
                # 基本コマンド一覧
                commands = {
                    "!config": "Bot設定を表示・変更します（管理者用）",
                    "!keywords": "トリガーキーワード一覧を表示します",
                    "!channels": "Bot有効チャンネル一覧を表示します",
                    "!help": "このヘルプを表示します",
                }
                
                for cmd, desc in commands.items():
                    embed.add_field(name=cmd, value=desc, inline=False)
                
                # 現在のキーワード表示
                embed.add_field(name="現在のトリガーキーワード", value=TRIGGER_KEYWORDS, inline=False)
                
                # 管理者情報
                is_admin = self.is_admin(ctx.author)
                embed.set_footer(text=f"{'管理者権限あり' if is_admin else '管理者権限なし'}")
                
                await ctx.send(embed=embed)
            else:
                # 特定コマンドのヘルプ
                command = self.get_command(command_name.lower())
                if command:
                    await ctx.send(f"**{command.name}**: {command.help}")
                else:
                    await ctx.send(f"コマンド `{command_name}` は存在しません。")
        
        @self.command(name="keywords", help="現在のトリガーキーワード一覧を表示します")
        async def keywords_command(ctx):
            keywords = ", ".join(f"`{kw}`" for kw in TRIGGER_KEYWORDS) if TRIGGER_KEYWORDS else "（なし）"
            embed = discord.Embed(
                title="トリガーキーワード",
                description=f"以下のキーワードでスレッドを作成します：\n{keywords}",
                color=discord.Color.green()
            )
            
            if self.is_admin(ctx.author):
                embed.add_field(
                    name="変更方法",
                    value="`!config TRIGGER_KEYWORDS キーワード1,キーワード2`",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        
        @self.command(name="channels", help="Bot有効チャンネル一覧を表示します")
        async def channels_command(ctx):
            if not ENABLED_CHANNEL_IDS:
                desc = "すべてのチャンネルで有効です"
            else:
                channels = []
                for channel_id in ENABLED_CHANNEL_IDS:
                    channel = self.get_channel(channel_id)
                    channel_name = f"#{channel.name}" if channel else f"ID:{channel_id}"
                    channels.append(channel_name)
                desc = "有効なチャンネル: " + ", ".join(channels)
            
            embed = discord.Embed(title="有効チャンネル", description=desc, color=discord.Color.green())
            
            if self.is_admin(ctx.author):
                embed.add_field(
                    name="変更方法",
                    value="`!config ENABLED_CHANNEL_IDS チャンネルID1,チャンネルID2`\n空にすると全チャンネルで有効",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        # ヘルパーメソッド
        def _format_setting_value(self, value):
            """設定値を読みやすくフォーマット"""
            if isinstance(value, (list, set)):
                return ", ".join(str(item) for item in value) if value else "（なし）"
            return str(value) if value is not None else "（なし）"
            
    async def show_config_list(self, ctx):
        """編集可能な設定一覧を表示"""
        editable_settings = get_editable_settings()
        
        embed = discord.Embed(
            title="Bot設定一覧",
            description="以下の設定を変更できます。詳細は `!config 設定名` で確認できます。",
            color=discord.Color.blue()
        )
        
        for name, info in editable_settings.items():
            # 値を読みやすく整形
            value_str = self._format_setting_value(info['current_value'])
            if len(value_str) > 100:
                value_str = value_str[:97] + "..."
            
            embed.add_field(
                name=name,
                value=f"{info['description']}\n**現在の値:** {value_str}",
                inline=False
            )
        
        embed.set_footer(text="!config <設定名> <新しい値> で設定を変更できます")
        await ctx.send(embed=embed)
    
    def _format_setting_value(self, value):
        """設定値を読みやすくフォーマット"""
        if isinstance(value, (list, set)):
            return ", ".join(str(item) for item in value) if value else "（なし）"
        return str(value) if value is not None else "（なし）"
    
    def _update_global_settings(self, setting_name, new_value):
        """グローバル設定を更新"""
        global TRIGGER_KEYWORDS, ENABLED_CHANNEL_IDS, THREAD_AUTO_ARCHIVE_DURATION, THREAD_NAME_TEMPLATE, ADMIN_USER_IDS
        
        if setting_name == "TRIGGER_KEYWORDS":
            TRIGGER_KEYWORDS = new_value
        elif setting_name == "ENABLED_CHANNEL_IDS":
            ENABLED_CHANNEL_IDS = new_value
        elif setting_name == "THREAD_AUTO_ARCHIVE_DURATION":
            THREAD_AUTO_ARCHIVE_DURATION = int(new_value)
        elif setting_name == "THREAD_NAME_TEMPLATE":
            THREAD_NAME_TEMPLATE = new_value
        elif setting_name == "ADMIN_USER_IDS":
            ADMIN_USER_IDS = new_value
    
    async def _send_config_update_message(self, ctx, setting_name, new_value):
        """設定更新メッセージを送信"""

        if setting_name == "TRIGGER_KEYWORDS":
            
            # TRIGGER_KEYWORDSの値を整形(カンマ区切りがあれば分割)


            # value_str = ", ".join(f"`{kw}`" for kw in TRIGGER_KEYWORDS)
            print(TRIGGER_KEYWORDS)
            await ctx.send(f"✅ トリガーキーワードを更新しました: {TRIGGER_KEYWORDS}")

        elif setting_name == "ENABLED_CHANNEL_IDS":
            if ENABLED_CHANNEL_IDS:
                channels = []
                for channel_id in ENABLED_CHANNEL_IDS:
                    channel = self.get_channel(channel_id)
                    channel_name = f"#{channel.name}" if channel else f"ID:{channel_id}"
                    channels.append(channel_name)
                value_str = ", ".join(channels)
                await ctx.send(f"✅ 有効なチャンネルを更新しました: {value_str}")
            else:
                await ctx.send("✅ すべてのチャンネルで有効になりました")
        elif setting_name == "THREAD_AUTO_ARCHIVE_DURATION":
            duration_map = {60: "1時間", 1440: "1日", 4320: "3日", 10080: "1週間"}
            duration_text = duration_map.get(THREAD_AUTO_ARCHIVE_DURATION, f"{THREAD_AUTO_ARCHIVE_DURATION}分")
            await ctx.send(f"✅ スレッド自動アーカイブ時間を更新しました: {duration_text}")
        elif setting_name == "THREAD_NAME_TEMPLATE":
            example = THREAD_NAME_TEMPLATE.format(username=ctx.author.display_name)
            await ctx.send(f"✅ スレッド名テンプレートを更新しました: `{THREAD_NAME_TEMPLATE}`\n例: {example}")
        elif setting_name == "ADMIN_USER_IDS":
            admins = []
            for user_id in ADMIN_USER_IDS:
                user = self.get_user(user_id)
                user_name = f"{user.name}" if user else f"ID:{user_id}"
                admins.append(user_name)
            value_str = ", ".join(admins) if admins else "（なし）"
            await ctx.send(f"✅ 管理者ユーザーを更新しました: {value_str}")
        else:
            await ctx.send(f"✅ 設定 `{setting_name}` を `{new_value}` に更新しました") 
      
    
    def is_admin(self, user: discord.User) -> bool:
        """ユーザーが管理者権限を持っているか確認"""
        # 管理者IDリストが空の場合はサーバー管理者を管理者とみなす
        if not ADMIN_USER_IDS:
            for guild in self.guilds:
                member = guild.get_member(user.id)
                if member and member.guild_permissions.administrator:
                    return True
            return False
        
        # 管理者IDリストが設定されている場合はそれを使用
        return user.id in ADMIN_USER_IDS 
        
    async def on_ready(self):
        """Bot準備完了時のイベントハンドラ"""
        logger.info(f"{self.user.name} としてログインしました (ID: {self.user.id})")
        
        # ステータスを設定
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="メッセージをスレッド化 | !help"
        )
        
        await self.change_presence(activity=activity)
        
    async def on_message(self, message: discord.Message):
        """メッセージ受信時のイベントハンドラ"""
        # 自分自身のメッセージは無視
        if message.author == self.user:
            return
            
        # DMは無視
        if not isinstance(message.channel, discord.TextChannel):
            return
            
        # すでにスレッド内のメッセージは無視
        if isinstance(message.channel, discord.Thread):
            return
        
        # コマンド処理を試みる
        ctx = await self.get_context(message)
        if ctx.valid:
            await self.invoke(ctx)
            return
        
        # メッセージを処理
        await self.process_message(message)