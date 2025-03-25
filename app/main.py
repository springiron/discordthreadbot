#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント
"""

import asyncio
import os
import signal
import sys
import traceback
from datetime import datetime

# 環境変数の読み込み
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ボットと設定をインポート
from bot.client import ThreadBot
from config import DISCORD_BOT_TOKEN as BOT_TOKEN
from utils.logger import setup_logger

# メインロガーを設定
logger = setup_logger("main")

# グローバル変数
bot_instance = None
shutdown_in_progress = False

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    global shutdown_in_progress
    
    if shutdown_in_progress:
        return
        
    shutdown_in_progress = True
    print("終了シグナルを受信しました。終了処理中...")
    logger.info("終了シグナルを受信しました。終了処理中...")
    
    # asyncioのループにタスクを入れて確実に終了するようにする
    if bot_instance and bot_instance.is_ready():
        # メインスレッドからasyncio.run()を呼べないので、
        # 既存のイベントループにタスクを投入する代替手段を使う
        asyncio.run_coroutine_threadsafe(bot_instance.close(), asyncio.get_event_loop())
    
    # 強制的にプログラム終了（バックアップ措置）
    import threading
    threading.Timer(5.0, lambda: os._exit(0)).start()


async def run_bot():
    """Botの実行と終了を管理する関数"""
    global bot_instance, shutdown_in_progress
    
    bot = ThreadBot()
    bot_instance = bot
    
    try:
        logger.info("Botを起動しています...")
        await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Bot実行中にエラーが発生しました: {e}")
        
        if not shutdown_in_progress:
            await asyncio.sleep(3)
            return True  # 再起動フラグ
    finally:
        # 終了処理
        try:
            if bot.is_ready():
                await bot.close()
        except Exception as e:
            logger.error(f"Bot終了処理中にエラーが発生しました: {e}")
    
    return False

async def main():
    """メイン関数"""
    global shutdown_in_progress
    
    # シグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # Bot起動ループ
    restart_count = 0
    max_restarts = 5  # 最大再起動回数
    
    while not shutdown_in_progress and restart_count < max_restarts:
        try:
            # Botを実行
            should_restart = await run_bot()
            
            # 再起動フラグがない場合は終了
            if not should_restart:
                break
                
            restart_count += 1
            logger.info(f"Bot再起動試行 {restart_count}/{max_restarts}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"実行中にエラーが発生しました: {e}")
            
            # 再起動を試みる
            restart_count += 1
            if restart_count < max_restarts:
                await asyncio.sleep(5)
            else:
                logger.info(f"最大再起動回数に達しました。終了します。")
                break
    
    # 終了時のクリーンアップ
    shutdown_in_progress = True

# ===============================
# Bot 実行
# ===============================
if __name__ == "__main__":
    try:
        # シンプルな起動メッセージ
        print("= Discord スレッド自動生成 Bot =")
        
        # メイン処理を実行
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムが中断されました")
    except Exception as e:
        print(f"予期しない例外が発生しました: {e}")
    finally:
        print("終了しました")