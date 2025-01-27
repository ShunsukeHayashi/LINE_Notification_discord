import pytest
from discord.ext import commands
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
import discord
from datetime import datetime

@pytest.mark.unit
@pytest.mark.discord
class TestDiscordBot:
    @pytest.fixture
    async def test_bot(self):
        """Set up test bot"""
        with patch('discord_bot.bot.EventBot') as MockBot:
            mock_bot = MagicMock()
            mock_bot.supabase = MagicMock()
            MockBot.return_value = mock_bot
            from discord_bot.bot import bot
            return bot

    @pytest.fixture
    def mock_context(self):
        """Create a mock context"""
        ctx = MagicMock()
        ctx.send = AsyncMock()
        return ctx

    def setup_supabase_mock(self, mock_supabase, result_data, count_data=None):
        """Set up Supabase mock with proper chaining"""
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_execute = MagicMock()
        mock_result = MagicMock()
        mock_result.data = result_data

        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_select
        mock_select.gte.return_value = mock_select
        mock_select.order.return_value = mock_select
        mock_select.range.return_value = mock_select
        mock_select.execute.return_value = mock_result

        if count_data is not None:
            mock_count = MagicMock()
            mock_count.count = count_data
            mock_select.execute.side_effect = [mock_result, mock_count]

        mock_supabase.table.return_value = mock_table
        return mock_table, mock_result

    @pytest.mark.asyncio
    async def test_events_command(self, test_bot, event_data, mock_supabase, mock_context):
        """Test events command"""
        # Supabaseのモックレスポンスの設定
        result_data = [{
            'name': event_data['name'],
            'description': event_data['description'],
            'start_time': '2024-02-01T10:00:00Z',
            'location': event_data['location']
        }]
        
        mock_table, _ = self.setup_supabase_mock(mock_supabase, result_data, count_data=1)
        test_bot.supabase = mock_supabase
        
        # EventCommandsのインスタンスを作成
        from discord_bot.bot import EventCommands
        cog = EventCommands(test_bot)
        
        # eventsコマンドをテスト
        await cog.list_events.callback(cog, mock_context)
        
        # アサーション
        mock_context.send.assert_called_once()
        call_args = mock_context.send.call_args
        assert isinstance(call_args[1]['embed'], discord.Embed)
        assert event_data['name'] in str(call_args[1]['embed'].to_dict())

    @pytest.mark.asyncio
    async def test_eventinfo_command(self, test_bot, event_data, mock_supabase, mock_context):
        """Test eventinfo command"""
        # イベント情報のモック設定
        event_result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'description': event_data['description'],
            'start_time': '2024-02-01T10:00:00Z',
            'end_time': '2024-02-01T12:00:00Z',
            'location': event_data['location'],
            'status': 'scheduled'
        }]
        
        # 参加者情報のモック設定
        participants_result_data = [{
            'users': {
                'name': 'Test User'
            }
        }]

        # Supabaseのモックを設定
        mock_event_table = MagicMock()
        mock_event_select = MagicMock()
        mock_event_result = MagicMock()
        mock_event_result.data = event_result_data

        mock_participants_table = MagicMock()
        mock_participants_select = MagicMock()
        mock_participants_result = MagicMock()
        mock_participants_result.data = participants_result_data

        # イベントテーブルのチェーン設定
        mock_event_table.select.return_value = mock_event_select
        mock_event_select.eq.return_value = mock_event_select
        mock_event_select.execute.return_value = mock_event_result

        # 参加者テーブルのチェーン設定
        mock_participants_table.select.return_value = mock_participants_select
        mock_participants_select.eq.return_value = mock_participants_select
        mock_participants_select.execute.return_value = mock_participants_result

        # Supabaseのtableメソッドをモック
        def mock_table_side_effect(table_name):
            if table_name == 'events':
                return mock_event_table
            elif table_name == 'participants':
                return mock_participants_table
            return MagicMock()

        mock_supabase.table.side_effect = mock_table_side_effect
        test_bot.supabase = mock_supabase
        
        # EventCommandsのインスタンスを作成
        from discord_bot.bot import EventCommands
        cog = EventCommands(test_bot)
        
        # eventinfoコマンドをテスト
        await cog.event_info.callback(cog, mock_context, event_data["id"])
        
        # アサーション
        mock_context.send.assert_called_once()
        call_args = mock_context.send.call_args
        assert isinstance(call_args[1]['embed'], discord.Embed)
        embed_dict = call_args[1]['embed'].to_dict()
        assert event_data['name'] == embed_dict['title']
        assert event_data['description'] == embed_dict['description']

    @pytest.mark.asyncio
    async def test_search_command(self, test_bot, event_data, mock_supabase, mock_context):
        """Test search command"""
        # Supabaseのモックレスポンスの設定
        result_data = [{
            'name': event_data['name'],
            'description': event_data['description'],
            'start_time': '2024-02-01T10:00:00Z',
            'location': event_data['location']
        }]
        
        mock_table, _ = self.setup_supabase_mock(mock_supabase, result_data)
        test_bot.supabase = mock_supabase
        
        # EventCommandsのインスタンスを作成
        from discord_bot.bot import EventCommands
        cog = EventCommands(test_bot)
        
        # searchコマンドをテスト
        await cog.search_events.callback(cog, mock_context, query="Test")
        
        # アサーション
        mock_context.send.assert_called_once()
        call_args = mock_context.send.call_args
        assert isinstance(call_args[1]['embed'], discord.Embed)
        embed_dict = call_args[1]['embed'].to_dict()
        assert "Test" in embed_dict['title']