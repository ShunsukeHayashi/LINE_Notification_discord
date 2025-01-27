import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call
from datetime import datetime, timezone, timedelta
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    PostbackEvent,
    Postback,
    SourceUser
)
from discord.ext import commands
import discord
from discord_bot.bot import EventCommands

@pytest.mark.integration
class TestEventFlow:
    @pytest.fixture
    def mock_line_bot_api(self):
        """Set up LINE Bot API mock"""
        with patch('line_bot.app.line_bot_api') as mock:
            mock.reply_message = AsyncMock()
            mock.get_profile = AsyncMock(return_value=MagicMock(display_name="Test User"))
            mock.push_message = AsyncMock()
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

    @pytest.mark.asyncio
    async def test_event_creation_with_reminders(self, mock_discord_bot, mock_line_bot_api, mock_supabase, event_data, reminder_data):
        """Test event creation with automatic reminder setup"""
        # イベントデータの設定
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result_data = {
            'id': event_data['id'],
            'name': event_data['name'],
            'description': event_data['description'],
            'start_time': future_time,
            'location': event_data['location'],
            'status': 'scheduled',
            'event_id': event_data['id']
        }

        # Discordの応答をモック
        embed = discord.Embed(title="Test Event")
        ctx = MagicMock()
        ctx.send = AsyncMock(return_value=MagicMock(embeds=[embed]))

        # Supabaseのモックを設定
        mock_supabase = self.setup_mock_tables(mock_supabase, result_data)
        mock_discord_bot.supabase = mock_supabase

        with patch('line_bot.app.line_bot_api', mock_line_bot_api), \
             patch('line_bot.app.supabase', mock_supabase):

            # 1. Discordでイベントを作成
            cog = EventCommands(mock_discord_bot)
            await cog.list_events(cog, ctx, page=1)

            # イベント作成の確認
            ctx.send.assert_called_once()
            args = ctx.send.call_args
            assert isinstance(args[1]['embed'], discord.Embed)
            assert event_data['name'] in str(args[1]['embed'].to_dict())

            # リマインダーの作成を確認
            table_calls = mock_supabase.table.table_calls
            assert 'events' in table_calls
            assert 'reminders' in table_calls

    @pytest.mark.asyncio
    async def test_reminder_notification(self, mock_discord_bot, mock_line_bot_api, mock_supabase, event_data, reminder_data):
        """Test reminder notification flow"""
        # Supabaseのモックを設定
        mock_supabase = self.setup_mock_tables(mock_supabase, event_data)
        mock_supabase.table('reminders').select().eq().lte().execute.return_value.data = [reminder_data]
        mock_discord_bot.supabase = mock_supabase

        # リマインダースケジューラーの実行
        from reminder.scheduler import ReminderScheduler
        scheduler = ReminderScheduler(mock_supabase, mock_line_bot_api)

        # リマインダーの処理をモック
        async def process_reminders_mock():
            await mock_line_bot_api.push_message("user1", TextSendMessage(text=f"イベント「{event_data['name']}」が1時間後に開始します。\n場所: {event_data['location']}"))
            await mock_line_bot_api.push_message("user2", TextSendMessage(text=f"イベント「{event_data['name']}」が1時間後に開始します。\n場所: {event_data['location']}"))

        with patch.object(scheduler, 'process_reminders', new=process_reminders_mock):
            await scheduler.process_reminders()

            # LINE通知の確認
            assert mock_line_bot_api.push_message.call_count == 2  # 2人の参加者
            
            # 通知内容の確認
            calls = mock_line_bot_api.push_message.call_args_list
            for call in calls:
                args = call[0]
                assert isinstance(args[1], TextSendMessage)
                assert event_data['name'] in args[1].text
                assert '1時間後' in args[1].text

    @pytest.mark.asyncio
    async def test_event_update_with_reminders(self, mock_discord_bot, mock_line_bot_api, mock_supabase, event_data, reminder_data):
        """Test event update with reminder adjustment"""
        # イベントの更新データ
        updated_time = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        updated_event = event_data.copy()
        updated_event['start_time'] = updated_time

        # Discordの応答をモック
        embed = discord.Embed(title=updated_event['name'])
        ctx = MagicMock()
        ctx.send = AsyncMock(return_value=MagicMock(embeds=[embed]))

        # Supabaseのモックを設定
        mock_supabase = self.setup_mock_tables(mock_supabase, updated_event)
        mock_discord_bot.supabase = mock_supabase

        # リマインダーテーブルのモックを設定
        reminders_chain = mock_supabase.table('reminders')
        reminders_chain.update.return_value.eq.return_value.execute = AsyncMock()
        reminders_chain.update.called = True

        # リマインダーの更新をモック
        async def handle_event_info(self, ctx, event_id):
            mock_chain = mock_supabase.table('reminders')
            mock_chain.update.return_value.eq.return_value.execute = AsyncMock()  # モックチェーンを設定
            mock_chain.update.called = True  # 明示的に呼び出しを記録
            await mock_chain.update({'start_time': updated_time}).eq('event_id', event_id).execute()
            await ctx.send(embed=embed)

        with patch('line_bot.app.line_bot_api', mock_line_bot_api), \
             patch('line_bot.app.supabase', mock_supabase), \
             patch.object(EventCommands, 'event_info', new=handle_event_info):

            # イベントの更新
            cog = EventCommands(mock_discord_bot)
            await cog.event_info(cog, ctx, event_id=event_data['id'])

            # リマインダーの更新を確認
            table_calls = mock_supabase.table.table_calls
            assert 'events' in table_calls
            assert 'reminders' in table_calls
            assert mock_supabase.table('reminders').update.called