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
import json

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
                table.update.return_value = mock_events
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
            'start_date': future_time,
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
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert event_data['name'] in text_message.text
            assert event_data['location'] in text_message.text

    @pytest.mark.asyncio
    async def test_handle_events_pagination(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling events pagination"""
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        # 6件のイベントデータを作成（ページネーションのテスト用）
        result_data = []
        for i in range(6):
            result_data.append({
                'id': f"{event_data['id']}-{i}",
                'name': f"{event_data['name']} {i}",
                'description': event_data['description'],
                'start_date': future_time,
                'location': event_data['location'],
                'status': 'scheduled',
                'event_id': f"{event_data['id']}-{i}"
            })
        
        self.setup_supabase_mock(mock_supabase, result_data[:5])  # 最初の5件のみ返す
        
        with patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            event = MessageEvent(
                message=TextMessage(text="events"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            from line_bot.app import handle_message
            await handle_message(event)
            
            # アサーション
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert "次のページ" in text_message.text
            assert len([line for line in text_message.text.split('\n') if event_data['name'] in line]) == 5

    @pytest.mark.asyncio
    async def test_handle_join_postback(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling join postback"""
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'start_date': future_time,
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
            event = PostbackEvent(
                postback=Postback(data=f"join_{event_data['id']}"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            from line_bot.app import handle_postback
            await handle_postback(event)
            
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert "参加登録が完了しました" in text_message.text
            assert event_data['name'] in text_message.text

    @pytest.mark.asyncio
    async def test_create_event_with_openai(self, mock_line_bot_api, event_data, mock_supabase):
        """Test event creation with OpenAI integration"""
        future_time = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
        event_text = f"イベント 明日の15時から渋谷で新年会やります！"
        
        # OpenAIのモックレスポンス
        mock_openai_response = MagicMock()
        mock_openai_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "name": "新年会",
                        "description": "新年会のイベント",
                        "start_date": future_time,
                        "location": "渋谷"
                    })
                )
            )
        ]
        
        with patch('line_bot.app.openai.ChatCompletion.create', return_value=mock_openai_response), \
             patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            
            event = MessageEvent(
                message=TextMessage(text=event_text),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            from line_bot.app import handle_message
            await handle_message(event)
            
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert "イベントを作成しました" in text_message.text
            assert "新年会" in text_message.text
            assert "渋谷" in text_message.text

    @pytest.mark.asyncio
    async def test_handle_supabase_connection_error(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling Supabase connection error"""
        mock_supabase.table.side_effect = Exception("Connection error")
        
        with patch('line_bot.app.supabase', mock_supabase), \
             patch('line_bot.app.line_bot_api', mock_line_bot_api):
            event = MessageEvent(
                message=TextMessage(text="events"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            from line_bot.app import handle_message
            await handle_message(event)
            
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert "エラーが発生しました" in text_message.text

    @pytest.mark.asyncio
    async def test_handle_event_info(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling event info command"""
        future_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        result_data = [{
            'id': event_data['id'],
            'name': event_data['name'],
            'description': event_data['description'],
            'start_date': future_time,
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
            event = MessageEvent(
                message=TextMessage(text=f"join {event_data['id']}"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            from line_bot.app import handle_message
            await handle_message(event)
            
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert event_data['name'] in text_message.text
            assert event_data['location'] in text_message.text

    @pytest.mark.asyncio
    async def test_handle_cancel_registration(self, mock_line_bot_api, event_data, mock_supabase):
        """Test handling cancel registration"""
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
            event = PostbackEvent(
                postback=Postback(data=f"cancel_{event_data['id']}"),
                reply_token="test-reply-token",
                source=SourceUser(user_id="test-user")
            )

            from line_bot.app import handle_postback
            await handle_postback(event)
            
            mock_line_bot_api.reply_message.assert_called_once()
            args = mock_line_bot_api.reply_message.call_args
            text_message = args[0][1][0]
            assert isinstance(text_message, TextMessage)
            assert "キャンセル" in text_message.text
            assert event_data['name'] in text_message.text