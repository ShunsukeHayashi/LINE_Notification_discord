-- リマインダー設定テーブルの作成
DROP TABLE IF EXISTS public.reminders CASCADE;

CREATE TABLE public.reminders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id UUID NOT NULL,
    reminder_type VARCHAR(50) NOT NULL, -- '1day', '3hours', '1hour'
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()),
    sent_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(event_id, reminder_type),
    CONSTRAINT fk_event
        FOREIGN KEY(event_id) 
        REFERENCES public.events(id)
        ON DELETE CASCADE
);

-- インデックスの作成
CREATE INDEX idx_reminders_scheduled ON reminders(scheduled_at) WHERE sent_at IS NULL;
CREATE INDEX idx_reminders_event ON reminders(event_id);

-- リマインダー設定用の関数
CREATE OR REPLACE FUNCTION create_event_reminders(
    p_event_id UUID,
    p_start_time TIMESTAMP WITH TIME ZONE
) RETURNS VOID AS $$
BEGIN
    -- 1日前のリマインダー
    INSERT INTO public.reminders (
        event_id,
        reminder_type,
        scheduled_at
    ) VALUES (
        p_event_id,
        '1day',
        p_start_time - INTERVAL '1 day'
    );

    -- 3時間前のリマインダー
    INSERT INTO public.reminders (
        event_id,
        reminder_type,
        scheduled_at
    ) VALUES (
        p_event_id,
        '3hours',
        p_start_time - INTERVAL '3 hours'
    );

    -- 1時間前のリマインダー
    INSERT INTO public.reminders (
        event_id,
        reminder_type,
        scheduled_at
    ) VALUES (
        p_event_id,
        '1hour',
        p_start_time - INTERVAL '1 hour'
    );
END;
$$ LANGUAGE plpgsql;

-- イベント作成時のトリガー
CREATE OR REPLACE FUNCTION create_reminders_on_event() RETURNS TRIGGER AS $$
BEGIN
    -- スケジュール済みのイベントの場合のみリマインダーを作成
    IF NEW.status = 'scheduled' THEN
        PERFORM create_event_reminders(NEW.id, NEW.start_date);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER create_reminders_after_event_insert
    AFTER INSERT ON events
    FOR EACH ROW
    EXECUTE FUNCTION create_reminders_on_event();

-- イベント更新時のトリガー
CREATE OR REPLACE FUNCTION update_reminders_on_event() RETURNS TRIGGER AS $$
BEGIN
    -- イベントがキャンセルされた場合、未送信のリマインダーを削除
    IF NEW.status = 'cancelled' THEN
        DELETE FROM public.reminders WHERE event_id = NEW.id AND sent_at IS NULL;
    -- 開始時刻が変更された場合、未送信のリマインダーを更新
    ELSIF NEW.start_date <> OLD.start_date THEN
        -- 1日前
        UPDATE public.reminders
        SET scheduled_at = NEW.start_date - INTERVAL '1 day'
        WHERE event_id = NEW.id AND reminder_type = '1day' AND sent_at IS NULL;
        
        -- 3時間前
        UPDATE public.reminders
        SET scheduled_at = NEW.start_date - INTERVAL '3 hours'
        WHERE event_id = NEW.id AND reminder_type = '3hours' AND sent_at IS NULL;
        
        -- 1時間前
        UPDATE public.reminders
        SET scheduled_at = NEW.start_date - INTERVAL '1 hour'
        WHERE event_id = NEW.id AND reminder_type = '1hour' AND sent_at IS NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_reminders_after_event_update
    AFTER UPDATE ON events
    FOR EACH ROW
    EXECUTE FUNCTION update_reminders_on_event();