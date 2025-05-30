#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client.py - Discord スレッド自動生成 Bot (シンプル化版)
"""

import discord
from discord.ext import commands
import asyncio
from typing import Optional, List, Union, Dict, Any
import re

from config import (
    BOT_CONFIG, TRIGGER_KEYWORDS, THREAD_AUTO_ARCHIVE_DURATION, 
    THREAD_NAME_TEMPLATE, ENABLED_CHANNEL_IDS, ADMIN_USER_IDS, 
    THREAD_CLOSE_KEYWORDS, THREAD_CLOSED_NAME_TEMPLATE, THREAD_MONITORING_DURATION,
    IGNORED_BOT_IDS, DEBUG_MODE
)
from bot.thread_handler import (
    should_create_thread, create_thread_from_message,
    process_thread_message, monitored_threads
)
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
        
        # イベントリスナーの追加
        self.add_listeners()
        
    def add_listeners(self):
        """イベントリスナーを追加"""
        
        @self.event
        async def on_interaction(interaction: discord.Interaction):
            """インタラクション処理"""
            # ボタンインタラクションのみを処理
            if interaction.type == discord.InteractionType.component:
                # 締め切りボタンかどうかを確認
                if interaction.data.get("custom_id", "").startswith("close_thread_"):
                    # ボタンのコールバックはボタンクラス内で処理されるため、
                    # ここでは追加のログ記録のみ行う
                    logger.debug(f"締め切りボタンが押されました: ユーザー={interaction.user.display_name}, "
                            f"チャンネル={interaction.channel.name if interaction.channel else 'unknown'}")
        
    async def process_message(self, message: discord.Message):
        """
        メッセージを処理し、必要に応じてスレッドを作成
        """
        channel_id = message.channel.id
        
        # 指定されたチャンネルIDのリストがある場合、そのチャンネルでのみ動作
        if ENABLED_CHANNEL_IDS and channel_id not in ENABLED_CHANNEL_IDS:
            return
        
        # 無視するBotからのメッセージをスキップするロジックの前に追加
        if message.author.bot:
            logger.debug(f"Botからのメッセージを検出: Bot ID={message.author.id}, 無視リスト={IGNORED_BOT_IDS}")

            # 型変換を明示的に行って比較
            author_id = message.author.id

            # IGNORED_BOT_IDSがsetなので直接比較
            if author_id in IGNORED_BOT_IDS:
                logger.debug(f"無視リストに含まれるBot (ID: {message.author.id}) からのメッセージをスキップします")
                return
            
        # スレッド作成条件をチェック
        if should_create_thread(message, TRIGGER_KEYWORDS):
            logger.info(f"スレッド作成: メッセージ={message.clean_content}")
            logger.info(f"スレッド作成: メッセージID={message.id}")
            try:
                # スレッド名を生成
                thread_name = THREAD_NAME_TEMPLATE.format(username=message.author.display_name)
                
                # thread_handler.py の関数を呼び出すためのパラメータを準備
                create_args = {
                    "message": message,
                    "name": thread_name,
                    "auto_archive_duration": THREAD_AUTO_ARCHIVE_DURATION,
                    "monitoring_duration": THREAD_MONITORING_DURATION,
                    "close_keywords": THREAD_CLOSE_KEYWORDS,
                    "closed_name_template": THREAD_CLOSED_NAME_TEMPLATE,
                    "bot": self  # ここでボットインスタンスを渡す
                }
                
                # スレッドを作成
                thread = await create_thread_from_message(**create_args)
                
                if thread:
                    logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) 作成完了")
                    
                    # スレッドからBotを退出するのは監視時間が0の場合のみ
                    if THREAD_MONITORING_DURATION <= 0:
                        await asyncio.sleep(1)
                        await thread.leave()
                        logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) からBotが退出しました")
                    
            except Exception as e:
                logger.error(f"スレッド作成エラー: {e}")
    
    async def process_thread_message(self, message: discord.Message):
        """
        スレッド内のメッセージを処理し、必要に応じてスレッド名を変更
        """
        # スレッド内のメッセージのみを処理
        if not isinstance(message.channel, discord.Thread):
            return
            
        # スレッド内のメッセージを処理
        # thread_handler.pyの更新された関数を呼び出す - 作成者チェックが追加されている
        await process_thread_message(
            message=message,
            close_keywords=THREAD_CLOSE_KEYWORDS,
            closed_name_template=THREAD_CLOSED_NAME_TEMPLATE
        )
            
    def add_commands(self):
        """コマンドを登録"""
        
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
                    "!keywords": "トリガーキーワード一覧を表示します",
                    "!channels": "Bot有効チャンネル一覧を表示します",
                    "!closekeywords": "締め切りキーワード一覧を表示します",
                    "!ignoredbots": "無視するBotの一覧を表示します",
                    "!settings": "現在の設定を表示します",
                    "!help": "このヘルプを表示します",
                }
                
                if self.is_admin(ctx.author):
                    commands["!debug"] = "デバッグ情報を表示します（管理者用）"
                
                for cmd, desc in commands.items():
                    embed.add_field(name=cmd, value=desc, inline=False)
                
                # 現在のキーワード表示
                embed.add_field(name="現在のトリガーキーワード", value=", ".join(TRIGGER_KEYWORDS), inline=False)
                
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
            
            embed.add_field(
                name="変更方法",
                value="設定ファイル（.env）の `TRIGGER_KEYWORDS` を編集してBotを再起動してください",
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
            
            embed.add_field(
                name="変更方法",
                value="設定ファイル（.env）の `ENABLED_CHANNEL_IDS` を編集してBotを再起動してください",
                inline=False
            )
            
            await ctx.send(embed=embed)

        @self.command(name="closekeywords", help="締め切りキーワード一覧を表示します")
        async def closekeywords_command(ctx):
            keywords = ", ".join(f"`{kw}`" for kw in THREAD_CLOSE_KEYWORDS) if THREAD_CLOSE_KEYWORDS else "（なし）"
            embed = discord.Embed(
                title="締め切りキーワード",
                description=f"以下のキーワードでスレッドを締め切ります：\n{keywords}",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="変更方法",
                value="設定ファイル（.env）の `THREAD_CLOSE_KEYWORDS` を編集してBotを再起動してください",
                inline=False
            )
            
            await ctx.send(embed=embed)

        @self.command(name="ignoredbots", help="無視するBotの一覧を表示します")
        async def ignoredbots_command(ctx):
            """無視するBotの一覧を表示するコマンド"""
            if not IGNORED_BOT_IDS:
                desc = "無視するBotは設定されていません"
            else:
                bot_names = []
                for bot_id in IGNORED_BOT_IDS:
                    bot = self.get_user(bot_id)
                    bot_name = f"{bot.name} (ID:{bot_id})" if bot else f"ID:{bot_id}"
                    bot_names.append(bot_name)
                desc = "無視するBot: " + ", ".join(bot_names)
            
            embed = discord.Embed(title="無視するBotリスト", description=desc, color=discord.Color.green())
            
            embed.add_field(
                name="変更方法",
                value="設定ファイル（.env）の `IGNORED_BOT_IDS` を編集してBotを再起動してください",
                inline=False
            )
                
            # Bot IDの取得方法を説明
            embed.add_field(
                name="Bot IDの調べ方",
                value="1. 開発者モードを有効にする（ユーザー設定→詳細設定）\n"
                    "2. 対象のBotを右クリックして「IDをコピー」を選択",
                inline=False
            )
            
            await ctx.send(embed=embed)

        @self.command(name="settings", help="現在の設定を表示します")
        async def settings_command(ctx):
            """現在の設定を表示するコマンド"""
            embed = discord.Embed(
                title="Bot設定一覧",
                description="現在の設定値を表示します。設定変更は.envファイルを編集してBotを再起動してください。",
                color=discord.Color.blue()
            )
            
            # 基本設定
            embed.add_field(
                name="🎯 基本設定",
                value=f"**デバッグモード**: {DEBUG_MODE}\n"
                      f"**トリガーキーワード**: {', '.join(TRIGGER_KEYWORDS)}\n"
                      f"**有効チャンネル数**: {len(ENABLED_CHANNEL_IDS) if ENABLED_CHANNEL_IDS else '全チャンネル'}",
                inline=False
            )
            
            # スレッド設定
            archive_map = {60: "1時間", 1440: "1日", 4320: "3日", 10080: "1週間"}
            archive_text = archive_map.get(THREAD_AUTO_ARCHIVE_DURATION, f"{THREAD_AUTO_ARCHIVE_DURATION}分")
            monitoring_map = {60: "1時間", 180: "3時間", 360: "6時間", 720: "12時間", 
                             1440: "1日", 4320: "3日", 10080: "1週間", 43200: "1ヶ月"}
            monitoring_text = monitoring_map.get(THREAD_MONITORING_DURATION, f"{THREAD_MONITORING_DURATION}分")
            
            embed.add_field(
                name="🧵 スレッド設定",
                value=f"**自動アーカイブ時間**: {archive_text}\n"
                      f"**監視時間**: {monitoring_text}\n"
                      f"**スレッド名テンプレート**: `{THREAD_NAME_TEMPLATE}`\n"
                      f"**締め切り後テンプレート**: `{THREAD_CLOSED_NAME_TEMPLATE}`",
                inline=False
            )
            
            # スプレッドシート設定
            from config import (SPREADSHEET_LOGGING_ENABLED, SPREADSHEET_DAILY_LIMIT_ENABLED, 
                              SPREADSHEET_DAILY_RESET_HOUR, SPREADSHEET_TIMEZONE_OFFSET)
            
            if SPREADSHEET_LOGGING_ENABLED:
                tz_name = "JST" if SPREADSHEET_TIMEZONE_OFFSET == 9 else f"UTC{SPREADSHEET_TIMEZONE_OFFSET:+d}"
                spreadsheet_info = f"**ログ記録**: 有効\n"
                if SPREADSHEET_DAILY_LIMIT_ENABLED:
                    spreadsheet_info += f"**1日1回制限**: 有効 ({tz_name} {SPREADSHEET_DAILY_RESET_HOUR}:00リセット)"
                else:
                    spreadsheet_info += f"**1日1回制限**: 無効"
            else:
                spreadsheet_info = "**ログ記録**: 無効"
            
            embed.add_field(
                name="📊 スプレッドシート設定",
                value=spreadsheet_info,
                inline=False
            )
            
            embed.set_footer(text="設定変更: .envファイルを編集 → Bot再起動")
            await ctx.send(embed=embed)

        @self.command(name="debug", help="デバッグ情報を表示します（管理者用）")
        async def debug_command(ctx):
            # 管理者権限チェック
            if not self.is_admin(ctx.author):
                await ctx.send("⚠️ このコマンドは管理者のみ使用できます。")
                return
                
            from bot.thread_handler import get_monitored_threads_status, monitored_threads
            
            if not DEBUG_MODE:
                await ctx.send("⚠️ デバッグモードが無効です。環境変数 `DEBUG_MODE=true` を設定してBotを再起動してください。")
                return
                
            # 監視中のスレッド情報を取得
            threads_status = get_monitored_threads_status()
            
            if not threads_status:
                await ctx.send("📊 現在監視中のスレッドはありません。")
                return
                
            # 情報を表示
            embed = discord.Embed(
                title="🔍 監視中スレッド情報",
                description=f"現在 {len(threads_status)} 個のスレッドを監視中",
                color=discord.Color.blue()
            )
            
            for thread_id, info in threads_status.items():
                field_value = (
                    f"**作成者:** {info['author']}\n"
                    f"**作成日時:** {info['created_at']}\n"
                    f"**監視残り時間:** {info['monitoring_remaining_minutes']}分\n"
                    f"**アーカイブ時間:** {info['auto_archive_duration']}分"
                )
                embed.add_field(
                    name=f"💬 {info['name']} (ID: {thread_id})",
                    value=field_value,
                    inline=False
                )
            
            await ctx.send(embed=embed)
    
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
            name="メッセージをスレッド化 | !bothelp"
        )
        
        await self.change_presence(activity=activity)
        
        # デバッグモードの場合、定期的にスレッド監視状態をログに出力するタスクを開始
        if DEBUG_MODE:
            self.debug_task = asyncio.create_task(self.debug_log_task())
            logger.info("デバッグモード: スレッド監視状態のログ出力タスクを開始しました")
    
    async def debug_log_task(self):
        """定期的にスレッド監視状態をログに出力するタスク"""
        from bot.thread_handler import get_monitored_threads_status
        
        # 1時間ごとに出力
        log_interval = 60 * 60  # 1時間
        
        try:
            while True:
                # スレッド情報を取得
                threads_status = get_monitored_threads_status()
                
                if threads_status:
                    # 情報をログに出力
                    logger.debug(f"===== 監視中スレッド状態 ({len(threads_status)} 件) =====")
                    for thread_id, info in threads_status.items():
                        logger.debug(
                            f"スレッド: '{info['name']}' (ID: {thread_id}), "
                            f"作成者: {info['author']}, "
                            f"作成日時: {info['created_at']}, "
                            f"監視残り時間: {info['monitoring_remaining_minutes']}分, "
                            f"アーカイブ時間: {info['auto_archive_duration']}分"
                        )
                    logger.debug("============================================")
                
                # 待機
                await asyncio.sleep(log_interval)
                
        except asyncio.CancelledError:
            logger.info("デバッグログタスクが中断されました")
        except Exception as e:
            logger.error(f"デバッグログタスクでエラーが発生しました: {e}")
            
    async def close(self):
        """Botの終了処理"""
        # デバッグタスクが存在すれば中断
        if hasattr(self, 'debug_task') and self.debug_task and not self.debug_task.done():
            self.debug_task.cancel()
        
        # スレッド関連データのクリーンアップを実行
        from bot.thread_handler import cleanup_thread_data
        try:
            await cleanup_thread_data()
            logger.info("スレッド関連データをクリーンアップしました")
        except Exception as e:
            logger.error(f"スレッドデータのクリーンアップ中にエラーが発生しました: {e}")
            
        # 親クラスのclose処理を呼び出す
        await super().close()
        
    async def on_message(self, message: discord.Message):
        """メッセージ受信時のイベントハンドラ"""
        # 自分自身のメッセージは無視
        if message.author == self.user:
            return
            
        # DMは無視
        if not isinstance(message.channel, discord.TextChannel) and not isinstance(message.channel, discord.Thread):
            return
        
        # コマンド処理を試みる
        ctx = await self.get_context(message)
        if ctx.valid:
            await self.invoke(ctx)
            return
        
        # スレッド内のメッセージか、通常チャンネルのメッセージかで処理を分ける
        if isinstance(message.channel, discord.Thread):
            # スレッド内のメッセージを処理
            await self.process_thread_message(message)
        else:
            # 通常チャンネルのメッセージを処理
            await self.process_message(message)