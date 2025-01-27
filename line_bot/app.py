from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, PostbackAction,
    PostbackEvent
)
import sys
import os
import asyncio
from typing import Optional
from datetime import datetime, timezone
import logging
from textwrap import shorten

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
    WEBHOOK_HANDLER_PATH,
    SUPABASE_URL,
    SUPABASE_ANON_KEY
)
from supabase import create_client, Client
from postgrest import APIError

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# LINE Bot API設定
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Supabase接続の再試行設定
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

async def get_supabase_client() -> Optional[Client]:
    """Supabaseクライアントの取得（再試行あり）"""
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Connecting to Supabase at {SUPABASE_URL} (attempt {attempt + 1})")
            supabase: Client = create_client(str(SUPABASE_URL), str(SUPABASE_ANON_KEY))
            # 接続テスト
            await asyncio.to_thread(lambda: supabase.table('events').select('count', count='exact').execute())
            logger.info("Supabase connection established")
            return supabase
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Failed to connect to Supabase (attempt {attempt + 1}): {e}")
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"Failed to connect to Supabase after {MAX_RETRIES} attempts: {e}")
                raise

# Supabase初期化
supabase: Optional[Client] = None

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の初期化"""
    global supabase
    supabase = await get_supabase_client()

@app.post(WEBHOOK_HANDLER_PATH)
async def webhook(request: Request):
    """LINEからのWebhookを処理"""
    signature = request.headers.get('X-Line-Signature', '')
    body = await request.body()
    body_decode = body.decode('utf-8')

    try:
        await asyncio.to_thread(handler.handle, body_decode, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature error")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Webhook handling error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
async def handle_message(event):
    """メッセージイベントの処理"""
    try:
        text = event.message.text.lower()
        
        if text == 'events':
            await show_event_list(event.reply_token)
        elif text.startswith('join '):
            event_id = text.split(' ')[1]
            await handle_event_join(event.reply_token, event_id, event.source.user_id)
        else:
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="以下のコマンドが使用できます：\n- events: イベント一覧の表示\n- join [イベントID]: イベントへの参加")
            )
    
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="申し訳ありません。エラーが発生しました。")
        )

@handler.add(PostbackEvent)
async def handle_postback(event):
    """ポストバックイベントの処理"""
    try:
        data = event.postback.data
        if data.startswith('join_'):
            event_id = data.split('_')[1]
            await handle_event_join(event.reply_token, event_id, event.source.user_id)
        elif data.startswith('cancel_'):
            event_id = data.split('_')[1]
            await handle_event_cancel(event.reply_token, event_id, event.source.user_id)
    
    except Exception as e:
        logger.error(f"Error handling postback: {e}")
        await line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="申し訳ありません。エラーが発生しました。")
        )

async def show_event_list(reply_token, page: int = 1, per_page: int = 5):
    """イベント一覧の表示（ページネーション対応）"""
    try:
        # 現在時刻以降のイベントのみを取得
        current_time = datetime.now(timezone.utc).isoformat()
        query = supabase.table('events')\
            .select('*')\
            .eq('status', 'scheduled')\
            .gte('start_date', current_time)\
            .order('start_date', desc=False)\
            .range((page-1)*per_page, page*per_page)
        
        result = await asyncio.to_thread(lambda: query.execute())
        
        if not result.data:
            await line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="現在予定されているイベントはありません。")
            )
            return

        # イベント一覧の作成
        events_text = "📅 予定されているイベント:\n\n"
        for event in result.data:
            start_time = datetime.fromisoformat(event['start_date'].replace('Z', '+00:00'))
            events_text += f"🎉 {event['name']}\n"
            events_text += f"📅 {start_time.strftime('%Y-%m-%d %H:%M')}\n"
            events_text += f"📍 {event['location']}\n"
            # 説明文を適切な長さに切り詰める
            description = shorten(event['description'], width=100, placeholder="...")
            events_text += f"ℹ️ {description}\n"
            events_text += f"参加するには: join {event['event_id']}\n\n"

        # ページネーション情報
        total_count = await asyncio.to_thread(
            lambda: supabase.table('events')
                .select('count', count='exact')
                .eq('status', 'scheduled')
                .gte('start_date', current_time)
                .execute()
        )
        total_pages = -(-total_count.count // per_page)  # 切り上げ除算

        if total_pages > 1:
            events_text += f"\nページ {page}/{total_pages}"
            if page < total_pages:
                events_text += "\n次のページを見るには 'events next' と入力してください。"

        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=events_text)
        )

    except Exception as e:
        logger.error(f"Error showing event list: {e}")
        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="イベント一覧の取得中にエラーが発生しました。")
        )

async def handle_event_join(reply_token, event_id, user_id):
    """イベント参加処理（トランザクション対応）"""
    try:
        # イベントの存在確認
        event_result = await asyncio.to_thread(
            lambda: supabase.table('events').select('*').eq('event_id', event_id).execute()
        )
        
        if not event_result.data:
            await line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="指定されたイベントは見つかりませんでした。")
            )
            return

        event = event_result.data[0]

        # イベントの開催時期チェック
        start_time = datetime.fromisoformat(event['start_date'].replace('Z', '+00:00'))
        if start_time < datetime.now(timezone.utc):
            await line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="このイベントは既に開始されているか終了しています。")
            )
            return

        # トランザクション開始
        async with asyncio.Lock():
            # 重複参加チェック
            existing_participant = await asyncio.to_thread(
                lambda: supabase.table('participants')
                    .select('*')
                    .eq('event_id', event['id'])
                    .eq('user_id', user_id)
                    .execute()
            )

            if existing_participant.data:
                await line_bot_api.reply_message(
                    reply_token,
                    TextSendMessage(text="既にこのイベントに参加登録されています。")
                )
                return

            # ユーザー情報の取得または作成
            user_result = await asyncio.to_thread(
                lambda: supabase.table('users').select('*').eq('line_user_id', user_id).execute()
            )
            
            if not user_result.data:
                # LINEプロファイルの取得
                profile = await asyncio.to_thread(lambda: line_bot_api.get_profile(user_id))
                user_data = {
                    'line_user_id': user_id,
                    'name': profile.display_name
                }
                user_result = await asyncio.to_thread(
                    lambda: supabase.table('users').insert(user_data).execute()
                )

            user = user_result.data[0]

            # 参加登録
            participant_data = {
                'event_id': event['id'],
                'user_id': user['id'],
                'status': 'registered'
            }
            await asyncio.to_thread(
                lambda: supabase.table('participants').insert(participant_data).execute()
            )

        # 参加確認メッセージの送信
        message = f"イベント「{event['name']}」への参加登録が完了しました！\n\n"
        message += f"📅 開始: {start_time.strftime('%Y-%m-%d %H:%M')}\n"
        message += f"📍 場所: {event['location']}"

        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=message)
        )

    except APIError as e:
        logger.error(f"Supabase API error: {e}")
        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="データベース処理中にエラーが発生しました。")
        )
    except Exception as e:
        logger.error(f"Error handling event join: {e}")
        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="イベントへの参加処理中にエラーが発生しました。")
        )

async def handle_event_cancel(reply_token, event_id, user_id):
    """イベント参加キャンセル処理"""
    try:
        # イベントの存在確認
        event_result = await asyncio.to_thread(
            lambda: supabase.table('events').select('*').eq('event_id', event_id).execute()
        )
        
        if not event_result.data:
            await line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="指定されたイベントは見つかりませんでした。")
            )
            return

        event = event_result.data[0]

        # ユーザー情報の取得
        user_result = await asyncio.to_thread(
            lambda: supabase.table('users').select('*').eq('line_user_id', user_id).execute()
        )

        if not user_result.data:
            await line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="ユーザー情報が見つかりませんでした。")
            )
            return

        user = user_result.data[0]

        # 参加登録の確認と削除
        participant_result = await asyncio.to_thread(
            lambda: supabase.table('participants')
                .select('*')
                .eq('event_id', event['id'])
                .eq('user_id', user['id'])
                .execute()
        )

        if not participant_result.data:
            await line_bot_api.reply_message(
                reply_token,
                TextSendMessage(text="このイベントへの参加登録が見つかりませんでした。")
            )
            return

        # トランザクション開始
        async with asyncio.Lock():
            # 参加登録の削除
            await asyncio.to_thread(
                lambda: supabase.table('participants')
                    .delete()
                    .eq('event_id', event['id'])
                    .eq('user_id', user['id'])
                    .execute()
            )

            # 参加者数の確認
            participants_count = await asyncio.to_thread(
                lambda: supabase.table('participants')
                    .select('count', count='exact')
                    .eq('event_id', event['id'])
                    .execute()
            )

            # 参加者が0人になった場合、イベントのステータスを更新
            if participants_count.count == 0:
                await asyncio.to_thread(
                    lambda: supabase.table('events')
                        .update({'status': 'pending'})
                        .eq('id', event['id'])
                        .execute()
                )

        # キャンセル確認メッセージの送信
        message = f"イベント「{event['name']}」の参加をキャンセルしました。"
        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=message)
        )

    except APIError as e:
        logger.error(f"Supabase API error: {e}")
        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="データベース処理中にエラーが発生しました。")
        )
    except Exception as e:
        logger.error(f"Error handling event cancel: {e}")
        await line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text="イベントのキャンセル処理中にエラーが発生しました。")
        )

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)