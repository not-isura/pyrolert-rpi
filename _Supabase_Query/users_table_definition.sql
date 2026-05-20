create table public.users (
  id uuid not null default gen_random_uuid (),
  first_name text not null,
  last_name text not null,
  email text not null,
  role text not null,
  status text not null default 'active'::text,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  auth_user_id uuid null,
  constraint users_pkey primary key (id),
  constraint users_auth_user_id_unique unique (auth_user_id),
  constraint users_email_key unique (email),
  constraint users_auth_user_id_fkey foreign KEY (auth_user_id) references auth.users (id),
  constraint users_role_check check (
    (
      role = any (
        array[
          'admin'::text,
          'security'::text,
          'dean'::text,
          'facility'::text,
          'director'::text
        ]
      )
    )
  ),
  constraint users_status_check check (
    (
      status = any (array['active'::text, 'inactive'::text])
    )
  )
) TABLESPACE pg_default;