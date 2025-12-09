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
