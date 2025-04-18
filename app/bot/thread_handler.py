#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
スレッド生成と管理のロジック
"""

import discord
from discord.ui import Button, View
from typing import List, Optional, Dict
import re
import asyncio
import time
from datetime import datetime, timedelta

from utils.logger import setup_logger
from config import DEBUG_MODE

# スプレッドシートロガーをインポート（遅延インポート）
def get_spreadsheet_logger():
    """スプレッドシートロガーを取得（遅延インポート）"""
    try:
        from bot.spreadsheet_logger import log_thread_creation, log_thread_close
        return log_thread_creation, log_thread_close
    except ImportError:
        logger.warning("スプレッドシートロガーモジュールがインポートできませんでした")
        # ダミー関数を返す
        dummy = lambda *args, **kwargs: False
        return dummy, dummy
    

logger = setup_logger(__name__)

# スレッド監視状態を追跡するディクショナリ
# キー：スレッドID、値：監視タスク
monitored_threads: Dict[int, asyncio.Task] = {}

# スレッド作成者を追跡するディクショナリ
thread_creators = {}  # キー: スレッドID、値: 作成者のユーザーID

# デバッグ情報を保持する辞書
# キー：スレッドID、値：{'created_at': タイムスタンプ, 'end_time': 監視終了タイムスタンプ}
thread_debug_info: Dict[int, Dict] = {}

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
    if at_number_pattern.search(message.clean_content):
        return True
    
    # メッセージ内容にトリガーキーワードが含まれるかチェック
    for keyword in trigger_keywords:
        # 大文字小文字を区別せずにキーワードを検索
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        if pattern.search(message.clean_content):
            return True
    
    return False

def should_close_thread(message: discord.Message, close_keywords: List[str]) -> bool:
    """
    メッセージがスレッド締め切り条件を満たすかチェック
    
    Args:
        message: チェック対象のDiscordメッセージ
        close_keywords: 締め切りトリガーとなるキーワードのリスト
        
    Returns:
        bool: スレッドを締め切るべき場合はTrue
    """
    # メッセージ内容が空の場合は無視
    if not message.content:
        return False
    
    # メッセージ内容に締め切りキーワードが含まれるかチェック
    for keyword in close_keywords:
        # 大文字小文字を区別せずにキーワードを検索
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        if pattern.search(message.content):
            return True
    
    return False

async def create_thread_from_message(
    message: discord.Message, 
    name: str, 
    auto_archive_duration: int = 10080,
    monitoring_duration: int = 43200,
    close_keywords: List[str] = [],
    closed_name_template: str = "[募集締切] {original_name}",
    bot = None
) -> Optional[discord.Thread]:
    """
    メッセージからスレッドを作成し、監視を開始
    
    Args:
        message: スレッド作成元のDiscordメッセージ
        name: スレッド名
        auto_archive_duration: 自動アーカイブ時間（分）
        monitoring_duration: 監視時間（分）
        close_keywords: 締め切りトリガーキーワード
        closed_name_template: 締め切り後のスレッド名テンプレート
        bot: Discordボットインスタンス（client.pyから渡される）
        
    Returns:
        Optional[discord.Thread]: 作成されたスレッド。失敗した場合はNone
    """
    try:
        # auto_archive_durationとmonitoring_durationが文字列なら整数に変換
        if isinstance(auto_archive_duration, str):
            try:
                auto_archive_duration = int(auto_archive_duration)
            except ValueError:
                logger.error(f"無効なauto_archive_duration値: {auto_archive_duration}、デフォルト値の10080を使用します")
                auto_archive_duration = 10080
                
        # Discord APIが許可する有効な値のみを使用（60, 1440, 4320, 10080）
        valid_archive_durations = [60, 1440, 4320, 10080]
        if auto_archive_duration not in valid_archive_durations:
            # 最も近い有効な値を選択
            auto_archive_duration = min(valid_archive_durations, key=lambda x: abs(x - auto_archive_duration))
            logger.info(f"auto_archive_durationを有効な値 {auto_archive_duration} に調整しました")
                
        if isinstance(monitoring_duration, str):
            try:
                monitoring_duration = int(monitoring_duration)
            except ValueError:
                logger.error(f"無効なmonitoring_duration値: {monitoring_duration}、デフォルト値の43200を使用します")
                monitoring_duration = 43200
          
        # スレッド作成を試みる
        thread = await message.create_thread(
            name=name,
            auto_archive_duration=auto_archive_duration
        )
        
        logger.info(f"スレッド '{name}' を作成しました (ID: {thread.id})")
        
        # スレッド作成者情報を保存
        thread_creators[thread.id] = message.author.id

        # スプレッドシートにログ記録（非同期・非ブロッキング）
        try:
            # スプレッドシートロガーを取得（遅延インポート）
            log_thread_creation, _ = get_spreadsheet_logger()
            
            # ログを記録（キューに追加するだけなのでブロッキングしない）
            log_result = log_thread_creation(
                user_id=message.author.id,
                username=message.author.display_name
            )
            
            if log_result:
                logger.debug(f"スレッド作成ログをキューに追加しました: ID={thread.id}, ユーザー={message.author.display_name}")
            
        except Exception as e:
            logger.error(f"スプレッドシートログ記録エラー: {e}")

        logger.info(f"スレッド作成者情報を保存しました: スレッドID={thread.id}, 作成者ID={message.author.id}")
        
        # 締め切りボタンを含むメッセージを送信
        try:
            # ボタンビューを作成 - 作成者IDも渡す
            view = CloseThreadView(thread.id, closed_name_template, message.author.id)
            
            # メッセージを送信
            await thread.send(
                content="このスレッドは自動作成されました。募集を締め切る場合は下のボタンを押してください。",
                view=view
            )
            logger.info(f"スレッド '{name}' (ID: {thread.id}) に締め切りボタンを送信しました")
        except Exception as e:
            logger.error(f"締め切りボタン送信エラー: {e}")
        
        # デバッグ情報を設定
        if DEBUG_MODE:
            created_at = time.time()
            end_monitoring_time = created_at + (monitoring_duration * 60)
            thread_debug_info[thread.id] = {
                'created_at': created_at,
                'end_monitoring_time': end_monitoring_time,
                'auto_archive_duration': auto_archive_duration,
                'name': name,
                'author': message.author.display_name,
                'author_id': message.author.id,  # 作成者IDも保存
                'monitoring_duration': monitoring_duration
            }
            
            # デバッグ情報をログに出力
            logger.debug(f"スレッド作成デバッグ情報: ID={thread.id}, 作成者={message.author.display_name}, "
                        f"作成者ID={message.author.id}, "
                        f"アーカイブ時間={auto_archive_duration}分, 監視時間={monitoring_duration}分")
        
        # スレッド監視タスクを開始
        if monitoring_duration > 0 and bot is not None:
            # 監視タスクを開始
            monitor_task = asyncio.create_task(
                monitor_thread(
                    bot=bot,
                    thread=thread,
                    monitoring_duration=monitoring_duration,
                    close_keywords=close_keywords,
                    closed_name_template=closed_name_template
                )
            )
            # タスクを監視リストに追加
            monitored_threads[thread.id] = monitor_task
            logger.info(f"スレッド '{name}' (ID: {thread.id}) の監視を開始しました（監視時間: {monitoring_duration}分）")
        
        return thread
        
    except discord.Forbidden:
        logger.error(f"スレッド作成に必要な権限がありません: チャンネル={message.channel.name}")
        
    except discord.HTTPException as e:
        logger.error(f"スレッド作成中にHTTPエラーが発生しました: {e.status}/{e.code}")
        
    except Exception as e:
        logger.error(f"スレッド作成中にエラーが発生しました: {e}")
    
    return None

async def close_thread(
    thread: discord.Thread, 
    closed_name_template: str
) -> bool:
    """
    スレッドを締め切る（スレッド名を変更）
    
    Args:
        thread: 対象のスレッド
        closed_name_template: 締め切り後のスレッド名テンプレート
        
    Returns:
        bool: 成功した場合はTrue
    """
    try:
        # 元のスレッド名
        original_name = thread.name
        
        # 「[✅ 募集中]」タグが含まれている場合は除去
        # 正規表現を使用して柔軟に対応
        import re
        recruitment_tag_pattern = re.compile(r'\[✅\s*募集中\]')
        clean_name = recruitment_tag_pattern.sub('', original_name).strip()
        
        # 新しいスレッド名を生成
        new_name = closed_name_template.format(original_name=clean_name)
        
        # もし新しい名前が長すぎる場合は切り詰める（Discordの制限は100文字）
        if len(new_name) > 100:
            logger.warning(f"生成されたスレッド名が長すぎるため切り詰めます: {new_name}")
            new_name = new_name[:97] + "..."
        
        # スレッド名を変更
        await thread.edit(name=new_name)
        
        # スレッド作成者情報を削除（スレッドが閉じられたため）
        if thread.id in thread_creators:
            del thread_creators[thread.id]
            
            # スプレッドシートにログ記録（非同期・非ブロッキング）
            try:
                # スレッド作成者情報があれば、その情報でログを残す
                author_id = thread_creators.get(thread.id)
                if author_id:
                    # スレッド作成者のユーザーオブジェクトを取得
                    guild = thread.guild
                    if guild:
                        member = guild.get_member(author_id)
                        if member:
                            username = member.display_name
                            # スプレッドシートロガーを取得（遅延インポート）
                            _, log_thread_close = get_spreadsheet_logger()
                            
                            # ログを記録（キューに追加するだけなのでブロッキングしない）
                            log_result = log_thread_close(
                                user_id=author_id,  # ユーザーIDを追加
                                username=username
                            )
                            
                            if log_result:
                                logger.debug(f"スレッド締め切りログをキューに追加しました: ID={thread.id}, ユーザー={username}")
            except Exception as e:
                logger.error(f"スプレッドシートログ記録エラー: {e}")
            logger.info(f"スレッド '{original_name}' (ID: {thread.id}) の作成者情報を削除しました")
        
        logger.info(f"スレッド名を変更しました: '{original_name}' → '{new_name}' (ID: {thread.id})")
        return True
        
    except discord.Forbidden:
        logger.error(f"スレッド名変更に必要な権限がありません: スレッド={thread.name}")
        
    except discord.HTTPException as e:
        logger.error(f"スレッド名変更中にHTTPエラーが発生しました: {e.status}/{e.code}")
        
    except Exception as e:
        logger.error(f"スレッド名変更中にエラーが発生しました: {e}")
    
    return False

async def monitor_thread(
    bot: discord.Client,
    thread: discord.Thread,
    monitoring_duration: int,
    close_keywords: List[str],
    closed_name_template: str
) -> None:
    """
    スレッドを監視し、必要に応じてスレッド名を変更
    
    Args:
        bot: Discordボットインスタンス
        thread: 監視対象のスレッド
        monitoring_duration: 監視時間（分）
        close_keywords: 締め切りトリガーキーワード
        closed_name_template: 締め切り後のスレッド名テンプレート
    """
    thread_id = thread.id
    is_closed = False
    
    try:
        # スレッドが見つからない場合は終了
        if not thread:
            logger.warning(f"監視対象のスレッド（ID: {thread_id}）が見つかりません")
            return
            
        logger.info(f"スレッド '{thread.name}' (ID: {thread_id}) の監視を開始しました")
        
        # 監視終了時間 (秒)
        end_time = asyncio.get_event_loop().time() + (monitoring_duration * 60)
        
        # デバッグモードでログ間隔 (デフォルト30分ごと)
        debug_log_interval = 30 * 60  # 30分
        next_debug_log = asyncio.get_event_loop().time() + debug_log_interval
        
        # 監視ループ
        while asyncio.get_event_loop().time() < end_time:
            # デバッグモードの場合、定期的にステータスをログ出力
            current_time = asyncio.get_event_loop().time()
            if DEBUG_MODE and current_time >= next_debug_log:
                # スレッド情報を更新
                try:
                    refreshed_thread = await bot.fetch_channel(thread_id)
                    if refreshed_thread and isinstance(refreshed_thread, discord.Thread):
                        thread = refreshed_thread
                        
                        # アーカイブまでの残り時間（分）を計算
                        archive_timestamp = thread.archive_timestamp
                        if archive_timestamp:
                            now = datetime.now()
                            archive_time = archive_timestamp.replace(tzinfo=None)
                            if archive_time > now:
                                minutes_to_archive = int((archive_time - now).total_seconds() / 60)
                                
                                # 残り監視時間（分）を計算
                                minutes_to_end_monitoring = int((end_time - current_time) / 60)
                                
                                # ログ出力
                                logger.debug(
                                    f"スレッド監視中: '{thread.name}' (ID: {thread_id}), "
                                    f"アーカイブまで残り {minutes_to_archive}分, "
                                    f"監視終了まで残り {minutes_to_end_monitoring}分"
                                )
                except Exception as e:
                    logger.debug(f"スレッド情報取得エラー (ID: {thread_id}): {e}")
                
                # 次のログ出力時間を設定
                next_debug_log = current_time + debug_log_interval
            
            # スレッドが存在しなくなった場合は終了
            try:
                # fetch_channelでスレッドの状態を更新
                refreshed_thread = await bot.fetch_channel(thread_id)
                if not refreshed_thread or not isinstance(refreshed_thread, discord.Thread):
                    logger.warning(f"監視対象のスレッド（ID: {thread_id}）が存在しなくなりました")
                    return
                
                # スレッドがアーカイブされていたら終了
                if refreshed_thread.archived:
                    logger.info(f"スレッド '{refreshed_thread.name}' (ID: {thread_id}) はアーカイブされています")
                    return
                
                # 更新されたスレッドオブジェクトを使用
                thread = refreshed_thread
                
            except (discord.NotFound, discord.HTTPException):
                logger.warning(f"監視対象のスレッド（ID: {thread_id}）が見つかりません")
                return
            
            # スレッドがすでに締め切り状態かチェック
            if closed_name_template.format(original_name="") in thread.name:
                is_closed = True
            
            # 一定時間待機 (10分ごとにチェック)
            try:
                await asyncio.sleep(600)  # 10分待機
            except asyncio.CancelledError:
                logger.info(f"スレッド '{thread.name}' (ID: {thread_id}) の監視が中断されました")
                break
                
        # 監視時間終了
        logger.info(f"スレッド '{thread.name}' (ID: {thread_id}) の監視時間が終了しました")
            
    except Exception as e:
        logger.error(f"スレッド監視中にエラーが発生しました (ID: {thread_id}): {e}")
    
    finally:
        # タスク終了時の処理
        try:
            # スレッドが存在する場合のみ
            if thread:
                # モニタリング時間終了による締め切り
                # まずスレッドがまだ締め切られていないことを確認
                close_marker = closed_name_template.format(original_name="").strip()
                if not (close_marker and close_marker in thread.name):
                    # スレッド名を変更
                    await close_thread(thread, closed_name_template)
                    logger.info(f"スレッド '{thread.name}' (ID: {thread_id}) のモニタリング時間終了により締め切りました")
                
                # まだスレッドに参加中なら退出
                try:                 
                    # スレッドからBotを退出
                    await thread.leave()
                    logger.info(f"スレッド '{thread.name}' (ID: {thread_id}) から退出しました")
                except:
                    pass
            
            # 監視リストから削除
            if thread_id in monitored_threads:
                del monitored_threads[thread_id]
                
            # デバッグ情報から削除
            if thread_id in thread_debug_info:
                del thread_debug_info[thread_id]
                
        except Exception as e:
            logger.error(f"スレッド監視終了処理でエラーが発生しました (ID: {thread_id}): {e}")

async def process_thread_message(
    message: discord.Message,
    close_keywords: List[str],
    closed_name_template: str
) -> None:
    """
    スレッド内のメッセージを処理
    
    Args:
        message: 処理対象のDiscordメッセージ
        close_keywords: 締め切りトリガーキーワード
        closed_name_template: 締め切り後のスレッド名テンプレート
    """
    # スレッドでない場合は無視
    if not isinstance(message.channel, discord.Thread):
        return
        
    thread = message.channel
    
    # 締め切りマーカーに基づいて、すでに締め切られているか確認
    import re
    close_marker = closed_name_template.format(original_name="").strip()
    if close_marker and close_marker in thread.name:
        return
    
    # 締め切りキーワードが含まれているかチェック
    if should_close_thread(message, close_keywords):
        # スレッド作成者IDを取得
        creator_id = thread_creators.get(thread.id)
        
        # 作成者のみが締め切れるようにする
        if creator_id and creator_id != message.author.id:
            logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) で締め切りキーワードを検出しましたが、"
                      f"作成者(ID:{creator_id})以外のユーザー(ID:{message.author.id})からのため無視します")
            return

        logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) で締め切りキーワードを検出しました")
        
        # スレッドを締め切る
        success = await close_thread(thread, closed_name_template)
        
        if success:            
            # 監視タスクを終了
            if thread.id in monitored_threads:
                monitored_threads[thread.id].cancel()
                del monitored_threads[thread.id]
                logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) の監視を終了しました（キーワードによる締め切り）")
                
            # スレッドからBotを退出
            try:
                await thread.leave()
                logger.info(f"スレッド '{thread.name}' (ID: {thread.id}) から退出しました（キーワードによる締め切り）")
            except Exception as e:
                logger.error(f"スレッド退出処理でエラーが発生しました (ID: {thread.id}): {e}")

def get_monitored_threads_status():
    """
    現在監視中のスレッドの状態を取得
    
    Returns:
        dict: スレッドIDをキーとする状態情報
    """
    current_time = time.time()
    status = {}
    
    for thread_id, info in thread_debug_info.items():
        if thread_id in monitored_threads:
            # 監視終了までの残り時間を計算
            remaining_monitoring = max(0, int((info['end_monitoring_time'] - current_time) / 60))
            
            status[thread_id] = {
                'name': info['name'],
                'author': info['author'],
                'created_at': datetime.fromtimestamp(info['created_at']).strftime('%Y-%m-%d %H:%M:%S'),
                'monitoring_remaining_minutes': remaining_monitoring,
                'auto_archive_duration': info['auto_archive_duration']
            }
    
    return status


# ボタンクラスとビュー
class CloseThreadButton(Button):
    """スレッド締め切りボタン"""
    
    def __init__(self, thread_id: int, closed_name_template: str, creator_id: int = None):
        """
        ボタンの初期化
        
        Args:
            thread_id: 対象スレッドのID
            closed_name_template: 締め切り後のスレッド名テンプレート
            creator_id: スレッド作成者のユーザーID
        """
        super().__init__(
            style=discord.ButtonStyle.danger,  # 赤色のボタン
            label="募集を締め切る",
            # 〆切りボタンの絵文字
            emoji="🔒",
            custom_id=f"close_thread_{thread_id}"
        )
        self.thread_id = thread_id
        self.closed_name_template = closed_name_template
        self.creator_id = creator_id  # 作成者IDを保存
        
    async def callback(self, interaction: discord.Interaction):
        """ボタンクリック時のコールバック"""
        # スレッドを取得
        thread = interaction.channel
        
        if not isinstance(thread, discord.Thread) or thread.id != self.thread_id:
            await interaction.response.send_message("⚠️ このボタンは現在のスレッドでは使用できません", ephemeral=True)
            return
            
        # すでに締め切られているか確認
        if self.closed_name_template.format(original_name="") in thread.name:
            await interaction.response.send_message("⚠️ このスレッドはすでに締め切られています", ephemeral=True)
            return
            
        # 作成者IDを取得（ボタンに保存されていない場合はグローバル辞書から取得）
        creator_id = self.creator_id if self.creator_id else thread_creators.get(thread.id)
        
        # 作成者以外のユーザーからのリクエストを拒否
        if creator_id and interaction.user.id != creator_id:
            await interaction.response.send_message(
                "⚠️ スレッドを締め切れるのはスレッドの作成者のみです", 
                ephemeral=True
            )
            logger.info(f"作成者(ID:{creator_id})以外のユーザー(ID:{interaction.user.id})による"
                      f"スレッド '{thread.name}' (ID: {thread.id}) の締め切り操作を拒否しました")
            return
            
        # スレッドを締め切る
        try:
            # 元のスレッド名を保存
            original_name = thread.name
            
            # 「[✅ 募集中]」タグの除去（正規表現を使用）
            import re
            recruitment_tag_pattern = re.compile(r'\[✅\s*募集中\]')
            clean_name = recruitment_tag_pattern.sub('', original_name).strip()
            
            # 新しいスレッド名を生成
            new_name = self.closed_name_template.format(original_name=clean_name)
            
            # スレッド名を変更
            await thread.edit(name=new_name)
            
            # 応答を送信
            await interaction.response.send_message(f"✅ 募集を締め切りました")
            
            # 親メッセージ（募集メッセージ）にリアクションを追加
            try:
                # スレッドの親メッセージを取得
                starter_message = thread.starter_message
                
                # starter_messageがNoneの場合、メッセージを取得（Discord APIの制限でNoneになる場合がある）
                if starter_message is None:
                    # スレッドの開始メッセージIDを取得
                    if hasattr(thread, 'id') and hasattr(thread, 'parent') and hasattr(thread, 'starter_message_id'):
                        # 親チャンネルからメッセージを取得
                        try:
                            starter_message = await thread.parent.fetch_message(thread.starter_message_id)
                        except (discord.NotFound, discord.HTTPException, AttributeError) as e:
                            logger.warning(f"親メッセージの取得に失敗しました: {e}")
                
                # リアクションを追加
                if starter_message:
                    # 締め切りを示すリアクション絵文字
                    closed_emoji = "⛔"  # 鍵の絵文字
                    
                    # リアクションを追加
                    await starter_message.add_reaction(closed_emoji)
                    logger.info(f"募集メッセージ (ID: {starter_message.id}) に締め切りリアクション {closed_emoji} を追加しました")
                else:
                    logger.warning(f"親メッセージが見つからないため、リアクションを追加できませんでした (Thread ID: {thread.id})")
            except Exception as e:
                logger.error(f"リアクション追加エラー: {e}")
            
            # ログに記録
            logger.info(f"ボタンによるスレッド名変更: '{original_name}' → '{new_name}' (ID: {thread.id}, "
                        f"実行者: {interaction.user.display_name})")
            
            # ボタンを非アクティブ化
            self.disabled = True
            self.label = "締め切り済み"
            await interaction.message.edit(view=self.view)
            
            # 監視タスクを終了（オプション）
            if thread.id in monitored_threads:
                monitored_threads[thread.id].cancel()
                del monitored_threads[thread.id]
                logger.info(f"スレッド '{new_name}' (ID: {thread.id}) の監視を終了しました（ボタンによる締め切り）")
                
            # スレッドからBotを退出（オプション）
            try:
                await thread.leave()
                logger.info(f"スレッド '{new_name}' (ID: {thread.id}) から退出しました（ボタンによる締め切り）")
            except Exception as e:
                logger.error(f"スレッド退出処理でエラーが発生しました (ID: {thread.id}): {e}")
                
        except Exception as e:
            # エラー応答
            await interaction.response.send_message(f"❌ エラーが発生しました: {e}", ephemeral=True)
            logger.error(f"ボタンによるスレッド名変更エラー (ID: {thread.id}): {e}")


class CloseThreadView(View):
    """スレッド締め切りボタンを含むビュー"""
    
    def __init__(self, thread_id: int, closed_name_template: str, creator_id: int = None):
        """
        ビューの初期化
        
        Args:
            thread_id: 対象スレッドのID
            closed_name_template: 締め切り後のスレッド名テンプレート
            creator_id: スレッド作成者のユーザーID
        """
        super().__init__(timeout=None)  # タイムアウトなし（ボタンは永続的）
        
        # ボタンを追加 - 作成者IDも渡す
        self.add_item(CloseThreadButton(thread_id, closed_name_template, creator_id))


async def cleanup_thread_data():
    """スレッド関連のデータをクリーンアップ"""
    global thread_creators, monitored_threads, thread_debug_info
    
    try:
        # スレッド作成者情報をクリア
        thread_creators.clear()
        
        # 他のデータもクリア
        monitored_threads.clear()
        thread_debug_info.clear()
        
        logger.info("スレッドデータがクリーンアップされました")
    except Exception as e:
        logger.error(f"スレッドデータのクリーンアップ中にエラーが発生しました: {e}")