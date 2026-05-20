-- Allow the RPi (anon key) to read active user emails for alert email notifications
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_users"
  ON public.users FOR SELECT
  USING (auth.role() = 'anon');
