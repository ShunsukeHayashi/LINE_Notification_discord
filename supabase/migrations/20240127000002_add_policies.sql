-- RLSを有効化
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triggers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reminders ENABLE ROW LEVEL SECURITY;

-- eventsテーブルのポリシー
CREATE POLICY "events_read_policy" ON public.events
    FOR SELECT USING (true);

CREATE POLICY "events_insert_policy" ON public.events
    FOR INSERT WITH CHECK (true);

CREATE POLICY "events_update_policy" ON public.events
    FOR UPDATE USING (true);

-- usersテーブルのポリシー
CREATE POLICY "users_read_policy" ON public.users
    FOR SELECT USING (true);

CREATE POLICY "users_insert_policy" ON public.users
    FOR INSERT WITH CHECK (true);

CREATE POLICY "users_update_policy" ON public.users
    FOR UPDATE USING (true);

-- participantsテーブルのポリシー
CREATE POLICY "participants_read_policy" ON public.participants
    FOR SELECT USING (true);

CREATE POLICY "participants_insert_policy" ON public.participants
    FOR INSERT WITH CHECK (true);

CREATE POLICY "participants_update_policy" ON public.participants
    FOR UPDATE USING (true);

CREATE POLICY "participants_delete_policy" ON public.participants
    FOR DELETE USING (true);

-- triggersテーブルのポリシー
CREATE POLICY "triggers_read_policy" ON public.triggers
    FOR SELECT USING (true);

CREATE POLICY "triggers_insert_policy" ON public.triggers
    FOR INSERT WITH CHECK (true);

-- remindersテーブルのポリシー
CREATE POLICY "reminders_read_policy" ON public.reminders
    FOR SELECT USING (true);

CREATE POLICY "reminders_insert_policy" ON public.reminders
    FOR INSERT WITH CHECK (true);

CREATE POLICY "reminders_update_policy" ON public.reminders
    FOR UPDATE USING (true);

CREATE POLICY "reminders_delete_policy" ON public.reminders
    FOR DELETE USING (true);