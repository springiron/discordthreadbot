#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
client.py - 詳細なデバッグ出力と設定コマンド機能を追加
"""

import discord
from discord.ext import commands
import asyncio
from typing import Optional, List, Union, Dict, Any
import re

from config import (
    BOT_CONFIG, TRIGGER_KEYWORDS, THREAD_AUTO_ARCHIVE_DURATION, 
    THREAD_NAME_TEMPLATE, ENABLED_CHANNEL_IDS, DEBUG_MODE, 
    ADMIN_USER_IDS, update_setting, get_editable_settings
)
from bot.thread_handler import should_create_thread, create_thread_from_message
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ThreadBot(commands.Bot):
    """
    スレッド自動生成Bot - 設定コマンド機能を追加
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
        logger.info(f"管理者ユーザーID: {ADMIN_USER_IDS}")
        
        # コマンドの登録
        self.add_commands()
        
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
            
    def add_commands(self):
        """コマンドを登録"""
        
        @self.command(name="config", help="Bot設定を表示・変更します")
        async def config_command(ctx, setting_name: str = None, *, new_value: str = None):
            """
            Bot設定を表示・変更するコマンド
            
            Args:
                ctx: コマンドコンテキスト
                setting_name: 設定名（指定しない場合は一覧を表示）
                new_value: 新しい設定値（指定しない場合は現在の値を表示）
            """
            # 管理者権限チェック
            if not self.is_admin(ctx.author):
                await ctx.send("⚠️ このコマンドは管理者のみ使用できます。")
                logger.warning(f"管理者以外がconfig実行を試みました: {ctx.author.name} (ID: {ctx.author.id})")
                return
            
            # 設定名が指定されていない場合は一覧を表示
            if setting_name is None:
                await self.show_config_list(ctx)
                return
                
            # 設定名を正規化
            setting_name = setting_name.upper()
            
            # 編集可能な設定のリストを取得
            editable_settings = get_editable_settings()
            
            # 指定された設定が存在するか確認
            if setting_name not in editable_settings:
                valid_settings = ", ".join(f"`{k}`" for k in editable_settings.keys())
                await ctx.send(f"⚠️ 指定された設定 `{setting_name}` は存在しないか編集できません。\n"
                             f"有効な設定: {valid_settings}")
                return
            
            # 設定情報を取得
            setting_info = editable_settings[setting_name]
            current_value = setting_info['current_value']
            
            # 新しい値が指定されていない場合は現在の値を表示
            if new_value is None:
                # 設定の詳細情報を表示
                embed = discord.Embed(
                    title=f"設定: {setting_name}",
                    description=setting_info['description'],
                    color=discord.Color.blue()
                )
                
                # 型情報
                embed.add_field(name="型", value=setting_info['type'], inline=True)
                
                # 現在の値
                if isinstance(current_value, (list, set)):
                    value_str = ", ".join(str(item) for item in current_value) if current_value else "（なし）"
                else:
                    value_str = str(current_value) if current_value is not None else "（なし）"
                    
                embed.add_field(name="現在の値", value=value_str, inline=True)
                
                # 選択肢がある場合は表示
                if setting_info['options']:
                    options_str = ", ".join(str(opt) for opt in setting_info['options'])
                    embed.add_field(name="選択肢", value=options_str, inline=False)
                
                # ヘルプテキスト
                if setting_info.get('help_text'):
                    embed.add_field(name="ヘルプ", value=setting_info['help_text'], inline=False)
                
                # 設定方法の例
                embed.add_field(
                    name="設定例",
                    value=f"`!config {setting_name} 新しい値`",
                    inline=False
                )
                
                await ctx.send(embed=embed)
                return
            
            # 新しい値で設定を更新
            success = update_setting(setting_name, new_value)
            
            if success:
                # 設定の型に応じてメッセージを整形
                if setting_name == "TRIGGER_KEYWORDS":
                    global TRIGGER_KEYWORDS
                    TRIGGER_KEYWORDS = new_value
                    value_str = ", ".join(f"`{kw}`" for kw in TRIGGER_KEYWORDS)
                    await ctx.send(f"✅ トリガーキーワードを更新しました: {value_str}")
                    
                elif setting_name == "ENABLED_CHANNEL_IDS":
                    global ENABLED_CHANNEL_IDS
                    ENABLED_CHANNEL_IDS = new_value
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
                    global THREAD_AUTO_ARCHIVE_DURATION
                    THREAD_AUTO_ARCHIVE_DURATION = int(new_value)
                    duration_text = ""
                    if THREAD_AUTO_ARCHIVE_DURATION == 60:
                        duration_text = "1時間"
                    elif THREAD_AUTO_ARCHIVE_DURATION == 1440:
                        duration_text = "1日"
                    elif THREAD_AUTO_ARCHIVE_DURATION == 4320:
                        duration_text = "3日"
                    elif THREAD_AUTO_ARCHIVE_DURATION == 10080:
                        duration_text = "1週間"
                    
                    await ctx.send(f"✅ スレッド自動アーカイブ時間を更新しました: {duration_text} ({THREAD_AUTO_ARCHIVE_DURATION}分)")
                    
                elif setting_name == "THREAD_NAME_TEMPLATE":
                    global THREAD_NAME_TEMPLATE
                    THREAD_NAME_TEMPLATE = new_value
                    example = THREAD_NAME_TEMPLATE.format(username=ctx.author.display_name)
                    await ctx.send(f"✅ スレッド名テンプレートを更新しました: `{THREAD_NAME_TEMPLATE}`\n"
                                 f"例: {example}")
                    
                elif setting_name == "ADMIN_USER_IDS":
                    global ADMIN_USER_IDS
                    ADMIN_USER_IDS = new_value
                    admins = []
                    for user_id in ADMIN_USER_IDS:
                        user = self.get_user(user_id)
                        user_name = f"{user.name}" if user else f"ID:{user_id}"
                        admins.append(user_name)
                    value_str = ", ".join(admins) if admins else "（なし）"
                    await ctx.send(f"✅ 管理者ユーザーを更新しました: {value_str}")
                    
                else:
                    # その他の設定
                    await ctx.send(f"✅ 設定 `{setting_name}` を `{new_value}` に更新しました")
                
                logger.info(f"設定 {setting_name} を {new_value} に更新しました (実行者: {ctx.author.name})")
            else:
                # 更新失敗
                await ctx.send(f"❌ 設定 `{setting_name}` の更新に失敗しました。値が正しいか確認してください。")
                logger.error(f"設定 {setting_name} の更新に失敗しました (値: {new_value}, 実行者: {ctx.author.name})")
        
        async def show_config_list(self, ctx):
            """編集可能な設定一覧を表示"""
            editable_settings = get_editable_settings()
            
            embed = discord.Embed(
                title="Bot設定一覧",
                description="以下の設定を変更できます。詳細は `!config 設定名` で確認できます。",
                color=discord.Color.blue()
            )
            
            for name, info in editable_settings.items():
                # 現在の値を取得（リストや辞書はカンマ区切りの文字列に変換）
                if isinstance(info['current_value'], (list, set)):
                    value_str = ", ".join(str(item) for item in info['current_value']) if info['current_value'] else "（なし）"
                else:
                    value_str = str(info['current_value']) if info['current_value'] is not None else "（なし）"
                
                # 値が長い場合は省略
                if len(value_str) > 100:
                    value_str = value_str[:97] + "..."
                
                # 設定の説明と現在の値を表示
                embed.add_field(
                    name=f"{name}",
                    value=f"{info['description']}\n**現在の値:** {value_str}",
                    inline=False
                )
            
            embed.set_footer(text="!config <設定名> <新しい値> で設定を変更できます")
            await ctx.send(embed=embed)
        
        @self.command(name="help", help="コマンドのヘルプを表示します")
        async def help_command(ctx, command_name: str = None):
            """カスタムヘルプコマンド"""
            if command_name is None:
                # 基本的なヘルプメッセージ
                embed = discord.Embed(
                    title="スレッド自動生成Bot ヘルプ",
                    description="指定したキーワードを含むメッセージに対して自動的にスレッドを作成します。",
                    color=discord.Color.blue()
                )
                
                # コマンド一覧
                commands_list = [
                    {"name": "!config", "value": "Bot設定を表示・変更します。管理者のみ使用できます。"},
                    {"name": "!config <設定名>", "value": "特定の設定の詳細と現在の値を表示します。"},
                    {"name": "!config <設定名> <新しい値>", "value": "設定を変更します。"},
                    {"name": "!keywords", "value": "現在のトリガーキーワード一覧を表示します。"},
                    {"name": "!channels", "value": "Bot有効チャンネル一覧を表示します。"},
                    {"name": "!help", "value": "このヘルプメッセージを表示します。"},
                ]
                
                for cmd in commands_list:
                    embed.add_field(name=cmd["name"], value=cmd["value"], inline=False)
                
                # 現在の設定を表示
                keywords = ", ".join(f"`{kw}`" for kw in TRIGGER_KEYWORDS) if TRIGGER_KEYWORDS else "（なし）"
                embed.add_field(name="現在のトリガーキーワード", value=keywords, inline=False)
                
                # 管理者情報
                if self.is_admin(ctx.author):
                    embed.set_footer(text="あなたは管理者として認識されています。すべてのコマンドが使用可能です。")
                else:
                    embed.set_footer(text="管理者限定コマンドにはアクセスできません。")
                
                await ctx.send(embed=embed)
            else:
                # 特定のコマンドのヘルプ
                command = self.get_command(command_name.lower())
                if command:
                    embed = discord.Embed(
                        title=f"コマンド: {command.name}",
                        description=command.help or "説明なし",
                        color=discord.Color.blue()
                    )
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"コマンド `{command_name}` が見つかりませんでした。")
        
        @self.command(name="keywords", help="現在のトリガーキーワード一覧を表示します")
        async def keywords_command(ctx):
            """トリガーキーワード一覧を表示"""
            keywords = ", ".join(f"`{kw}`" for kw in TRIGGER_KEYWORDS) if TRIGGER_KEYWORDS else "（なし）"
            embed = discord.Embed(
                title="トリガーキーワード一覧",
                description=f"以下のキーワードを含むメッセージに対してスレッドを作成します：\n{keywords}",
                color=discord.Color.green()
            )
            
            # 管理者向けヒント
            if self.is_admin(ctx.author):
                embed.add_field(
                    name="キーワード管理（管理者用）",
                    value="`!config TRIGGER_KEYWORDS 新しいキーワード1,新しいキーワード2` でキーワードを変更できます。",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        
        @self.command(name="channels", help="Bot有効チャンネル一覧を表示します")
        async def channels_command(ctx):
            """有効チャンネル一覧を表示"""
            if not ENABLED_CHANNEL_IDS:
                embed = discord.Embed(
                    title="有効チャンネル",
                    description="すべてのチャンネルで有効です。",
                    color=discord.Color.green()
                )
            else:
                channels = []
                for channel_id in ENABLED_CHANNEL_IDS:
                    channel = self.get_channel(channel_id)
                    if channel:
                        channels.append(f"• #{channel.name} (ID: {channel.id})")
                    else:
                        channels.append(f"• 不明なチャンネル (ID: {channel_id})")
                
                embed = discord.Embed(
                    title="有効チャンネル一覧",
                    description="以下のチャンネルでのみBotが有効です：\n" + "\n".join(channels),
                    color=discord.Color.green()
                )
            
            # 管理者向けヒント
            if self.is_admin(ctx.author):
                embed.add_field(
                    name="チャンネル管理（管理者用）",
                    value="`!config ENABLED_CHANNEL_IDS チャンネルID1,チャンネルID2` でチャンネルを変更できます。\n"
                          "空にすると全チャンネルで有効になります。",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
    def is_admin(self, user: discord.User) -> bool:
        """
        ユーザーが管理者権限を持っているか確認
        
        Args:
            user: チェック対象のユーザー
            
        Returns:
            bool: 管理者権限を持っていればTrue
        """
        # 管理者IDリストが空の場合（初期設定時）はサーバー管理者を管理者とみなす
        if not ADMIN_USER_IDS:
            # ユーザーのサーバーでの権限をチェック
            # 注意: DMでの利用やBotがサーバーに入っていない場合は常にFalseを返す
            for guild in self.guilds:
                member = guild.get_member(user.id)
                if member and member.guild_permissions.administrator:
                    return True
            return False
        
        # 管理者IDリストが設定されている場合はそれを使用
        return user.id in ADMIN_USER_IDS 
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
        
        # 管理者IDの確認
        if ADMIN_USER_IDS:
            logger.info(f"管理者ユーザーID: {ADMIN_USER_IDS}")
        else:
            logger.warning("管理者ユーザーIDが設定されていません。サーバー管理者権限を持つユーザーが管理者として扱われます。")
        
        # ステータスを設定
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name="メッセージをスレッド化 | !help"
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
        
        # コマンド処理を試みる
        # これによりBotはメッセージコンテンツとしてコマンドを認識できる
        ctx = await self.get_context(message)
        if ctx.valid:
            await self.invoke(ctx)
            return
        
        # メッセージを処理
        logger.info(f"メッセージを処理します: ID={message.id}")
        await self.process_message(message)
        
    async