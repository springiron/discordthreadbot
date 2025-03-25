#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot メインエントリーポイント - クロスプラットフォーム対応版 (nohup最適化)
改良されたキープアライブ機構と安定性の向上
nohup環境でも安定して動作、SIGHUPシグナルを適切に処理
"""

import asyncio
import os
import signal
import sys
import time
import traceback
import platform
from datetime import datetime
import tempfile

# OSの種類を判定
IS_WINDOWS = platform.system() == "Windows"

# 一時ディレクトリパスを取得（クロスプラットフォーム対応）
TMP_DIR = tempfile.gettempdir()

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
running_with_nohup = "nohup" in os.environ.get('_', '')

# ステータスファイル定義（クロスプラットフォーム対応）
STATUS_FILE = os.path.join(TMP_DIR, "discord_bot_status.txt")

def update_status_file(status):
    """ステータスファイルを更新"""
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(f"{status}\n")
            f.write(f"更新時刻: {datetime.now().isoformat()}\n")
            f.write(f"起動時刻: {start_time.isoformat()}\n")
            uptime = datetime.now() - start_time
            f.write(f"稼働時間: {uptime}\n")
            f.write(f"nohup検出: {running_with_nohup}\n")
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
    
    # SIGHUPは無視する設定
    if signum == signal.SIGHUP:
        print(f"{sig_name} シグナルを受信しましたが、無視します")
        update_status_file(f"{sig_name}受信 - 無視")
        return
    
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
        
        # 重要なエラーの場合でも再起動を試みる
        if not signal_received:
            print("3秒後にBot再起動を試みます...")
            await asyncio.sleep(3)
            return True  # 再起動フラグを返す
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
    
    return False  # 正常終了

async def main():
    """メイン関数 - イベントループの問題を回避し、シャットダウン処理を改善"""
    global keepalive_thread, http_server_thread, signal_received, shutdown_in_progress
    
    # 起動時刻を記録
    global start_time, instance_id
    start_time = datetime.now()
    
    # 環境変数を設定（他のモジュールで使用）
    os.environ['INSTANCE_ID'] = instance_id
    os.environ['START_TIME'] = start_time.isoformat()
    
    # nohupを使用している場合はSIGHUPを無視するように設定
    # これがnohup環境でのコアとなる対応
    if not IS_WINDOWS and hasattr(signal, 'SIGHUP'):
        if running_with_nohup:
            # nohup環境ではSIGHUPを無視
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
            print("nohup環境を検出: SIGHUPシグナルを無視するように設定しました")
        else:
            # 通常環境ではSIGHUPを処理
            signal.signal(signal.SIGHUP, handle_exit)
    
    # 他のシグナルハンドラを設定
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # ステータス初期化
    update_status_file("起動中")
    
    # 永続的なメインループ - SIGTERMやSIGINTを受け取るまで継続
    restart_count = 0
    max_restarts = 10  # 最大再起動回数
    
    while not signal_received and not shutdown_in_progress and restart_count < max_restarts:
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
            should_restart = await run_bot()
            
            # エラーによる再起動フラグがない場合は終了
            if not should_restart:
                break
                
            restart_count += 1
            print(f"Bot再起動試行 {restart_count}/{max_restarts}")
            update_status_file(f"Bot再起動試行 {restart_count}/{max_restarts}")
            
        except KeyboardInterrupt:
            print("キーボード割り込みを検知しました。終了します。")
            update_status_file("キーボード割り込みによる終了")
            break
        except Exception as e:
            print(f"致命的なエラーが発生しました: {e}")
            update_status_file(f"致命的なエラー: {e}")
            traceback.print_exc()
            
            # 重大なエラー時も再起動を試みる
            restart_count += 1
            if restart_count < max_restarts:
                print(f"5秒後に再起動を試みます... ({restart_count}/{max_restarts})")
                await asyncio.sleep(5)
            else:
                print(f"最大再起動回数({max_restarts})に達しました。終了します。")
                break
    
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

# エラー発生時にもプログラムを継続実行する監視ループ
def safe_run_loop():
    """
    メインプログラムを安全に実行し、例外発生時も継続実行を試みる
    nohup環境で特に重要
    """
    loop_count = 0
    max_loops = 100  # 安全のため最大ループ回数を設定
    
    while loop_count < max_loops:
        try:
            # 起動メッセージを表示
            print("=" * 60)
            print(f"Discord Bot - クロスプラットフォーム対応版 (v2.3 - nohup最適化)")
            print("=" * 60)
            print(f"実行環境: {platform.system()} {platform.release()}")
            print(f"開始時刻: {datetime.now().isoformat()}")
            print(f"インスタンスID: {instance_id}")
            print(f"一時ファイル保存先: {TMP_DIR}")
            print(f"nohup検出: {running_with_nohup}")
            print("Ctrl+Cで終了できます")
            print("=" * 60)
            
            # ステータスファイル初期化
            update_status_file("プログラム起動")
            
            # 非同期実行
            asyncio.run(main())
            
            # 正常終了の場合はループを抜ける
            break
            
        except KeyboardInterrupt:
            print("\nプログラムが中断されました。終了します。")
            update_status_file("キーボード割り込みによる終了")
            break
        except Exception as e:
            # 致命的なエラーでも再起動を試みる
            loop_count += 1
            print(f"予期しない例外が発生しました: {e}")
            update_status_file(f"予期しない例外: {e} (再起動試行 {loop_count})")
            traceback.print_exc()
            
            # 再起動前に待機
            print(f"10秒後に再起動を試みます... ({loop_count}/{max_loops})")
            time.sleep(10)
        finally:
            # 各ループの最後に実行
            if loop_count >= max_loops:
                print(f"最大再起動回数({max_loops})に達しました。終了します。")
                update_status_file("最大再起動回数到達")
                break

# ===============================
# Bot 実行
# ===============================
if __name__ == "__main__":
    # メイン処理を安全に実行
    safe_run_loop()
    
    # 終了処理
    print("プログラムを終了します...")
    
    # 強制終了を防ぐため少し待機
    time.sleep(1)
    
    # シャットダウンフラグが立っていない場合は、強制終了
    if not shutdown_in_progress:
        print("プログラムが正常に終了しなかったため、強制終了します")
        update_status_file("強制終了")
        os._exit(1)