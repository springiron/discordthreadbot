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
    THREAD_CLOSE_KEYWORDS, THREAD_CLOSED_NAME_TEMPLATE, THREAD_MONITORING_DURATION,IGNORED_BOT_IDS,
    update_setting, get_editable_settings
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
            author_id_str = str(message.author.id)

            # IGNORED_BOT_IDSをカンマ区切りでリスト化
            ignored_ids_str = IGNORED_BOT_IDS.split(",") if IGNORED_BOT_IDS else []
            
            logger.debug(f"比較: {author_id_str} in {ignored_ids_str} = {author_id_str in ignored_ids_str}")
            
            for ignored_id in ignored_ids_str:
                if author_id_str == ignored_id.strip():
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
            print(update_setting(setting_name, new_value))
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
                    "!closekeywords": "締め切りキーワード一覧を表示します",
                    "!help": "このヘルプを表示します",
                }
                
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
                    await ctx.send(f"コマンド `{command_name}` は存在しません。")@self.command(name="keywords", help="現在のトリガーキーワード一覧を表示します")
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

        @self.command(name="closekeywords", help="締め切りキーワード一覧を表示します")
        async def closekeywords_command(ctx):
            keywords = ", ".join(f"`{kw}`" for kw in THREAD_CLOSE_KEYWORDS) if THREAD_CLOSE_KEYWORDS else "（なし）"
            embed = discord.Embed(
                title="締め切りキーワード",
                description=f"以下のキーワードでスレッドを締め切ります：\n{keywords}",
                color=discord.Color.green()
            )
            
            if self.is_admin(ctx.author):
                embed.add_field(
                    name="変更方法",
                    value="`!config THREAD_CLOSE_KEYWORDS キーワード1,キーワード2`",
                    inline=False
                )
            
            await ctx.send(embed=embed)

        @self.command(name="debug", help="デバッグ情報を表示します（管理者用）")
        async def debug_command(ctx):
            # 管理者権限チェック
            if not self.is_admin(ctx.author):
                await ctx.send("⚠️ このコマンドは管理者のみ使用できます。")
                return
                
            from bot.thread_handler import get_monitored_threads_status, monitored_threads
            from config import DEBUG_MODE
            
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
            
        # ヘルパーメソッド
        def _format_setting_value(self, value):
            """設定値を読みやすくフォーマット"""
            if isinstance(value, (list, set)):
                return ", ".join(str(item) for item in value) if value else "（なし）"
            return str(value) if value is not None else "（なし）"

        @self.command(name="ignoredbots", help="無視するBotの一覧を表示します")
        async def ignoredbots_command(ctx):
            """無視するBotの一覧を表示するコマンド"""
            if not IGNORED_BOT_IDS:
                desc = "無視するBotは設定されていません"
            else:
                desc = "無視するBot: " + IGNORED_BOT_IDS
            
            embed = discord.Embed(title="無視するBotリスト", description=desc, color=discord.Color.green())
            
            if self.is_admin(ctx.author):
                embed.add_field(
                    name="変更方法",
                    value="`!config IGNORED_BOT_IDS BotID1,BotID2`\n例: `!config IGNORED_BOT_IDS 123456789012345678`",
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
            
            # description キーの存在を確認してから使用
            description = info.get('description', '説明なし')
            
            embed.add_field(
                name=name,
                value=f"{description}\n**現在の値:** {value_str}",
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
        global TRIGGER_KEYWORDS, ENABLED_CHANNEL_IDS, THREAD_AUTO_ARCHIVE_DURATION
        global THREAD_NAME_TEMPLATE, ADMIN_USER_IDS, THREAD_CLOSE_KEYWORDS
        global THREAD_CLOSED_NAME_TEMPLATE, THREAD_MONITORING_DURATION
        
        # 設定値は config.py の update_setting() で既に適切な型に変換されているため
        # ここでは単にグローバル変数に代入するだけでOK
        if setting_name == "TRIGGER_KEYWORDS":
            TRIGGER_KEYWORDS = new_value
        elif setting_name == "ENABLED_CHANNEL_IDS":
            ENABLED_CHANNEL_IDS = new_value
        elif setting_name == "THREAD_AUTO_ARCHIVE_DURATION":
            THREAD_AUTO_ARCHIVE_DURATION = new_value
        elif setting_name == "THREAD_NAME_TEMPLATE":
            THREAD_NAME_TEMPLATE = new_value
        elif setting_name == "ADMIN_USER_IDS":
            ADMIN_USER_IDS = new_value
        elif setting_name == "THREAD_CLOSE_KEYWORDS":
            THREAD_CLOSE_KEYWORDS = new_value
        elif setting_name == "THREAD_CLOSED_NAME_TEMPLATE":
            THREAD_CLOSED_NAME_TEMPLATE = new_value
        elif setting_name == "THREAD_MONITORING_DURATION":
            THREAD_MONITORING_DURATION = new_value

    async def _send_config_update_message(self, ctx, setting_name, new_value):
        """設定更新メッセージを送信"""
        if setting_name == "TRIGGER_KEYWORDS":
            # キーワードリストの整形
            keywords_list = ", ".join(f"`{kw}`" for kw in TRIGGER_KEYWORDS) if TRIGGER_KEYWORDS else "（なし）"
            await ctx.send(f"✅ トリガーキーワードを更新しました: {keywords_list}")
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
        elif setting_name == "THREAD_CLOSE_KEYWORDS":
            keywords_list = ", ".join(f"`{kw}`" for kw in THREAD_CLOSE_KEYWORDS) if THREAD_CLOSE_KEYWORDS else "（なし）"
            await ctx.send(f"✅ 締め切りキーワードを更新しました: {keywords_list}")
        elif setting_name == "THREAD_CLOSED_NAME_TEMPLATE":
            example = THREAD_CLOSED_NAME_TEMPLATE.format(original_name=f"{ctx.author.display_name}の募集")
            await ctx.send(f"✅ 締め切り後のスレッド名テンプレートを更新しました: `{THREAD_CLOSED_NAME_TEMPLATE}`\n例: {example}")
        elif setting_name == "THREAD_MONITORING_DURATION":
            duration_map = {60: "1時間", 180: "3時間", 360: "6時間", 720: "12時間", 
                           1440: "1日", 4320: "3日", 10080: "1週間", 43200: "1ヶ月"}
            duration_text = duration_map.get(THREAD_MONITORING_DURATION, f"{THREAD_MONITORING_DURATION}分")
            await ctx.send(f"✅ スレッド監視時間を更新しました: {duration_text}")
        else:
            await ctx.send(f"✅ 設定 `{setting_name}` を更新しました")
        
    
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
        
        # デバッグモードの場合、定期的にスレッド監視状態をログに出力するタスクを開始
        from config import DEBUG_MODE
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


