#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント - 最適化版
キープアライブの統合実装例
"""

import asyncio
import os
import signal
import sys
import time
import traceback

# 環境変数の読み込み処理
def load_environment_variables():
    """環境変数を.envファイルまたはシステム環境変数から読み込む"""
    try:
        from dotenv import load_dotenv
        loaded = load_dotenv()
        if loaded:
            print(".envファイルから環境変数を読み込みました")
    except ImportError:
        print("python-dotenvがインストールされていません。システム環境変数のみを使用します")
    
    # BOT_TOKENの確認
    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        print("警告: DISCORD_BOT_TOKENが設定されていません")

# 環境変数を読み込む
load_environment_variables()

# ボットと設定をインポート
from bot.client import ThreadBot
from config import DISCORD_BOT_TOKEN as BOT_TOKEN, ENABLED_CHANNEL_IDS

# 最適化されたキープアライブモジュールをインポート
from utils.ultimate_keepalive import start_keepalive, stop_keepalive

# シグナルハンドラの状態
signal_received = False

# キープアライブスレッドの参照
keepalive_thread = None

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    global signal_received
    
    # 多重シグナル処理を防止
    if signal_received:
        print("既に終了処理中です。強制終了するにはCtrl+Cをもう一度押してください。")
        return
        
    signal_received = True
    print(f"終了シグナル {signum} を受信しました。終了処理中...")
    
    # キープアライブスレッドを停止
    global keepalive_thread
    if keepalive_thread:
        print("キープアライブスレッドを停止します")
        stop_keepalive()
    
    # 10秒後に強制終了するタイマーを設定
    import threading
    def force_exit():
        time.sleep(10)
        print("10秒以内に正常終了できませんでした。強制終了します。")
        os._exit(1)  # 確実に終了するためにos._exit()を使用
    
    threading.Thread(target=force_exit, daemon=True).start()

async def run_bot():
    """Botの実行と終了を管理するシンプルな関数"""
    bot = ThreadBot()
    
    try:
        print("Botを起動しています...")
        await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        print("キーボード割り込みを検知しました。Botを終了します。")
    except Exception as e:
        print(f"Bot実行中にエラーが発生しました: {e}")
        traceback.print_exc()
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
        # キープアライブ機能を開始（30秒間隔）
        print("キープアライブ機能を有効化します (間隔: 30秒)")
        keepalive_thread = start_keepalive(interval=30)
            
        # Botを実行
        await run_bot()
            
    except KeyboardInterrupt:
        print("キーボード割り込みを検知しました。終了します。")
    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")
        traceback.print_exc()
    finally:
        # 終了時のクリーンアップ
        if keepalive_thread:
            stop_keepalive()
            print("キープアライブスレッドを停止しました")

# ===============================
# Bot 実行
# ===============================
if __name__ == "__main__":
    try:
        # 起動メッセージを表示
        print("=" * 60)
        print("Discord Bot - 最適化キープアライブ機能付き")
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