import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from supabase import Client
from linebot import LineBotApi
from linebot.models import TextSendMessage

logger = logging.getLogger(__name__)

class ReminderScheduler:
    def __init__(self, supabase: Client, line_bot_api: LineBotApi):
        self.supabase = supabase
        self.line_bot_api = line_bot_api
        self.running = True

    async def start(self):
        """リマインダースケジューラーの開始"""
        logger.info("Starting reminder scheduler...")
        while self.running:
            try:
                await self.process_reminders()
                await asyncio.sleep(60)  # 1分ごとにチェック
            except Exception as e:
                logger.error(f"Error in reminder scheduler: {e}")
                await asyncio.sleep(60)  # エラー時も1分待機

    async def stop(self):
        """スケジューラーの停止"""
        self.running = False

    async def process_reminders(self):
        """期限の来たリマインダーの処理"""
        try:
            current_time = datetime.now(timezone.utc)
            target_time = current_time + timedelta(minutes=5)

            # 未送信のリマインダーを取得
            reminders = await asyncio.to_thread(
                lambda: self.supabase.table('reminders')
                    .select('*, events(*)')
                    .is_('sent_at', 'null')
                    .lte('scheduled_at', target_time.isoformat())
                    .execute()
            )

            for reminder in reminders.data:
                try:
                    event = reminder['events']
                    if not event or event['status'] != 'scheduled':
                        continue

                    # メッセージの作成と送信
                    message = self.create_reminder_message(event, reminder['reminder_type'])
                    await self.send_reminder(event['id'], message)

                    # リマインダーを送信済みとしてマーク
                    await asyncio.to_thread(
                        lambda: self.supabase.table('reminders')
                            .update({
                                'sent_at': datetime.now(timezone.utc).isoformat()
                            })
                            .eq('id', reminder['id'])
                            .execute()
                    )
                except Exception as e:
                    logger.error(f"Error processing reminder {reminder['id']}: {e}")

        except Exception as e:
            logger.error(f"Error processing reminders: {e}")
            raise

    async def send_reminder(self, event_id: str, message: str):
        """リマインダーの送信"""
        try:
            # イベント参加者の取得
            participants = await asyncio.to_thread(
                lambda: self.supabase.table('participants')
                    .select('users(line_user_id)')
                    .eq('event_id', event_id)
                    .execute()
            )

            # 参加者へのメッセージ送信
            for participant in participants.data:
                user = participant['users']
                if user and user['line_user_id']:
                    try:
                        await asyncio.to_thread(
                            lambda: self.line_bot_api.push_message(
                                user['line_user_id'],
                                TextSendMessage(text=message)
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error sending reminder to user {user['line_user_id']}: {e}")

        except Exception as e:
            logger.error(f"Error sending reminder for event {event_id}: {e}")
            raise

    def create_reminder_message(self, event: Dict[Any, Any], reminder_type: str) -> str:
        """リマインダーメッセージの作成"""
        start_time = datetime.fromisoformat(event['start_date'].replace('Z', '+00:00'))
        formatted_time = start_time.strftime('%Y-%m-%d %H:%M')

        type_messages = {
            '1day': '明日',
            '3hours': '3時間後',
            '1hour': '1時間後'
        }
        time_text = type_messages.get(reminder_type, 'まもなく')

        message = (
            f"🔔 イベントリマインダー\n\n"
            f"「{event['name']}」が{time_text}開催されます！\n\n"
            f"📅 開始時刻: {formatted_time}\n"
            f"📍 場所: {event['location']}\n"
        )

        if event['description']:
            message += f"\nℹ️ {event['description']}\n"

        return message