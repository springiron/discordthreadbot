#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント - 改良版
改良されたキープアライブ機構と安定性の向上
"""

import asyncio
import os
import signal
import sys
import time
import traceback
from datetime import datetime

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
from config import (
    DISCORD_BOT_TOKEN as BOT_TOKEN,
    ENABLED_CHANNEL_IDS,
    KEEP_ALIVE_ENABLED,
    KEEP_ALIVE_INTERVAL,
    PORT,
    DEBUG_MODE
)

# 改良されたモジュールをインポート
from utils.improved_keepalive import start_keepalive, stop_keepalive
from utils.improved_http_server import server_thread

# シグナルハンドラとシャットダウン管理のための状態変数
signal_received = False
bot_instance = None
keepalive_thread = None
http_server_thread = None
shutdown_in_progress = False
start_time = datetime.now()
instance_id = os.environ.get('INSTANCE_ID', f"{int(time.time())}")

# ステータスファイル定義
STATUS_FILE = "/tmp/discord_bot_status.txt"

def update_status_file(status):
    """ステータスファイルを更新"""
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(f"{status}\n")
            f.write(f"更新時刻: {datetime.now().isoformat()}\n")
            f.write(f"起動時刻: {start_time.isoformat()}\n")
            uptime = datetime.now() - start_time
            f.write(f"稼働時間: {uptime}\n")
    except Exception as e:
        print(f"ステータスファイル更新エラー: {e}")

def handle_exit(signum, frame):
    """終了シグナルを適切に処理する"""
    global signal_received, shutdown_in_progress
    
    signals = {
        signal.SIGINT: "SIGINT",
        signal.SIGTERM: "SIGTERM",
        signal.SIGHUP: "SIGHUP"
    }
    sig_name = signals.get(signum, f"Signal {signum}")
    
    # 多重シグナル処理を防止
    if shutdown_in_progress:
        print(f"既に終了処理中です。強制終了するにはCtrl+Cをもう一度押してください。（シグナル: {sig_name}）")
        return
        
    shutdown_in_progress = True
    signal_received = True
    print(f"終了シグナル {sig_name} を受信しました。終了処理中...")
    update_status_file(f"終了中 - {sig_name}受信")
    
    # キープアライブスレッドを停止
    global keepalive_thread
    if keepalive_thread:
        print("キープアライブスレッドを停止します")
        try:
            stop_keepalive()
        except Exception as e:
            print(f"キープアライブ停止エラー: {e}")
    
    # 10秒後に強制終了するタイマーを設定
    import threading
    def force_exit():
        time.sleep(10)
        print("10秒以内に正常終了できませんでした。強制終了します。")
        update_status_file("強制終了")
        os._exit(1)  # 確実に終了するためにos._exit()を使用
    
    threading.Thread(target=force_exit, daemon=True).start()

    # SIGTERMの場合は、Botのクローズ処理は非同期イベントループで処理
    # asyncioのイベントループを直接操作せず、終了フラグを立てるだけにする
    if signum == signal.SIGTERM:
        print("SIGTERM受信 - 終了フラグを設定しました。非同期終了処理が実行されます。")

async def run_bot():
    """Botの実行と終了を管理する関数"""
    global bot_instance, signal_received
    
    bot = ThreadBot()
    bot_instance = bot
    
    update_status_file("Bot起動中")
    
    try:
        print("Botを起動しています...")
        # 通常の起動処理
        await bot.start(BOT_TOKEN)
    except KeyboardInterrupt:
        print("キーボード割り込みを検知しました。Botを終了します。")
        update_status_file("キーボード割り込みによる終了")
    except Exception as e:
        print(f"Bot実行中にエラーが発生しました: {e}")
        update_status_file(f"エラー発生: {e}")
        traceback.print_exc()
    finally:
        # 終了処理
        try:
            if bot.is_ready():
                print("Botのクローズ処理を実行します...")
                update_status_file("Bot終了処理中")
                await bot.close()
                print("Botの終了処理が完了しました")
        except Exception as e:
            print(f"Bot終了処理中にエラーが発生しました: {e}")
            traceback.print_exc()

async def main():
    """メイン関数 - イベントループの問題を回避し、シャットダウン処理を改善"""
    global keepalive_thread, http_server_thread, signal_received, shutdown_in_progress
    
    # 起動時刻を記録
    global start_time, instance_id
    start_time = datetime.now()
    
    # 環境変数を設定（他のモジュールで使用）
    os.environ['INSTANCE_ID'] = instance_id
    os.environ['START_TIME'] = start_time.isoformat()
    
    # 終了シグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGHUP, handle_exit)
    
    # ステータス初期化
    update_status_file("起動中")
    
    try:
        # HTTPサーバーの起動（Koyeb対応のため優先的に起動）
        port = PORT
        if DEBUG_MODE:
            port = PORT + 1
            print(f"デバッグモードのため、ポート番号を変更: {port}")
        
        print(f"HTTPサーバーを起動します (ポート: {port})")
        update_status_file(f"HTTPサーバー起動中 (ポート: {port})")
        http_server_thread = server_thread(port=port)
        
        # サーバー起動を確認するため少し待機
        await asyncio.sleep(1)
        
        # キープアライブ機能の開始
        if KEEP_ALIVE_ENABLED:
            interval = KEEP_ALIVE_INTERVAL
            print(f"キープアライブ機能を有効化します (間隔: {interval}秒)")
            update_status_file(f"キープアライブ開始 (間隔: {interval}秒)")
            
            # キープアライブを開始（シグナルハンドリングは無効化 - main.pyが処理する）
            keepalive_thread = start_keepalive(interval=interval, port=port, handle_signals=False)
            if keepalive_thread:
                print("キープアライブスレッドを開始しました")
            else:
                print("キープアライブスレッドの開始に失敗しました")
        else:
            print("キープアライブ機能は無効です")
            
        # ステータス更新
        update_status_file("Bot実行中")
        
        # Botを実行
        await run_bot()
            
    except KeyboardInterrupt:
        print("キーボード割り込みを検知しました。終了します。")
        update_status_file("キーボード割り込みによる終了")
    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")
        update_status_file(f"致命的なエラー: {e}")
        traceback.print_exc()
    finally:
        # 終了時のクリーンアップ
        shutdown_in_progress = True
        
        # キープアライブスレッドの停止
        if keepalive_thread:
            try:
                print("キープアライブスレッドを停止します")
                stop_keepalive()
                print("キープアライブスレッドを停止しました")
                # スレッドが確実に終了するまで少し待機
                await asyncio.sleep(1)
            except Exception as e:
                print(f"キープアライブ停止中にエラーが発生しました: {e}")
        
        # 最終ステータス
        update_status_file("正常終了")
        print("終了処理が完了しました")

# ===============================
# Bot 実行
# ===============================
if __name__ == "__main__":
    try:
        # 起動メッセージを表示
        print("=" * 60)
        print(f"Discord Bot - Koyeb対応キープアライブ機能付き (v2.1)")
        print("=" * 60)
        print(f"開始時刻: {start_time.isoformat()}")
        print(f"インスタンスID: {instance_id}")
        print("Ctrl+Cで終了できます")
        print("=" * 60)
        
        # ステータスファイル初期化
        update_status_file("プログラム起動")
        
        # 非同期実行
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムが中断されました。終了します。")
        update_status_file("キーボード割り込みによる終了")
    except Exception as e:
        print(f"予期しない例外が発生しました: {e}")
        update_status_file(f"予期しない例外: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 終了処理の確認
        print("プログラムを終了します...")
        
        # 強制終了を防ぐため少し待機
        time.sleep(1)
        # シャットダウンフラグが立っていない場合は、強制終了
        if not shutdown_in_progress:
            print("プログラムが正常に終了しなかったため、強制終了します")
            update_status_file("強制終了")
            os._exit(1)