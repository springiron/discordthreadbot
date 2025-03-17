#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント
スレッド自動生成Botを起動する
"""

import asyncio
import os
import signal
import sys

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
from config import BOT_TOKEN, ENABLED_CHANNEL_IDS, KEEP_ALIVE_ENABLED, KEEP_ALIVE_INTERVAL
from utils.logger import setup_logger
from utils.keep_alive import KeepAlive
from utils.health_check import HealthCheckServer

logger = setup_logger(__name__)
# グローバル変数としてインスタンスを保持
keep_alive_instance = None
health_check_server = None

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    logger.info("終了シグナルを受信しました。Botを正常に終了します。")
    # キープアライブとヘルスチェックサーバーを停止
    global keep_alive_instance, health_check_server
    if keep_alive_instance:
        keep_alive_instance.stop()
    if health_check_server:
        health_check_server.stop()
    sys.exit(0)

async def main():
    """メイン関数"""
    # 終了シグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # トークンの確認
    if not BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKENが設定されていません。.envファイルまたはKoyebの環境変数で設定してください。")
        return
        
    # トークンの先頭部分をログに出力（セキュリティのため全てではない）
    token_preview = BOT_TOKEN[:5] + "..." if len(BOT_TOKEN) > 5 else ""
    logger.info(f"BOT_TOKEN: {token_preview}")
    
    # 有効なチャンネルの設定を確認
    if ENABLED_CHANNEL_IDS:
        logger.info(f"有効なチャンネルIDが {len(ENABLED_CHANNEL_IDS)} 件設定されています")
    else:
        logger.warning("有効なチャンネルIDが設定されていません。すべてのチャンネルで動作します。")
    
    # キープアライブ機能の開始
    global keep_alive_instance, health_check_server
    if KEEP_ALIVE_ENABLED:
        logger.info(f"キープアライブ機能を有効化します (間隔: {KEEP_ALIVE_INTERVAL}分)")
        keep_alive_instance = KeepAlive(interval_minutes=KEEP_ALIVE_INTERVAL)
        keep_alive_instance.start()
    else:
        logger.info("キープアライブ機能は無効化されています")
        
    # ヘルスチェックサーバーの開始
    health_check_server = HealthCheckServer(port=8080)
    health_check_server.start()
    
    # Botインスタンスを作成
    bot = ThreadBot()
    
    try:
        logger.info("Botを起動しています...")
        await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("キーボード割り込みを検知しました。Botを終了します。")
        await bot.close()
    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        await bot.close()
        raise
    finally:
        # Botが終了する際にキープアライブとヘルスチェックサーバーも停止
        if keep_alive_instance:
            keep_alive_instance.stop()
        if health_check_server:
            health_check_server.stop()

if __name__ == "__main__":
    # Python 3.10以降はasyncio.runを使用
    if sys.version_info >= (3, 10):
        asyncio.run(main())
    else:
        # Python 3.9以前はevent loopを取得して実行
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(main())
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()