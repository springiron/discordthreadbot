# Discord 自動スレッド作成Bot

特定のキーワードを含むメッセージが送信された際に、自動でスレッドを作成するDiscord Botです。

## 主な機能

- 特定のキーワード（例: 「募集」）を含むメッセージが送信された時に自動でスレッドを作成
- スレッドタイトルにはメッセージ投稿者の表示名を設定
- スレッド作成後、Botは自動的にスレッドから退出
- スレッドは1週間（10080分）で自動的にアーカイブ

## セットアップ方法

### 必要条件

- Docker
- Discord Bot Token

### 環境変数の設定

以下の環境変数を設定してください：

- `DISCORD_BOT_TOKEN`: Discord Bot Token
- `DEBUG_MODE`: デバッグモード (`true` または `false`)
- `ENABLED_CHANNEL_IDS`: 有効なチャンネルIDのリスト (カンマ区切り、例: `123456789,987654321`)
- `KEEP_ALIVE_ENABLED`: キープアライブ機能の有効/無効 (`true` または `false`)
- `KEEP_ALIVE_INTERVAL`: キープアライブの間隔（分）

### ローカルでの実行方法

1. 環境変数を設定
```bash
export DISCORD_BOT_TOKEN=your_token_here
export DEBUG_MODE=false
```

2. Docker Composeでビルド・起動
```bash
docker-compose up --build
```

## Koyebでのデプロイ方法

1. Koyebアカウントを作成

2. Koyebダッシュボードから新しいアプリを作成
   - デプロイタイプとして「Docker」を選択

3. GitHubリポジトリと連携
   - メインブランチを連携
   - 自動デプロイを有効化

4. 環境変数を設定
   - `DISCORD_BOT_TOKEN`: Discord Bot Token

5. デプロイを実行

## カスタマイズ

`app/config.py` ファイルを編集することで、以下の設定をカスタマイズできます：

- `TRIGGER_KEYWORDS`: スレッド作成のトリガーとなるキーワード
- `THREAD_AUTO_ARCHIVE_DURATION`: スレッドの自動アーカイブ時間
- `THREAD_NAME_TEMPLATE`: スレッド名のテンプレート
- `ENABLED_CHANNEL_IDS`: 有効なチャンネルIDのリスト
- `KEEP_ALIVE_ENABLED`: キープアライブ機能の有効/無効
- `KEEP_ALIVE_INTERVAL`: キープアライブの間隔（分）

### チャンネルIDの設定

特定のチャンネルでのみBotを動作させるには：

1. Discordの設定で「開発者モード」を有効にします
2. 対象チャンネルを右クリックして「IDをコピー」を選択
3. 環境変数 `ENABLED_CHANNEL_IDS` に取得したIDをカンマ区切りで設定します
   ```
   ENABLED_CHANNEL_IDS=123456789012345678,987654321098765432
   ```
4. 環境変数を設定しない、または空の値を設定すると、Botはすべてのチャンネルで動作します

### キープアライブ機能

Koyebなどのサーバーで一定時間アクティビティがないとスリープする問題に対処するため、キープアライブ機能を実装しています：

1. `KEEP_ALIVE_ENABLED=true` に設定することで機能を有効化（デフォルトは有効）
2. `KEEP_ALIVE_INTERVAL` で間隔を分単位で指定（デフォルトは30分）
3. キープアライブ機能は定期的にログメッセージを出力して、サーバーをアクティブな状態に保ちます

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。