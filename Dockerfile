FROM python:3.9-slim

WORKDIR /app

# 依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY ./app /app

# ログディレクトリを作成
RUN mkdir -p /app/logs && chmod 777 /app/logs

# 実行ユーザーを設定
RUN useradd -m botuser
USER botuser

# 起動コマンド
CMD ["python", "main.py"]