#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント
スレッド自動生成Botを起動する - ロバストキープアライブ機能を統合
"""

import asyncio
import os
import signal
import sys
import time
import traceback
from typing import Optional

# 環境変数の読み込み処理
def load_environment_variables():
    """環境変数を.envファイルまたはシステム環境変数から読み込む"""
    env_file_loaded = False
    
    # .envファイルがある場合は読み込む
    try:
        from dotenv import load_dotenv
        env_file_loaded = load_dotenv()
        if env_file_loaded:
            print(".envファイルから環境変数を読み込みました")
        else:
            print(".envファイルが見つからないか読み込めませんでした。システム環境変数を使用します")
    except ImportError:
        print("python-dotenvがインストールされていません。システム環境変数のみを使用します")
    
    # BOT_TOKENの確認
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("警告: DISCORD_BOT_TOKENが設定されていません")
    
    return env_file_loaded

# 環境変数を読み込む
load_environment_variables()

from bot.client import ThreadBot
from config import DISCORD_BOT_TOKEN as BOT_TOKEN, ENABLED_CHANNEL_IDS, KEEP_ALIVE_ENABLED, KEEP_ALIVE_INTERVAL, PORT
from utils.logger import setup_logger

# ロバストキープアライブモジュールをインポート
from utils.robust_keepalive import start_keepalive, stop_keepalive

logger = setup_logger(__name__)

# グローバル変数としてBotインスタンスを保持
bot_instance = None
exit_event = asyncio.Event()
restart_count = 0
MAX_RESTARTS = 5
RESTART_DELAY = 60  # 再起動間の待機時間（秒）

# キープアライブスレッドの参照を保持
keepalive_thread = None

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    logger.info(f"終了シグナル {signum} を受信しました。Botを正常に終了します。")
    
    # キープアライブスレッドを停止
    global keepalive_thread
    if keepalive_thread:
        logger.info("キープアライブスレッドを停止します")
        stop_keepalive()
    
    # 非同期終了イベントをセット
    if not exit_event.is_set():
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(exit_event.set)
        logger.info("非同期終了イベントをセットしました")
    
    # 10秒以内に終了しなければ強制終了
    import threading
    def force_exit():
        time.sleep(10)
        logger.critical("10秒以内に正常終了できませんでした。強制終了します。")
        sys.exit(1)
    
    threading.Thread(target=force_exit, daemon=True).start()

async def initialize_bot() -> Optional[ThreadBot]:
    """Botを初期化する"""
    global bot_instance
    
    # トークンの確認
    if not BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKENが設定されていません。.envファイルまたはKoyebの環境変数で設定してください。")
        return None
        
    # トークンの先頭部分をログに出力（セキュリティのため全てではない）
    token_preview = BOT_TOKEN[:5] + "..." if len(BOT_TOKEN) > 5 else ""
    logger.info(f"BOT_TOKEN: {token_preview}")
    
    # 有効なチャンネルの設定を確認
    if ENABLED_CHANNEL_IDS:
        logger.info(f"有効なチャンネルIDが {len(ENABLED_CHANNEL_IDS)} 件設定されています")
    else:
        logger.warning("有効なチャンネルIDが設定されていません。すべてのチャンネルで動作します。")
    
    # Botインスタンスを作成
    bot_instance = ThreadBot()
    return bot_instance

async def start_bot(bot: ThreadBot) -> bool:
    """Botを起動し、適切に終了する"""
    try:
        logger.info("Botを起動しています...")
        # ボットを起動しつつ、終了イベントを待機
        bot_task = asyncio.create_task(bot.start(BOT_TOKEN))
        exit_task = asyncio.create_task(exit_event.wait())
        
        # いずれかのタスクが完了するまで待機
        done, pending = await asyncio.wait(
            [bot_task, exit_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # 残りのタスクをキャンセル
        for task in pending:
            task.cancel()
            
        # 終了イベントが発火した場合
        if exit_task in done:
            logger.info("終了イベントを検知しました。Botを正常に終了します。")
            await bot.close()
            return False
            
        # ボットが何らかの理由で終了した場合
        if bot_task in done:
            try:
                # 例外が発生したかチェック
                bot_task.result()
                logger.info("Botが正常に終了しました。")
                return False
            except Exception as e:
                logger.error(f"Bot実行中にエラーが発生しました: {e}")
                logger.error(traceback.format_exc())
                return True  # 再起動が必要
                
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました。Botを終了します。")
        await bot.close()
        return False
    except Exception as e:
        logger.error(f"予期しないエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
        if bot and bot.is_ready():
            await bot.close()
        return True  # 再起動が必要

async def main_with_restart():
    """リトライ機能付きのメイン関数"""
    global restart_count, keepalive_thread
    
    # ロバストキープアライブ機能の開始
    if KEEP_ALIVE_ENABLED:
        logger.info(f"ロバストキープアライブ機能を有効化します (間隔: 30秒)")
        # 分から秒に変換せず、30秒固定の高頻度で実行
        keepalive_thread = start_keepalive(
            port=PORT,
            interval=30  # 30秒固定の高頻度
        )
    else:
        logger.info("キープアライブ機能は無効化されています")
    
    while restart_count < MAX_RESTARTS and not exit_event.is_set():
        if restart_count > 0:
            logger.warning(f"Botを再起動しています... (試行: {restart_count}/{MAX_RESTARTS})")
            await asyncio.sleep(RESTART_DELAY)
        
        bot = await initialize_bot()
        if not bot:
            logger.critical("Botの初期化に失敗しました。終了します。")
            break
            
        should_restart = await start_bot(bot)
        if not should_restart:
            break
            
        restart_count += 1
        logger.warning(f"残り再起動回数: {MAX_RESTARTS - restart_count}")
    
    # 最大再起動回数に達した場合
    if restart_count >= MAX_RESTARTS:
        logger.critical(f"最大再起動回数 ({MAX_RESTARTS}回) に達しました。終了します。")
    
    # キープアライブスレッドを停止
    if keepalive_thread:
        stop_keepalive()
        logger.info("キープアライブスレッドを停止しました")

async def main():
    """メイン関数"""
    # 終了シグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    try:
        await main_with_restart()
    except Exception as e:
        logger.critical(f"致命的なエラーが発生しました: {e}")
        logger.critical(traceback.format_exc())
        
        # 終了前の最終クリーンアップ
        if keepalive_thread:
            stop_keepalive()
        if bot_instance and bot_instance.is_ready():
            await bot_instance.close()
        
        sys.exit(1)

# ===============================
# Bot 実行
# ===============================
if __name__ == "__main__":
    try:
        # コンソールに起動メッセージを表示
        print("=" * 60)
        print("Discord スレッド自動生成Bot - ロバストキープアライブ機能付き")
        print("=" * 60)
        print("Ctrl+Cで終了できます")
        print("=" * 60)
        
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("プログラムが中断されました。終了します。")
    except Exception as e:
        logger.critical(f"予期しない例外が発生しました: {e}")
        logger.critical(traceback.format_exc())
        sys.exit(1)