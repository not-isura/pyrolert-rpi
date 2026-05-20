ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS middle_name text null,
  ADD COLUMN IF NOT EXISTS employee_number text null;
