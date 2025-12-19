# Supabase RLS Edge Cases

RLS policies live in `intellex-infra/supabase/policies/rls_edge_policies.sql`. Apply that file in the Supabase SQL editor (run with the service role key or the dashboard SQL runner so `auth.uid()` is respected). Policies keep `users`, `projects`, `research_plans`, `messages`, and `project_shares` owner-only while still allowing the service role to manage rows.

## Quick Validation Snippets

Run these in the SQL editor to sanity-check RLS:

```sql
-- Pretend to be an authenticated user
select set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000000', true);
select set_config('request.jwt.claim.role', 'authenticated', true);

-- Expect only owned rows (or none) to return
select id, user_id from public.projects;
select project_id, content from public.messages;

-- Owner-only inserts should fail if project_id is not owned
insert into public.project_shares (id, project_id, email, access, invited_at)
values ('test-share', 'unowned-project', 'demo@example.com', 'viewer', extract(epoch from now()) * 1000);
```

Re-run with `set_config('request.jwt.claim.role', 'service_role', true);` to confirm the service role bypasses the policies for admin tasks.
