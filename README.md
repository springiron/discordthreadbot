# Discord スレッド自動生成 Bot

Discord上のメッセージから自動的にスレッドを作成し、募集完了時に閉じることができるBotです。

## 機能概要

- 特定のキーワードや`@数字`を含むメッセージに対して自動的にスレッドを作成
- スレッドを作成したユーザーのみが締め切りボタンを押せる権限管理
- キーワードによるスレッド締め切り機能（作成者のみ）
- 閉じたスレッドは名前が変更され、親メッセージにリアクションが追加される
- チャンネル単位での有効・無効設定
- 自動アーカイブ時間やスレッド名など、多彩な設定をDiscord上のコマンドで変更可能

## 使い方

### スレッド自動作成

以下のいずれかの条件を満たすメッセージを投稿すると、自動的にスレッドが作成されます：

1. 設定されたキーワード（デフォルトは「募集」）を含むメッセージ
2. `@数字`パターン（例：`@3`、`@10`）を含むメッセージ

### スレッド締め切り方法

スレッドを締め切るには、以下のいずれかの方法があります：

1. スレッド内の「募集を締め切る」ボタンを押す
2. スレッド内で締め切りキーワード（「〆」「締め切り」など）を投稿する

**※スレッドを締め切ることができるのは、スレッドの作成者のみです。**

## コマンド一覧

Botは以下のコマンドに対応しています：

- `!config` - Bot設定を表示・変更（管理者用）
- `!keywords` - トリガーキーワード一覧を表示
- `!channels` - Bot有効チャンネル一覧を表示
- `!closekeywords` - 締め切りキーワード一覧を表示
- `!ignoredbots` - 無視するBotの一覧を表示
- `!debug` - 監視中スレッドの詳細情報を表示（管理者用、デバッグモード時のみ）
- `!bothelp` - コマンドのヘルプを表示

### 設定変更例

```
!config TRIGGER_KEYWORDS 募集,参加者募集
!config THREAD_AUTO_ARCHIVE_DURATION 1440
!config ENABLED_CHANNEL_IDS 123456789012345678,987654321098765432
```

## 主な設定項目

| 設定名 | 説明 | デフォルト値 |
|--------|------|-------------|
| TRIGGER_KEYWORDS | スレッド作成のトリガーとなるキーワード | ["募集"] |
| ENABLED_CHANNEL_IDS | Botが有効なチャンネルID（空の場合は全チャンネルで有効） | [] |
| THREAD_AUTO_ARCHIVE_DURATION | スレッド自動アーカイブ時間（分） | 60 |
| THREAD_NAME_TEMPLATE | スレッド名のテンプレート | "[✅ 募集中]{username}の募集" |
| THREAD_CLOSE_KEYWORDS | スレッド締め切りのトリガーとなるキーワード | ["〆", "締め", "しめ", "〆切", "締切", "しめきり", "closed", "close"] |
| THREAD_CLOSED_NAME_TEMPLATE | スレッド締め切り後の名前テンプレート | "[⛔ 募集終了]{original_name}" |
| THREAD_MONITORING_DURATION | スレッド監視時間（分） | 60 |
| IGNORED_BOT_IDS | 無視するBotのID | [] |

## インストール方法

### 必要環境

- Python 3.8以上
- discord.py 2.0以上

### インストール手順

1. リポジトリをクローン
   ```
   git clone https://github.com/yourusername/discord-thread-bot.git
   cd discord-thread-bot
   ```

2. 依存パッケージをインストール
   ```
   pip install -r requirements.txt
   ```

3. 設定ファイルの準備
   ```
   cp .env.example .env
   ```

4. `.env`ファイルを編集し、Discord Botトークンとその他の設定を入力

5. Botを起動
   ```
   python app/main.py
   ```

## 設定ファイル

Botの設定は以下の2つのファイルで管理されています：

### .env ファイル

- **用途**: 初期設定および機密情報（トークンなど）を管理するためのファイル
- **特徴**: 
  - バージョン管理から除外されることが多い（.gitignoreに追加）
  - Bot 起動時に一度だけ読み込まれる
  - サーバー環境ごとに異なる設定が必要な場合に使用

設定例：
```
# 必須設定
DISCORD_BOT_TOKEN=あなたのBotトークン

# 基本設定
DEBUG_MODE=false
LOG_LEVEL=INFO

# スレッド設定
THREAD_AUTO_ARCHIVE_DURATION=60
THREAD_NAME_TEMPLATE=[✅ 募集中]{username}の募集
TRIGGER_KEYWORDS=募集
THREAD_CLOSE_KEYWORDS=〆,締め,しめ,〆切,締切,しめきり,closed,close
THREAD_CLOSED_NAME_TEMPLATE=[⛔ 募集終了]{original_name}
THREAD_MONITORING_DURATION=60

# チャンネル・ユーザー設定
ENABLED_CHANNEL_IDS=
ADMIN_USER_IDS=
IGNORED_BOT_IDS=
```

### config.json ファイル

- **用途**: Bot実行中に変更可能な設定を保存・管理するためのファイル
- **特徴**:
  - Discordコマンド（`!config`）で変更した設定が保存される
  - `.env`から読み込まれた設定はBot起動時に`config.json`に反映される
  - 機密情報（BOT_TOKEN）は保存されない

**重要**: `config.json`には機密情報（Botトークンなど）を保存しないでください。機密情報は`.env`ファイルのみで管理してください。

### 設定の優先順位

1. Bot起動時は`.env`ファイルから設定が読み込まれる
2. `.env`ファイルの設定は`config.json`に反映される（BOT_TOKENを除く）
3. `!config`コマンドで変更した設定は`config.json`に保存される
4. Bot再起動時には`config.json`の設定が優先されるが、`.env`に明示的に指定された値があればそちらが優先される

## Dockerでの実行

Dockerを使用して実行する場合：

```
docker build -t discord-thread-bot .
docker run -d --name discord-bot --env-file .env discord-thread-bot
```

Docker Composeを使用する場合：

```
docker-compose up -d
```

## 注意事項

- スレッド締め切り機能は、スレッドを作成したユーザーのみが実行できます
- Botが再起動した場合、スレッド作成者情報はリセットされるため、再起動前に作成されたスレッドの締め切りはできなくなる可能性があります
- 大量のメッセージが投稿されるチャンネルでは、トリガーキーワードをより具体的なものに設定することをお勧めします

## トラブルシューティング

- スレッドが自動作成されない
  - トリガーキーワードや有効チャンネル設定を確認してください
  - Botに必要な権限（スレッドの作成・読み取り権限）があるか確認してください

- 締め切りボタンが動作しない
  - スレッドを作成したユーザーでのみ操作可能です
  - Bot再起動後は、再起動前に作成されたスレッドの作成者情報が失われる可能性があります

- ユーザーメンション（@ユーザー名）でスレッドが作成されてしまう
  - Discordでは、ユーザーメンションは内部的に`<@数字>`や`<@!数字>`の形式で送信されるため、これが`@数字`パターンとして検出される場合があります
  - 解決策として、`!config TRIGGER_KEYWORDS`で具体的なキーワードのみを使用するように設定してください

## ライセンス

MITライセンス

## 貢献

バグ報告や機能リクエストは、GitHubのIssuesにて受け付けています。
プルリクエストも歓迎します！
