#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント
スレッド自動生成Botを起動する - 非同期ループの問題を修正
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
# 終了イベントは各関数内で作成（グローバル変数として共有しない）
restart_count = 0
MAX_RESTARTS = 5
RESTART_DELAY = 60  # 再起動間の待機時間（秒）

# キープアライブスレッドの参照を保持
keepalive_thread = None

# シグナルハンドラの状態
signal_received = False

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    global signal_received
    
    # 多重シグナル処理を防止
    if signal_received:
        logger.warning("既に終了処理中です。強制終了するにはCtrl+Cをもう一度押してください。")
        return
        
    signal_received = True
    logger.info(f"終了シグナル {signum} を受信しました。Botを正常に終了します。")
    
    # キープアライブスレッドを停止
    global keepalive_thread
    if keepalive_thread:
        logger.info("キープアライブスレッドを停止します")
        stop_keepalive()
    
    # 非同期コードからの終了はメインループで処理
    print(f"終了シグナル {signum} を受信しました。終了処理中...")
    
    # 10秒以内に終了しなければ強制終了
    import threading
    def force_exit():
        time.sleep(10)
        logger.critical("10秒以内に正常終了できませんでした。強制終了します。")
        os._exit(1)  # sys.exit()ではなくos._exit()を使用
    
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

async def run_bot(bot: ThreadBot):
    """
    Botの実行と終了を管理するシンプルな関数
    """
    try:
        logger.info("Botを起動しています...")
        await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました。Botを終了します。")
    except Exception as e:
        logger.error(f"Bot実行中にエラーが発生しました: {e}")
        logger.error(traceback.format_exc())
    finally:
        # 明示的にクローズ処理を実行
        if bot.is_ready():
            await bot.close()

async def main():
    """メイン関数 - シンプル化してイベントループの問題を回避"""
    global keepalive_thread
    
    # 終了シグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    try:
        # ロバストキープアライブ機能の開始
        if KEEP_ALIVE_ENABLED:
            logger.info(f"ロバストキープアライブ機能を有効化します (間隔: 30秒)")
            keepalive_thread = start_keepalive(
                port=PORT,
                interval=30  # 30秒固定の高頻度
            )
        else:
            logger.info("キープアライブ機能は無効化されています")
            
        # Botを初期化して実行
        bot = await initialize_bot()
        if bot:
            await run_bot(bot)
        else:
            logger.critical("Botの初期化に失敗しました。終了します。")
            
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました。終了します。")
    except Exception as e:
        logger.critical(f"致命的なエラーが発生しました: {e}")
        logger.critical(traceback.format_exc())
    finally:
        # 終了時のクリーンアップ
        if keepalive_thread:
            stop_keepalive()
            logger.info("キープアライブスレッドを停止しました")
            
        if bot_instance and bot_instance.is_ready():
            try:
                await bot_instance.close()
            except:
                pass

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
        
        # 直接実行
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムが中断されました。終了します。")
    except Exception as e:
        print(f"予期しない例外が発生しました: {e}")
        traceback.print_exc()
        sys.exit(1)