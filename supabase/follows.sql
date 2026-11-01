-- Public profiles, following, app-wide top players and copyable public bets.
-- Safe to run more than once.

-- Profile settings: appear in search / top players (on by default), bets visible to everyone signed in (off by default).
alter table public.profiles add column if not exists discoverable boolean not null default true;
alter table public.profiles add column if not exists bets_public boolean not null default false;

-- One-way follows.
create table if not exists public.follows (
  follower uuid not null default auth.uid() references auth.users(id) on delete cascade,
  followee uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (follower, followee),
  check (follower <> followee)
);
alter table public.follows enable row level security;
drop policy if exists "follows read" on public.follows;
drop policy if exists "follow someone" on public.follows;
drop policy if exists "unfollow" on public.follows;
create policy "follows read" on public.follows for select to authenticated using (true);
create policy "follow someone" on public.follows for insert to authenticated with check (follower = auth.uid());
create policy "unfollow" on public.follows for delete to authenticated using (follower = auth.uid());

-- Public bets can be read by anyone signed in (only when the owner switched it on and is discoverable).
create or replace function public.bets_are_public(owner uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((select discoverable and bets_public from public.profiles where id = owner), false)
$$;
drop policy if exists "public bets read" on public.bets;
create policy "public bets read" on public.bets for select to authenticated using (public.bets_are_public(user_id));

-- A public profile card for a list of people (discoverable people, friends, or yourself).
drop function if exists public.people(uuid[]);
create function public.people(ids uuid[])
returns table (id uuid, display_name text, avatar_url text, badges text[], plan text, fav_teams jsonb, created_at timestamptz,
               followers bigint, following bigint, i_follow boolean, bets_public boolean, discoverable boolean)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.badges, p.plan, p.fav_teams, p.created_at,
    (select count(*) from public.follows f where f.followee = p.id),
    (select count(*) from public.follows f where f.follower = p.id),
    exists (select 1 from public.follows f where f.follower = auth.uid() and f.followee = p.id),
    p.bets_public, p.discoverable
  from public.profiles p
  where p.id = any(ids) and (p.discoverable or p.id = auth.uid() or public.is_friend(p.id))
$$;

-- Search people by name.
drop function if exists public.search_people(text);
create function public.search_people(q text)
returns table (id uuid, display_name text, avatar_url text, badges text[], plan text, followers bigint, i_follow boolean, bets_public boolean)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.badges, p.plan,
    (select count(*) from public.follows f where f.followee = p.id) as followers,
    exists (select 1 from public.follows f where f.follower = auth.uid() and f.followee = p.id),
    p.bets_public
  from public.profiles p
  where p.discoverable and p.id <> auth.uid() and (coalesce(q, '') = '' or p.display_name ilike '%' || q || '%')
  order by followers desc, p.display_name
  limit 30
$$;

-- Top players across the whole app: profit on bets settled in the last N days (at least 3 settled).
drop function if exists public.top_players(int);
create function public.top_players(days int default 30)
returns table (user_id uuid, display_name text, avatar_url text, badges text[], plan text, settled bigint, won bigint, staked numeric, profit numeric, bets_public boolean, i_follow boolean)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.badges, p.plan,
    count(*) as settled,
    count(*) filter (where b.result = 'won'),
    coalesce(sum(b.stake), 0),
    coalesce(sum(coalesce(b.returns, 0) - b.stake), 0) as profit,
    p.bets_public,
    exists (select 1 from public.follows f where f.follower = auth.uid() and f.followee = p.id)
  from public.profiles p join public.bets b on b.user_id = p.id
  where p.discoverable and p.show_on_leaderboard and b.result <> 'open'
    and coalesce(b.settled_at, b.placed_at) > now() - make_interval(days => days)
  group by p.id, p.display_name, p.avatar_url, p.badges, p.plan, p.bets_public
  having count(*) >= 3
  order by profit desc
  limit 25
$$;

revoke all on function public.people(uuid[]) from public, anon;
revoke all on function public.search_people(text) from public, anon;
revoke all on function public.top_players(int) from public, anon;
grant execute on function public.people(uuid[]) to authenticated;
grant execute on function public.search_people(text) to authenticated;
grant execute on function public.top_players(int) to authenticated;
