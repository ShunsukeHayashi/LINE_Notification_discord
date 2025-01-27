import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    PostbackEvent,
    Postback,
    SourceUser
)
from datetime import datetime, timezone, timedelta
import time

@pytest.mark.unit
@pytest.mark.line
class TestLineBot:
    @pytest.fixture
    def mock_line_bot_api(self):
        """Set up LINE Bot API mock"""
        with patch('line_bot.app.line_bot_api') as mock:
            mock.reply_message = AsyncMock()
            mock.get_profile = AsyncMock(return_value=MagicMock(display_name="Test User"))
            return mock

    def create_mock_query_chain(self, result):
        """Create a mock query chain with a specific result"""
        mock_chain = MagicMock()
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.gte.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.range.return_value = mock_chain
        mock_chain.execute.return_value = MagicMock(data=result, count=len(result))
        return mock_chain

    def setup_supabase_mock(self, mock_supabase, event_data, user_data=None, participant_data=None):
        """Set up Supabase mock with proper chaining"""
        # イベントテーブルのモック
        mock_events = self.create_mock_query_chain(event_data)
        
        # ユーザーテーブルのモック
        mock_users = self.create_mock_query_chain([user_data] if user_data else [])
        
        # 参加者テーブルのモック
        mock_participants = self.create_mock_query_chain(participant_data if participant_data else [])
        
        # insertとdeleteのモック
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[{'id': 'new-id'}])
        
        mock_delete = MagicMock()
        mock_delete.eq.return_value = mock_delete
        mock_delete.execute.return_value = MagicMock(data=[{'id': 'deleted-id'}])

        # テーブル選択のモック
        def mock_table_side_effect(table_name):
            table = MagicMock()
            if table_name == 'events':
                table.select.return_value = mock_events
                table.insert.return_value = mock_insert
            elif table_name == 'users':
                table.select.return_value = mock_users
                table.insert.return_value = mock_insert
            elif table_name == 'participants':
                table.select.return_value = mock_participants
                table.insert.return_value = mock_insert
                table.delete.return_value = mock_delete
            return table

        mock_supabase.table.side_effect = mock_table_side_effect
        return mock_events

    @pytest.mark.asyncio
    async def test_handle_events_command(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling events command"""
        # Supabaseのモックレスポンスの設定
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'description': event_data['description'],
            'start_time': future_time,
            'location': event_data['location'],
            'status': 'scheduled',
            'event_id': event_data['id']
        }]
        
        self.setup_supabase_mock(mock_supabase, result_data)
        
        with patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            # メッセージイベントの作成
            event = MessageEvent(
                message=TextMessage(text="events"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            # イベントハンドラーのテスト
            from line_bot.app import handle_message
            await handle_message(event)
            
            # アサーション
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1]
            assert isinstance(text_message, TextSendMessage)
            assert event_data['name'] in text_message.text
            assert event_data['location'] in text_message.text

    @pytest.mark.asyncio
    async def test_handle_join_postback(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling join postback"""
        # Supabaseのモックレスポンスの設定
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'start_time': future_time,
            'location': event_data['location'],
            'status': 'scheduled',
            'event_id': event_data['id']
        }]
        
        user_data = {
            'id': 'test-user-id',
            'line_user_id': 'test-user',
            'name': 'Test User'
        }
        
        self.setup_supabase_mock(mock_supabase, result_data, user_data)
        
        with patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            # ポストバックイベントの作成
            event = PostbackEvent(
                postback=Postback(data=f"join_{event_data['id']}"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            # イベントハンドラーのテスト
            from line_bot.app import handle_postback
            await handle_postback(event)
            
            # アサーション
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1]
            assert isinstance(text_message, TextSendMessage)
            assert "参加登録が完了しました" in text_message.text
            assert event_data['name'] in text_message.text

    @pytest.mark.asyncio
    async def test_handle_event_info(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling event info command"""
        # Supabaseのモックレスポンスの設定
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'description': event_data['description'],
            'start_time': future_time,
            'end_time': (datetime.now(timezone.utc) + timedelta(days=7, hours=2)).isoformat(),
            'location': event_data['location'],
            'status': 'scheduled',
            'max_participants': 10,
            'current_participants': 5,
            'event_id': event_data['id']
        }]
        
        user_data = {
            'id': 'test-user-id',
            'line_user_id': 'test-user',
            'name': 'Test User'
        }
        
        self.setup_supabase_mock(mock_supabase, result_data, user_data)
        
        with patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            # メッセージイベントの作成
            event = MessageEvent(
                message=TextMessage(text=f"join {event_data['id']}"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            # イベントハンドラーのテスト
            from line_bot.app import handle_message
            await handle_message(event)
            
            # アサーション
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1]
            assert isinstance(text_message, TextSendMessage)
            assert event_data['name'] in text_message.text
            assert event_data['location'] in text_message.text

    @pytest.mark.asyncio
    async def test_handle_cancel_registration(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling cancel registration"""
        # Supabaseのモックレスポンスの設定
        result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'status': 'scheduled',
            'event_id': event_data['id']
        }]
        
        user_data = {
            'id': 'test-user-id',
            'line_user_id': 'test-user',
            'name': 'Test User'
        }
        
        participant_data = [{
            'event_id': event_data['id'],
            'user_id': user_data['id'],
            'status': 'registered'
        }]
        
        self.setup_supabase_mock(mock_supabase, result_data, user_data, participant_data)
        
        with patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            # ポストバックイベントの作成
            event = PostbackEvent(
                postback=Postback(data=f"cancel_{event_data['id']}"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            # イベントハンドラーのテスト
            from line_bot.app import handle_postback
            await handle_postback(event)
            
            # アサーション
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1]
            assert isinstance(text_message, TextSendMessage)
            assert "キャンセル" in text_message.text
            assert event_data['name'] in text_message.text