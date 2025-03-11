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

# .envファイルがある場合は読み込む
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from bot.client import ThreadBot
from config import BOT_TOKEN, ENABLED_CHANNEL_IDS, KEEP_ALIVE_ENABLED, KEEP_ALIVE_INTERVAL
from utils.logger import setup_logger
from utils.keep_alive import KeepAlive

logger = setup_logger(__name__)
# キープアライブインスタンスをグローバル変数として保持
keep_alive_instance = None

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    logger.info("終了シグナルを受信しました。Botを正常に終了します。")
    # キープアライブを停止
    global keep_alive_instance
    if keep_alive_instance:
        keep_alive_instance.stop()
    sys.exit(0)

async def main():
    """メイン関数"""
    # 終了シグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # トークンの確認
    if not BOT_TOKEN:
        logger.error("BOT_TOKENが設定されていません。環境変数を確認してください。")
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
    global keep_alive_instance
    if KEEP_ALIVE_ENABLED:
        logger.info(f"キープアライブ機能を有効化します (間隔: {KEEP_ALIVE_INTERVAL}分)")
        keep_alive_instance = KeepAlive(interval_minutes=KEEP_ALIVE_INTERVAL)
        keep_alive_instance.start()
    else:
        logger.info("キープアライブ機能は無効化されています")
    
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
        # Botが終了する際にキープアライブも停止
        if keep_alive_instance:
            keep_alive_instance.stop()

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