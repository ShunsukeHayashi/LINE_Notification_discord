import discord
from discord.ext import commands, tasks
import sys
import os
import asyncio
from typing import Optional
from datetime import datetime, timedelta
import logging
from textwrap import shorten

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import DISCORD_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY
from supabase import create_client, Client
from postgrest import APIError

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guild_scheduled_events = True

# Supabase接続の再試行設定
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

class EventBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.supabase = None
        self.reconnect_task = None

    async def setup_supabase(self):
        """Supabaseクライアントの初期化（再試行あり）"""
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Connecting to Supabase at {SUPABASE_URL} (attempt {attempt + 1})")
                self.supabase = create_client(str(SUPABASE_URL), str(SUPABASE_ANON_KEY))
                # 接続テスト
                await asyncio.to_thread(lambda: self.supabase.table('events').select('count', count='exact').execute())
                logger.info("Supabase connection established")
                return True
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Failed to connect to Supabase (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Failed to connect to Supabase after {MAX_RETRIES} attempts: {e}")
                    return False

    async def setup_hook(self):
        """Bot起動時の初期設定"""
        logger.info("Setting up bot...")
        if await self.setup_supabase():
            await self.add_cog(EventCommands(self))
            self.check_connection.start()
        else:
            logger.error("Failed to initialize Supabase connection")
            await self.close()

    @tasks.loop(minutes=5)
    async def check_connection(self):
        """定期的な接続チェックとリトライ"""
        try:
            await asyncio.to_thread(lambda: self.supabase.table('events').select('count', count='exact').execute())
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            await self.setup_supabase()

class EventCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.events_per_page = 5

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot起動時の処理"""
        logger.info(f'Logged in as {self.bot.user.name}')

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event):
        """イベント作成時の処理"""
        try:
            async with asyncio.Lock():
                # イベントデータの作成
                event_data = {
                    'event_id': str(event.id),
                    'name': event.name,
                    'description': event.description or "説明なし",
                    'start_date': event.start_time.isoformat(),
                    'end_date': event.end_time.isoformat() if event.end_time else None,
                    'location': event.location or "場所未定",
                    'status': 'scheduled',
                    'created_by': str(event.creator.id)
                }
                
                # Supabaseにイベントを保存
                result = await asyncio.to_thread(
                    lambda: self.bot.supabase.table('events').insert(event_data).execute()
                )
                logger.info(f"Event created: {event.name}")

                # トリガーの作成（LINE通知用）
                trigger_data = {
                    'event_id': result.data[0]['id'],
                    'trigger_condition': 'event_created',
                    'message_content': f'新しいイベントが作成されました！\n\n{event.name}\n開始: {event.start_time}\n場所: {event.location or "場所未定"}'
                }
                await asyncio.to_thread(
                    lambda: self.bot.supabase.table('triggers').insert(trigger_data).execute()
                )
                
        except Exception as e:
            logger.error(f"Error handling event creation: {e}")

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before, after):
        """イベント更新時の処理"""
        try:
            async with asyncio.Lock():
                event_data = {
                    'name': after.name,
                    'description': after.description or "説明なし",
                    'start_date': after.start_time.isoformat(),
                    'end_date': after.end_time.isoformat() if after.end_time else None,
                    'location': after.location or "場所未定",
                    'status': 'scheduled' if after.status == discord.EventStatus.scheduled else 'cancelled'
                }
                
                await asyncio.to_thread(
                    lambda: self.bot.supabase.table('events')
                        .update(event_data)
                        .eq('event_id', str(after.id))
                        .execute()
                )
                logger.info(f"Event updated: {after.name}")

                # トリガーの作成（LINE通知用）
                trigger_data = {
                    'event_id': str(after.id),
                    'trigger_condition': 'event_updated',
                    'message_content': f'イベントが更新されました！\n\n{after.name}\n開始: {after.start_time}\n場所: {after.location or "場所未定"}'
                }
                await asyncio.to_thread(
                    lambda: self.bot.supabase.table('triggers').insert(trigger_data).execute()
                )

        except Exception as e:
            logger.error(f"Error handling event update: {e}")

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event):
        """イベント削除時の処理"""
        try:
            async with asyncio.Lock():
                await asyncio.to_thread(
                    lambda: self.bot.supabase.table('events')
                        .update({'status': 'cancelled'})
                        .eq('event_id', str(event.id))
                        .execute()
                )
                logger.info(f"Event cancelled: {event.name}")

                # トリガーの作成（LINE通知用）
                trigger_data = {
                    'event_id': str(event.id),
                    'trigger_condition': 'event_cancelled',
                    'message_content': f'イベントがキャンセルされました。\n\n{event.name}'
                }
                await asyncio.to_thread(
                    lambda: self.bot.supabase.table('triggers').insert(trigger_data).execute()
                )

        except Exception as e:
            logger.error(f"Error handling event deletion: {e}")

    @commands.command(name='events')
    async def list_events(self, ctx, page: int = 1):
        """登録されているイベントの一覧表示（ページネーション対応）"""
        try:
            # 現在時刻以降のイベントのみを取得
            current_time = datetime.utcnow().isoformat() + 'Z'
            result = await asyncio.to_thread(
                lambda: self.bot.supabase.table('events')
                    .select('*')
                    .eq('status', 'scheduled')
                    .gte('start_date', current_time)
                    .order('start_date', desc=False)
                    .range((page-1)*self.events_per_page, page*self.events_per_page)
                    .execute()
            )
            
            if not result.data:
                await ctx.send("現在予定されているイベントはありません。")
                return

            embed = discord.Embed(
                title="予定されているイベント",
                color=discord.Color.blue()
            )

            for event in result.data:
                start_time = datetime.fromisoformat(event['start_date'].replace('Z', '+00:00'))
                description = shorten(event['description'], width=100, placeholder="...")
                embed.add_field(
                    name=event['name'],
                    value=f"📅 開始: {start_time.strftime('%Y-%m-%d %H:%M')}\n"
                          f"📍 場所: {event['location']}\n"
                          f"ℹ️ {description}",
                    inline=False
                )

            # ページネーション情報の追加
            total_count = await asyncio.to_thread(
                lambda: self.bot.supabase.table('events')
                    .select('count', count='exact')
                    .eq('status', 'scheduled')
                    .gte('start_date', current_time)
                    .execute()
            )
            total_pages = -(-total_count.count // self.events_per_page)  # 切り上げ除算

            if total_pages > 1:
                embed.set_footer(text=f"ページ {page}/{total_pages} (!events <ページ番号> でページを切り替え)")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error listing events: {e}")
            await ctx.send("イベントの取得中にエラーが発生しました。")

    @commands.command(name='eventinfo')
    async def event_info(self, ctx, event_id: str):
        """特定のイベントの詳細情報表示"""
        try:
            result = await asyncio.to_thread(
                lambda: self.bot.supabase.table('events')
                    .select('*')
                    .eq('event_id', event_id)
                    .execute()
            )
            
            if not result.data:
                await ctx.send("指定されたイベントは見つかりませんでした。")
                return

            event = result.data[0]
            embed = discord.Embed(
                title=event['name'],
                description=event['description'],
                color=discord.Color.green()
            )

            start_time = datetime.fromisoformat(event['start_date'].replace('Z', '+00:00'))
            embed.add_field(name="開始時間", value=start_time.strftime('%Y-%m-%d %H:%M'), inline=True)
            
            if event['end_date']:
                end_time = datetime.fromisoformat(event['end_date'].replace('Z', '+00:00'))
                embed.add_field(name="終了時間", value=end_time.strftime('%Y-%m-%d %H:%M'), inline=True)
            
            embed.add_field(name="場所", value=event['location'], inline=True)
            embed.add_field(name="ステータス", value=event['status'], inline=True)

            # 参加者情報の取得
            participants = await asyncio.to_thread(
                lambda: self.bot.supabase.table('participants')
                    .select('users(name)')
                    .eq('event_id', event['id'])
                    .execute()
            )

            participant_count = len(participants.data)
            participant_names = [p['users']['name'] for p in participants.data]
            
            embed.add_field(
                name=f"参加者 ({participant_count}人)",
                value='\n'.join(participant_names) if participant_names else "まだ参加者はいません",
                inline=False
            )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error getting event info: {e}")
            await ctx.send("イベント情報の取得中にエラーが発生しました。")

    @commands.command(name='search')
    async def search_events(self, ctx, *, query: str):
        """イベントの検索"""
        try:
            # 現在時刻以降のイベントから検索
            current_time = datetime.utcnow().isoformat() + 'Z'
            result = await asyncio.to_thread(
                lambda: self.bot.supabase.table('events')
                    .select('*')
                    .eq('status', 'scheduled')
                    .gte('start_date', current_time)
                    .or_(f'name.ilike.%{query}%,description.ilike.%{query}%,location.ilike.%{query}%')
                    .order('start_date', desc=False)
                    .execute()
            )

            if not result.data:
                await ctx.send(f"「{query}」に一致するイベントは見つかりませんでした。")
                return

            embed = discord.Embed(
                title=f"検索結果: {query}",
                color=discord.Color.blue()
            )

            for event in result.data:
                start_time = datetime.fromisoformat(event['start_date'].replace('Z', '+00:00'))
                description = shorten(event['description'], width=100, placeholder="...")
                embed.add_field(
                    name=event['name'],
                    value=f"📅 開始: {start_time.strftime('%Y-%m-%d %H:%M')}\n"
                          f"📍 場所: {event['location']}\n"
                          f"ℹ️ {description}",
                    inline=False
                )

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Error searching events: {e}")
            await ctx.send("イベントの検索中にエラーが発生しました。")

# Botインスタンスの作成とエクスポート
bot = EventBot()

def run_bot():
    """Botの起動"""
    bot.run(DISCORD_TOKEN)

if __name__ == '__main__':
    run_bot()