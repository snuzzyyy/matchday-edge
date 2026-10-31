-- Matchday Edge accounts. Paste this whole file into Supabase > SQL Editor and press Run.

-- Profiles: one per user, created automatically at sign-up
create table if not exists public.profiles (
  id uuid primary key references auth.users on delete cascade,
  display_name text not null default 'Player',
  fav_teams jsonb not null default '[]'::jsonb,
  plan text not null default 'free' check (plan in ('free','pro')),
  show_on_leaderboard boolean not null default true,
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
drop policy if exists "own profile read" on public.profiles;
drop policy if exists "own profile write" on public.profiles;
drop policy if exists "own profile insert" on public.profiles;
create policy "own profile read"   on public.profiles for select using (auth.uid() = id);
create policy "own profile insert" on public.profiles for insert with check (auth.uid() = id);
create policy "own profile write"  on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id and plan = (select p.plan from public.profiles p where p.id = auth.uid()));

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(nullif(new.raw_user_meta_data->>'display_name',''), split_part(new.email,'@',1)))
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

-- Bets: each user's own bet log
create table if not exists public.bets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  placed_at timestamptz not null default now(),
  sport text,
  label text not null,
  match text,
  legs jsonb not null default '[]'::jsonb,
  odds_dec numeric(10,3) not null check (odds_dec >= 1),
  stake numeric(10,2) not null check (stake >= 0),
  result text not null default 'open' check (result in ('open','won','lost','void')),
  returns numeric(12,2),
  kickoff timestamptz
);
alter table public.bets enable row level security;
drop policy if exists "own bets" on public.bets;
create policy "own bets" on public.bets for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create index if not exists bets_user_idx on public.bets (user_id, placed_at desc);

-- £1 -> £1K challenge, one ladder per user
create table if not exists public.challenges (
  user_id uuid primary key default auth.uid() references auth.users on delete cascade,
  data jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.challenges enable row level security;
drop policy if exists "own challenge" on public.challenges;
create policy "own challenge" on public.challenges for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Pro waitlist
create table if not exists public.pro_waitlist (
  user_id uuid primary key default auth.uid() references auth.users on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.pro_waitlist enable row level security;
drop policy if exists "own waitlist" on public.pro_waitlist;
create policy "own waitlist" on public.pro_waitlist for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Mates' leaderboard: names and settled P/L only, for players who opt in
create or replace function public.leaderboard()
returns table (user_id uuid, display_name text, settled bigint, won bigint, staked numeric, profit numeric)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name,
         count(b.id) filter (where b.result in ('won','lost','void')),
         count(b.id) filter (where b.result = 'won'),
         coalesce(sum(b.stake) filter (where b.result in ('won','lost','void')), 0),
         coalesce(sum(coalesce(b.returns,0) - b.stake) filter (where b.result in ('won','lost','void')), 0)
  from public.profiles p left join public.bets b on b.user_id = p.id
  where p.show_on_leaderboard
  group by p.id, p.display_name
  order by 6 desc
  limit 50
$$;
revoke all on function public.leaderboard() from public, anon;
grant execute on function public.leaderboard() to authenticated;
