import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from linebot.models import TextSendMessage
from reminder.scheduler import ReminderScheduler

@pytest.mark.unit
@pytest.mark.reminder
class TestReminderScheduler:
    @pytest.fixture
    def mock_line_bot_api(self):
        """Set up LINE Bot API mock"""
        mock = MagicMock()
        mock.push_message = AsyncMock()
        return mock

    @pytest.fixture
    def mock_supabase(self):
        """Set up Supabase mock"""
        mock = MagicMock()
        return mock

    def create_mock_reminder(self, event_data, reminder_type='1hour'):
        """Create a mock reminder data"""
        start_time = datetime.now(timezone.utc) + timedelta(hours=1)
        scheduled_at = start_time - timedelta(hours=1)
        
        return {
            'id': 'test-reminder-id',
            'event_id': event_data['id'],
            'reminder_type': reminder_type,
            'scheduled_at': scheduled_at.isoformat(),
            'is_sent': False,
            'events': {
                'id': event_data['id'],
                'name': event_data['name'],
                'description': event_data['description'],
                'start_time': start_time.isoformat(),
                'location': event_data['location'],
                'status': 'scheduled'
            },
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

    @pytest.mark.asyncio
    async def test_process_reminders(self, mock_line_bot_api, mock_supabase, event_data):
        """Test reminder processing"""
        # リマインダーデータの設定
        reminder = self.create_mock_reminder(event_data)
        mock_supabase.table().select().eq().lte().execute.return_value.data = [reminder]
        
        # スケジューラーの作成と実行
        scheduler = ReminderScheduler(mock_supabase, mock_line_bot_api)
        await scheduler.process_reminders()

        # 通知の送信を確認
        assert mock_line_bot_api.push_message.call_count == 2  # 2人の参加者
        
        # メッセージ内容の確認
        calls = mock_line_bot_api.push_message.call_args_list
        for call in calls:
            args = call[0]
            assert isinstance(args[1], TextSendMessage)
            assert event_data['name'] in args[1].text
            assert '1時間後' in args[1].text
            assert event_data['location'] in args[1].text

        # リマインダーのステータス更新を確認
        mock_supabase.table().update.assert_called_once()
        update_call = mock_supabase.table().update.call_args[0][0]
        assert update_call['is_sent'] is True
        assert 'sent_at' in update_call

    @pytest.mark.asyncio
    async def test_reminder_message_creation(self, mock_line_bot_api, mock_supabase, event_data):
        """Test reminder message creation for different types"""
        scheduler = ReminderScheduler(mock_supabase, mock_line_bot_api)

        # 各リマインダータイプのメッセージをテスト
        reminder_types = {
            '1day': '明日',
            '3hours': '3時間後',
            '1hour': '1時間後'
        }

        for reminder_type, expected_text in reminder_types.items():
            reminder = self.create_mock_reminder(event_data, reminder_type)
            message = scheduler.create_reminder_message(reminder)
            
            assert event_data['name'] in message
            assert expected_text in message
            assert event_data['location'] in message
            assert event_data['description'] in message

    @pytest.mark.asyncio
    async def test_cancelled_event_reminder(self, mock_line_bot_api, mock_supabase, event_data):
        """Test handling of cancelled event reminders"""
        # キャンセルされたイベントのリマインダー
        reminder = self.create_mock_reminder(event_data)
        reminder['events']['status'] = 'cancelled'
        
        mock_supabase.table().select().eq().lte().execute.return_value.data = [reminder]
        
        # スケジューラーの作成と実行
        scheduler = ReminderScheduler(mock_supabase, mock_line_bot_api)
        await scheduler.process_reminders()

        # キャンセルされたイベントの通知は送信されないことを確認
        mock_line_bot_api.push_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_line_bot_api, mock_supabase, event_data):
        """Test error handling during reminder processing"""
        # エラーを発生させる設定
        reminder = self.create_mock_reminder(event_data)
        mock_supabase.table().select().eq().lte().execute.return_value.data = [reminder]
        mock_line_bot_api.push_message.side_effect = Exception("Test error")

        # スケジューラーの作成と実行
        scheduler = ReminderScheduler(mock_supabase, mock_line_bot_api)
        await scheduler.process_reminders()

        # エラーが発生しても処理が継続することを確認
        mock_supabase.table().update.assert_called_once()  # リマインダーは送信済みとしてマークされる