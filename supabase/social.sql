-- Matchday Edge: profile photos + friends. Paste into Supabase > SQL Editor and press Run. Safe to run more than once.

-- 1. Profile extras
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles add column if not exists share_bets boolean not null default true;
alter table public.profiles add column if not exists friend_code text;
update public.profiles set friend_code = upper(substr(md5(random()::text || id::text), 1, 6)) where friend_code is null;
alter table public.profiles alter column friend_code set default upper(substr(md5(random()::text), 1, 6));
create unique index if not exists profiles_friend_code_key on public.profiles (friend_code);
alter table public.bets add column if not exists settled_at timestamptz;

-- 2. Friendships (stored both ways)
create table if not exists public.friendships (
  user_id uuid not null references auth.users on delete cascade,
  friend_id uuid not null references auth.users on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, friend_id)
);
alter table public.friendships enable row level security;
drop policy if exists "see own friendships" on public.friendships;
create policy "see own friendships" on public.friendships for select using (auth.uid() = user_id);

create or replace function public.is_friend(other uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.friendships where user_id = auth.uid() and friend_id = other)
$$;
create or replace function public.shares_bets(other uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((select share_bets from public.profiles where id = other), false)
$$;

create or replace function public.add_friend(code text) returns text
language plpgsql security definer set search_path = public as $$
declare other uuid; nm text;
begin
  if auth.uid() is null then raise exception 'Sign in first'; end if;
  select id, display_name into other, nm from public.profiles where friend_code = upper(trim(code));
  if other is null then raise exception 'No one has that code'; end if;
  if other = auth.uid() then raise exception 'That is your own code'; end if;
  insert into public.friendships (user_id, friend_id) values (auth.uid(), other), (other, auth.uid()) on conflict do nothing;
  return nm;
end $$;
create or replace function public.remove_friend(other uuid) returns void
language sql security definer set search_path = public as $$
  delete from public.friendships where (user_id = auth.uid() and friend_id = other) or (user_id = other and friend_id = auth.uid())
$$;
revoke all on function public.add_friend(text), public.remove_friend(uuid) from public, anon;
grant execute on function public.add_friend(text), public.remove_friend(uuid) to authenticated;

-- 3. Mates can see each other's profile, challenge and (if shared) bets
drop policy if exists "friend profile read" on public.profiles;
create policy "friend profile read" on public.profiles for select using (public.is_friend(id));
drop policy if exists "friend bets read" on public.bets;
create policy "friend bets read" on public.bets for select using (public.is_friend(user_id) and public.shares_bets(user_id));
drop policy if exists "friend challenge read" on public.challenges;
create policy "friend challenge read" on public.challenges for select using (public.is_friend(user_id));

-- 4. Reactions on bets
create table if not exists public.reactions (
  bet_id uuid not null references public.bets on delete cascade,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  emoji text not null check (emoji in ('fire','lol','clap','yikes')),
  created_at timestamptz not null default now(),
  primary key (bet_id, user_id, emoji)
);
alter table public.reactions enable row level security;
drop policy if exists "see reactions on visible bets" on public.reactions;
drop policy if exists "react to visible bets" on public.reactions;
drop policy if exists "remove own reactions" on public.reactions;
create policy "see reactions on visible bets" on public.reactions for select using (exists (select 1 from public.bets b where b.id = bet_id));
create policy "react to visible bets" on public.reactions for insert with check (auth.uid() = user_id and exists (select 1 from public.bets b where b.id = bet_id));
create policy "remove own reactions" on public.reactions for delete using (auth.uid() = user_id);

-- 5. Leaderboard: you and your mates only
drop function if exists public.leaderboard();
create function public.leaderboard()
returns table (user_id uuid, display_name text, avatar_url text, settled bigint, won bigint, staked numeric, profit numeric)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url,
         count(b.id) filter (where b.result in ('won','lost','void')),
         count(b.id) filter (where b.result = 'won'),
         coalesce(sum(b.stake) filter (where b.result in ('won','lost','void')), 0),
         coalesce(sum(coalesce(b.returns,0) - b.stake) filter (where b.result in ('won','lost','void')), 0)
  from public.profiles p left join public.bets b on b.user_id = p.id
  where (p.id = auth.uid() or public.is_friend(p.id)) and (p.show_on_leaderboard or p.id = auth.uid())
  group by p.id, p.display_name, p.avatar_url
  order by 7 desc
$$;
revoke all on function public.leaderboard() from public, anon;
grant execute on function public.leaderboard() to authenticated;

-- 6. Profile photos (public bucket; each person can only write their own folder)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 2097152, array['image/webp','image/jpeg','image/png'])
on conflict (id) do update set public = true;
drop policy if exists "avatar read own" on storage.objects;
drop policy if exists "avatar upload own" on storage.objects;
drop policy if exists "avatar update own" on storage.objects;
drop policy if exists "avatar delete own" on storage.objects;
create policy "avatar read own" on storage.objects for select to authenticated using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "avatar upload own" on storage.objects for insert to authenticated with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "avatar update own" on storage.objects for update to authenticated using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "avatar delete own" on storage.objects for delete to authenticated using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
