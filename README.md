# イベント通知システム

DiscordとLINEを連携したイベント通知システム

## 概要

このシステムは、Discordで作成されたイベントをLINE BOTを通じて通知し、参加管理を行うアプリケーションです。

## 機能

- Discord上でのイベント作成と管理
- LINE BOTによるイベント通知
- イベント参加登録の管理
- Supabaseを使用したデータ永続化
- イベントリマインダー機能
  - イベント開始1日前の通知
  - イベント開始3時間前の通知
  - イベント開始1時間前の通知

## 必要条件

- Python 3.11以上
- Conda
- Discord Bot Token
- LINE Messaging API Token
- Supabase アカウント

## セットアップ

1. conda環境の作成と依存関係のインストール:
```bash
conda env create -f environment.yml
conda activate event-notification-system
```

2. 環境変数の設定:
`.env`ファイルを作成し、以下の環境変数を設定してください：
```
# Discord設定
DISCORD_TOKEN=your_discord_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret

# LINE Bot設定
LINE_CHANNEL_ACCESS_TOKEN=your_line_token
LINE_CHANNEL_SECRET=your_line_secret
LINE_USER_ID=your_line_user_id

# Supabase設定
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_key
```

3. データベースのセットアップ:
Supabaseコンソールで必要なテーブルを作成してください。マイグレーションファイルは `supabase/migrations` ディレクトリにあります。

## 実行方法

1. アプリケーションの起動:
```bash
python main.py
```

2. LINE Webhookの設定:
- ngrokなどを使用してローカルサーバーを公開
- LINE DevelopersコンソールでWebhook URLを設定

## リマインダー機能

イベントリマインダー機能は、以下のタイミングで参加者に通知を送信します：

1. イベント開始1日前
2. イベント開始3時間前
3. イベント開始1時間前

リマインダーは以下の情報を含みます：
- イベント名
- 開始時刻
- 場所
- イベントの説明

リマインダーは自動的に設定され、以下のタイミングで更新されます：
- イベント作成時
- イベント更新時（開始時刻変更）
- イベントキャンセル時（リマインダーも自動的にキャンセル）

## 開発

### テストの実行

```bash
# 全てのテストを実行
pytest

# 特定のテストを実行
pytest tests/unit  # ユニットテスト
pytest tests/integration  # 統合テスト
pytest tests/e2e  # E2Eテスト
pytest tests/unit/test_reminder.py  # リマインダーのテストのみ実行
```

### コードフォーマット

```bash
black .
```

## プロジェクト構造

```
.
├── config/
│   └── settings.py      # 設定ファイル
├── discord_bot/
│   └── bot.py          # Discord Bot実装
├── line_bot/
│   └── app.py          # LINE Bot実装
├── reminder/
│   └── scheduler.py    # リマインダー機能の実装
├── supabase/
│   └── migrations/     # データベースマイグレーション
├── tests/
│   ├── unit/          # ユニットテスト
│   ├── integration/   # 統合テスト
│   └── e2e/          # E2Eテスト
├── .env               # 環境変数
├── environment.yml    # conda環境設定
├── main.py           # アプリケーションエントリーポイント
└── README.md         # このファイル
```

## 注意事項

- 本番環境では適切なセキュリティ設定を行ってください
- 環境変数は適切に管理してください
- Webhookの公開URLはHTTPS必須です
- リマインダー機能のために、アプリケーションは常時実行が必要です

## トラブルシューティング

### よくある問題

1. Discord Botの接続エラー
   - トークンが正しいか確認
   - 必要な権限が付与されているか確認

2. LINE Webhookのエラー
   - Webhook URLが正しいか確認
   - チャンネルシークレットが正しいか確認

3. データベース接続エラー
   - Supabase URLとキーが正しいか確認
   - テーブル構造が正しいか確認

4. リマインダーが送信されない
   - アプリケーションが正常に実行されているか確認
   - イベントの開始時刻が正しく設定されているか確認
   - データベースのリマインダーテーブルを確認

## ライセンス

MIT License# LINE_Notification_discord
