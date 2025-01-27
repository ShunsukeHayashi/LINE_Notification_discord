import asyncio
import uvicorn
from discord_bot.bot import EventBot
from line_bot.app import app, line_bot_api
from reminder.scheduler import ReminderScheduler
import logging
import sys
import signal
from concurrent.futures import ThreadPoolExecutor
from config.settings import DISCORD_TOKEN
from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_ANON_KEY

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EventNotificationSystem:
    def __init__(self):
        self.discord_bot = EventBot()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.running = True
        self.line_bot_server = None
        self.reminder_scheduler = None
        self.supabase = create_client(str(SUPABASE_URL), str(SUPABASE_ANON_KEY))

    async def start_discord_bot(self):
        """Discord Botの起動"""
        try:
            await self.discord_bot.start(DISCORD_TOKEN)
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
            await self.shutdown()

    def start_line_bot(self):
        """LINE Botの起動"""
        try:
            config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
            self.line_bot_server = uvicorn.Server(config)
            self.line_bot_server.run()
        except Exception as e:
            logger.error(f"LINE bot error: {e}")
            self.running = False
            # メインスレッドに例外を伝播させる
            raise

    async def start_reminder_scheduler(self):
        """リマインダースケジューラーの起動"""
        try:
            self.reminder_scheduler = ReminderScheduler(self.supabase, line_bot_api)
            await self.reminder_scheduler.start()
        except Exception as e:
            logger.error(f"Reminder scheduler error: {e}")
            await self.shutdown()

    async def run(self):
        """システム全体の起動"""
        logger.info("Starting Event Notification System...")

        # シグナルハンドラの設定
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(sig)))

        try:
            # LINE Bot、Discord Bot、リマインダースケジューラーを並行して起動
            line_bot_future = self.executor.submit(self.start_line_bot)
            discord_task = asyncio.create_task(self.start_discord_bot())
            reminder_task = asyncio.create_task(self.start_reminder_scheduler())

            # 全てのコンポーネントの状態を監視
            while self.running:
                # LINE Botのエラーチェック
                if line_bot_future.done():
                    exc = line_bot_future.exception()
                    if exc:
                        raise exc

                # Discord Botのエラーチェック
                if discord_task.done():
                    exc = discord_task.exception()
                    if exc:
                        raise exc

                # リマインダースケジューラーのエラーチェック
                if reminder_task.done():
                    exc = reminder_task.exception()
                    if exc:
                        raise exc

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"System error: {e}")
            await self.shutdown()

    async def shutdown(self, signal=None):
        """システムの終了処理"""
        if signal:
            logger.info(f"Received exit signal {signal.name}...")
        
        logger.info("Shutting down Event Notification System...")
        self.running = False

        # Discord Botの終了
        try:
            if self.discord_bot:
                await self.discord_bot.close()
        except Exception as e:
            logger.error(f"Error closing Discord bot: {e}")

        # LINE Botの終了
        try:
            if self.line_bot_server:
                self.line_bot_server.should_exit = True
                await asyncio.sleep(1)  # サーバーが終了するまで少し待つ
        except Exception as e:
            logger.error(f"Error closing LINE bot: {e}")

        # リマインダースケジューラーの終了
        try:
            if self.reminder_scheduler:
                await self.reminder_scheduler.stop()
        except Exception as e:
            logger.error(f"Error stopping reminder scheduler: {e}")

        # ThreadPoolExecutorの終了（待機してクリーンアップ）
        try:
            self.executor.shutdown(wait=True)
        except Exception as e:
            logger.error(f"Error shutting down executor: {e}")

        # 終了
        sys.exit(0)

def main():
    """メインエントリーポイント"""
    try:
        system = EventNotificationSystem()
        asyncio.run(system.run())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt...")
    except Exception as e:
        logger.error(f"System error: {e}")
    finally:
        logger.info("System shutdown complete.")

if __name__ == "__main__":
    main()