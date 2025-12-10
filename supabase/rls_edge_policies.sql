-- Hardened RLS policies for owner-scoped access.
-- Apply with the service role key to ensure auth.uid()/auth.role() are available.

-- USERS: owners can see/update their own row; service_role bypasses for admin tasks.
alter table public.users enable row level security;
drop policy if exists "users_select_self" on public.users;
create policy "users_select_self"
    on public.users
    for select
    using (auth.uid()::text = id or auth.role() = 'service_role');

drop policy if exists "users_upsert_self" on public.users;
create policy "users_upsert_self"
    on public.users
    for all
    using (auth.uid()::text = id or auth.role() = 'service_role')
    with check (auth.uid()::text = id or auth.role() = 'service_role');

-- PROJECTS: only the owner (or service_role) can read/write.
alter table public.projects enable row level security;
drop policy if exists "projects_owner_only" on public.projects;
create policy "projects_owner_only"
    on public.projects
    for all
    using (user_id = auth.uid()::text or auth.role() = 'service_role')
    with check (user_id = auth.uid()::text or auth.role() = 'service_role');

-- RESEARCH_PLANS: scoped to parent project owner.
alter table public.research_plans enable row level security;
drop policy if exists "research_plans_owner" on public.research_plans;
create policy "research_plans_owner"
    on public.research_plans
    for all
    using (
        project_id in (
            select id from public.projects where user_id = auth.uid()::text
        ) or auth.role() = 'service_role'
    )
    with check (
        project_id in (
            select id from public.projects where user_id = auth.uid()::text
        ) or auth.role() = 'service_role'
    );

-- MESSAGES: owner-only access tied to parent project.
alter table public.messages enable row level security;
drop policy if exists "messages_owner" on public.messages;
create policy "messages_owner"
    on public.messages
    for all
    using (
        project_id in (
            select id from public.projects where user_id = auth.uid()::text
        ) or auth.role() = 'service_role'
    )
    with check (
        project_id in (
            select id from public.projects where user_id = auth.uid()::text
        ) or auth.role() = 'service_role'
    );

-- PROJECT_SHARES: only project owners can manage their shares.
alter table public.project_shares enable row level security;
drop policy if exists "project_shares_owner_manage" on public.project_shares;
create policy "project_shares_owner_manage"
    on public.project_shares
    for all
    using (
        project_id in (
            select id from public.projects where user_id = auth.uid()::text
        ) or auth.role() = 'service_role'
    )
    with check (
        project_id in (
            select id from public.projects where user_id = auth.uid()::text
        ) or auth.role() = 'service_role'
    );

-- USER_DEVICES: track authenticated sessions per device; only owners (or service_role) can read/update.
create table if not exists public.user_devices (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    device_id text not null,
    user_agent text,
    platform text,
    browser text,
    os text,
    timezone text,
    locale text,
    screen text,
    device_memory numeric,
    city text,
    region text,
    ip text,
    label text,
    is_trusted boolean default false,
    refresh_token_ciphertext text,
    first_seen_at bigint not null,
    last_seen_at bigint not null,
    last_login_at bigint,
    revoked_at bigint,
    inserted_at timestamptz default now(),
    updated_at timestamptz default now()
);

create unique index if not exists user_devices_user_device_uidx on public.user_devices (user_id, device_id);
create index if not exists user_devices_user_idx on public.user_devices (user_id);
create index if not exists user_devices_last_seen_idx on public.user_devices (last_seen_at desc);

alter table public.user_devices enable row level security;
drop policy if exists "user_devices_owner_only" on public.user_devices;
create policy "user_devices_owner_only"
    on public.user_devices
    for all
    using (user_id = auth.uid()::text or auth.role() = 'service_role')
    with check (user_id = auth.uid()::text or auth.role() = 'service_role');
