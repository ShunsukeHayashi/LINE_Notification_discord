import pytest
from unittest.mock import MagicMock
import os
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import json

# テスト用の環境変数を読み込む
load_dotenv('.env.test')

@pytest.fixture
def event_data():
    """Sample event data for tests"""
    return {
        'id': 'test-event-id',
        'name': 'Test Event',
        'description': 'Test Description',
        'start_date': '2024-02-01T10:00:00Z',
        'end_date': '2024-02-01T12:00:00Z',
        'location': 'Test Location',
        'status': 'scheduled',
        'max_participants': 10,
        'event_id': 'test-event-id'
    }

@pytest.fixture
def user_data():
    """Sample user data for tests"""
    return {
        'id': 'test-user-id',
        'line_user_id': 'line-user-id',
        'discord_user_id': 'discord-user-id',
        'name': 'Test User',
        'email': 'test@example.com'
    }

@pytest.fixture
def reminder_data(event_data):
    """Sample reminder data for tests"""
    current_time = datetime.now(timezone.utc)
    return {
        'id': 'test-reminder-id',
        'event_id': event_data['id'],
        'reminder_type': '1hour',
        'scheduled_at': (current_time + timedelta(minutes=5)).isoformat(),
        'is_sent': False,
        'created_at': current_time.isoformat(),
        'sent_at': None,
        'events': event_data,
        'participants': [
            {
                'users': {
                    'line_user_id': 'test-user-1',
                    'name': 'Test User 1'
                }
            },
            {
                'users': {
                    'line_user_id': 'test-user-2',
                    'name': 'Test User 2'
                }
            }
        ]
    }

@pytest.fixture
def mock_supabase():
    """Mock Supabase client"""
    mock = MagicMock()
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.execute.return_value = MagicMock(data=[])
    mock.context = MagicMock
    return mock

@pytest.fixture
def mock_line_bot():
    """Mock LINE Bot client"""
    mock = MagicMock()
    # reply_messageをAsyncMockに変更
    mock.reply_message = MagicMock()
    mock.reply_message.return_value = asyncio.Future()
    mock.reply_message.return_value.set_result(None)
    # push_messageも同様に
    mock.push_message = MagicMock()
    mock.push_message.return_value = asyncio.Future()
    mock.push_message.return_value.set_result(None)
    # プロファイル取得用のメソッドを追加
    mock.get_profile = MagicMock()
    mock.get_profile.return_value = asyncio.Future()
    mock.get_profile.return_value.set_result(
        MagicMock(display_name="Test User")
    )
    return mock

@pytest.fixture
def mock_discord_bot():
    """Mock Discord Bot client"""
    mock = MagicMock()
    mock.send_message = asyncio.Future()
    mock.send_message.set_result(None)
    return mock

@pytest.fixture
def mock_scheduler():
    """Mock Reminder Scheduler"""
    mock = MagicMock()
    mock.process_reminders = asyncio.Future()
    mock.process_reminders.set_result(None)
    mock.send_reminder = asyncio.Future()
    mock.send_reminder.set_result(None)
    return mock

@pytest.fixture
def mock_openai():
    """Mock OpenAI client"""
    mock = MagicMock()
    future_time = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
    
    # ChatCompletionのレスポンスをモック
    mock_response = MagicMock()
    mock_response.choices = [
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
    
    mock.ChatCompletion.create.return_value = mock_response
    return mock

@pytest.fixture
def mock_line_message_event():
    """Mock LINE Message Event"""
    def _create_message_event(text="test message"):
        return MagicMock(
            message=MagicMock(text=text),
            reply_token="test-reply-token",
            source=MagicMock(user_id="test-user")
        )
    return _create_message_event

@pytest.fixture
def mock_line_postback_event():
    """Mock LINE Postback Event"""
    def _create_postback_event(data="test_data"):
        return MagicMock(
            postback=MagicMock(data=data),
            reply_token="test-reply-token",
            source=MagicMock(user_id="test-user")
        )
    return _create_postback_event