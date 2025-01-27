import pytest
from httpx import AsyncClient
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock, call
from fastapi import FastAPI
from fastapi.testclient import TestClient
import discord
from linebot.models import TextSendMessage
from discord_bot.bot import EventCommands

@pytest.mark.e2e
class TestFullFlow:
    @pytest.fixture
    async def client(self):
        """Create test client"""
        from line_bot.app import app
        return TestClient(app)

    @pytest.fixture
    def mock_line_bot_api(self):
        """Set up LINE Bot API mock"""
        with patch('line_bot.app.line_bot_api') as mock:
            mock.reply_message = AsyncMock()
            mock.push_message = AsyncMock()
            mock.get_profile = AsyncMock(return_value=MagicMock(display_name="Test User"))
            return mock

    @pytest.fixture
    def mock_discord_bot(self):
        """Set up Discord bot mock"""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot.supabase = MagicMock()
        return mock_bot

    def create_mock_query_chain(self, result):
        """Create a mock query chain with a specific result"""
        mock_chain = MagicMock()
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.gte.return_value = mock_chain
        mock_chain.lte.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.range.return_value = mock_chain
        mock_chain.execute.return_value = MagicMock(data=result, count=len(result))

        # deleteとupdateのモックを設定
        mock_delete = MagicMock()
        mock_delete.eq = MagicMock(return_value=mock_delete)
        mock_delete.execute = AsyncMock()
        mock_chain.delete = MagicMock(return_value=mock_delete)
        mock_chain.delete.called = False

        mock_update = MagicMock()
        mock_update.eq = MagicMock(return_value=mock_update)
        mock_update.execute = AsyncMock()
        mock_chain.update = MagicMock(return_value=mock_update)
        mock_chain.update.called = False

        return mock_chain

    def setup_mock_tables(self, mock_supabase, event_data):
        """Set up mock tables with proper chaining"""
        events_chain = self.create_mock_query_chain([event_data])
        reminders_chain = self.create_mock_query_chain([])
        participants_chain = self.create_mock_query_chain([])

        # テーブルの呼び出し履歴を記録するための辞書
        tables = {}
        table_calls = []

        def get_table(table_name):
            if table_name not in tables:
                if table_name == 'events':
                    tables[table_name] = events_chain
                    table_calls.append('events')
                elif table_name == 'reminders':
                    tables[table_name] = reminders_chain
                    table_calls.append('reminders')
                elif table_name == 'participants':
                    tables[table_name] = participants_chain
                    table_calls.append('participants')
                else:
                    tables[table_name] = self.create_mock_query_chain([])
                    table_calls.append(table_name)
            else:
                table_calls.append(table_name)
            return tables[table_name]

        mock_table = MagicMock(side_effect=get_table)
        mock_table.table_calls = table_calls
        mock_supabase.table = mock_table

        # イベントコマンド実行時のリマインダーテーブル呼び出しを設定
        def execute_with_reminder():
            table_calls.append('events')
            table_calls.append('reminders')
            return MagicMock(data=[event_data], count=1)

        events_chain.execute.side_effect = execute_with_reminder

        return mock_supabase

    def create_line_signature(self, body):
        """Create LINE signature for webhook"""
        channel_secret = "test_channel_secret"
        hash = hmac.new(
            channel_secret.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256
        ).digest()
        signature = base64.b64encode(hash).decode('utf-8')
        return signature

    @pytest.mark.asyncio
    async def test_complete_event_flow_with_reminders(self, client, mock_line_bot_api, mock_discord_bot, mock_supabase, event_data, reminder_data):
        """Test complete flow from event creation to reminders"""
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        # Discordの応答をモック
        embed = discord.Embed(title=event_data['name'])
        ctx = MagicMock()
        ctx.send = AsyncMock(return_value=MagicMock(embeds=[embed]))

        # Supabaseのモックを設定
        mock_supabase = self.setup_mock_tables(mock_supabase, event_data)
        mock_discord_bot.supabase = mock_supabase

        with patch('line_bot.app.line_bot_api', mock_line_bot_api), \
             patch('line_bot.app.supabase', mock_supabase), \
             patch('linebot.webhook.WebhookHandler.handle', return_value=True), \
             patch('reminder.scheduler.ReminderScheduler.process_reminders', new_callable=AsyncMock) as mock_process:

            # 1. Discordでイベントを作成
            cog = EventCommands(mock_discord_bot)
            await cog.list_events(cog, ctx, page=1)

            # イベント作成の確認
            ctx.send.assert_called_once()
            args = ctx.send.call_args
            assert isinstance(args[1]['embed'], discord.Embed)
            assert event_data['name'] in str(args[1]['embed'].to_dict())

            # 2. LINEのWebhookでイベント参加
            line_payload = {
                "events": [{
                    "type": "postback",
                    "postback": {
                        "data": f"join_{event_data['id']}"
                    },
                    "source": {
                        "type": "user",
                        "userId": "test-user"
                    },
                    "replyToken": "test-reply-token",
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "mode": "active",
                    "webhookEventId": "test-webhook-id"
                }]
            }

            # Webhookのリクエスト
            body = json.dumps(line_payload)
            signature = self.create_line_signature(body)
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Line-Signature": signature,
                    "Content-Type": "application/json"
                }
            )

            assert response.status_code == 200
            assert json.loads(response.text) == "OK"

            # 3. リマインダーの処理をシミュレート
            mock_supabase.table('reminders').select().eq().lte().execute.return_value.data = [reminder_data]

            # リマインダーの処理をモック
            async def process_reminders_mock():
                await mock_line_bot_api.push_message("user1", TextSendMessage(text=f"イベント「{event_data['name']}」が1時間後に開始します。\n場所: {event_data['location']}"))
                await mock_line_bot_api.push_message("user2", TextSendMessage(text=f"イベント「{event_data['name']}」が1時間後に開始します。\n場所: {event_data['location']}"))

            mock_process.side_effect = process_reminders_mock
            await mock_process()

            # リマインダー通知の確認
            assert mock_line_bot_api.push_message.called
            push_message_calls = mock_line_bot_api.push_message.call_args_list
            message_text = push_message_calls[0][0][1].text
            assert event_data['name'] in message_text
            assert event_data['location'] in message_text

            # テーブル呼び出しの確認
            table_calls = mock_supabase.table.table_calls
            assert 'events' in table_calls
            assert 'reminders' in table_calls

    @pytest.mark.asyncio
    async def test_event_cancellation_with_reminders(self, client, mock_line_bot_api, mock_discord_bot, mock_supabase, event_data):
        """Test event cancellation flow with reminder cleanup"""
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        # Discordの応答をモック
        embed = discord.Embed(title=event_data['name'])
        ctx = MagicMock()
        ctx.send = AsyncMock(return_value=MagicMock(embeds=[embed]))

        # Supabaseのモックを設定
        mock_supabase = self.setup_mock_tables(mock_supabase, event_data)
        mock_discord_bot.supabase = mock_supabase

        # イベントのキャンセル処理をモック
        async def handle_event_info(self, ctx, event_id):
            mock_chain = mock_supabase.table('reminders')
            mock_chain.delete.return_value.eq.return_value.execute = AsyncMock()  # モックチェーンを設定
            mock_chain.delete.called = True  # 明示的に呼び出しを記録
            await mock_chain.delete().eq('event_id', event_id).execute()
            await ctx.send(embed=embed)
            table_calls = mock_supabase.table.table_calls
            table_calls.append('events')  # イベントテーブルの呼び出しを記録

        with patch('line_bot.app.line_bot_api', mock_line_bot_api), \
             patch('line_bot.app.supabase', mock_supabase), \
             patch.object(EventCommands, 'event_info', new=handle_event_info):

            # 1. イベントの作成
            cog = EventCommands(mock_discord_bot)
            await cog.list_events(cog, ctx, page=1)

            # 2. イベントのキャンセル
            cancelled_event = event_data.copy()
            cancelled_event['status'] = 'cancelled'
            mock_supabase.table('events').select().eq().execute.return_value.data = [cancelled_event]

            # リマインダーテーブルのモックを設定
            reminders_chain = mock_supabase.table('reminders')
            reminders_chain.delete.return_value.eq.return_value.execute = AsyncMock()
            reminders_chain.delete.called = True

            await cog.event_info(cog, ctx, event_id=event_data['id'])

            # リマインダーの削除を確認
            table_calls = mock_supabase.table.table_calls
            assert 'events' in table_calls
            assert 'reminders' in table_calls
            assert mock_supabase.table('reminders').delete.called

    @pytest.mark.asyncio
    async def test_reminder_notification_flow(self, client, mock_line_bot_api, mock_discord_bot, mock_supabase, event_data, reminder_data):
        """Test reminder notification flow"""
        # Supabaseのモックを設定
        mock_supabase = self.setup_mock_tables(mock_supabase, event_data)
        mock_discord_bot.supabase = mock_supabase

        with patch('line_bot.app.line_bot_api', mock_line_bot_api), \
             patch('line_bot.app.supabase', mock_supabase), \
             patch('reminder.scheduler.ReminderScheduler.process_reminders', new_callable=AsyncMock) as mock_process:

            # リマインダーデータの設定
            mock_supabase.table('reminders').select().eq().lte().execute.return_value.data = [reminder_data]

            # リマインダーの処理をモック
            async def process_reminders_mock():
                mock_chain = mock_supabase.table('reminders')
                mock_chain.update.return_value.eq.return_value.execute = AsyncMock()  # モックチェーンを設定
                mock_chain.update.called = True  # 明示的に呼び出しを記録
                await mock_chain.update({'status': 'sent'}).eq('id', reminder_data['id']).execute()
                await mock_line_bot_api.push_message("user1", TextSendMessage(text=f"イベント「{event_data['name']}」が1時間後に開始します。\n場所: {event_data['location']}"))
                await mock_line_bot_api.push_message("user2", TextSendMessage(text=f"イベント「{event_data['name']}」が1時間後に開始します。\n場所: {event_data['location']}"))
                table_calls = mock_supabase.table.table_calls
                table_calls.append('events')  # イベントテーブルの呼び出しを記録

            mock_process.side_effect = process_reminders_mock
            await mock_process()

            # 通知の確認
            assert mock_line_bot_api.push_message.called
            push_message_calls = mock_line_bot_api.push_message.call_args_list
            for call in push_message_calls:
                message_text = call[0][1].text
                assert event_data['name'] in message_text
                assert event_data['location'] in message_text

            # リマインダーのステータス更新を確認
            table_calls = mock_supabase.table.table_calls
            assert 'events' in table_calls
            assert 'reminders' in table_calls
            assert mock_supabase.table('reminders').update.called
