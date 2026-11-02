-- Matchday Edge: comments on bets, "copied" marks, and the friends' leaderboard by week / month. Safe to run more than once.

-- 1. Comments on bets (anyone who can see the bet can comment; you can delete your own, and comments on your own bets)
create table if not exists public.comments (
  id uuid primary key default gen_random_uuid(),
  bet_id uuid not null references public.bets on delete cascade,
  user_id uuid not null default auth.uid() references auth.users on delete cascade,
  body text not null check (char_length(body) between 1 and 280),
  created_at timestamptz not null default now()
);
create index if not exists comments_bet_idx on public.comments (bet_id, created_at);
alter table public.comments enable row level security;
drop policy if exists "see comments on visible bets" on public.comments;
drop policy if exists "comment on visible bets" on public.comments;
drop policy if exists "delete own comments" on public.comments;
create policy "see comments on visible bets" on public.comments for select using (exists (select 1 from public.bets b where b.id = bet_id));
create policy "comment on visible bets" on public.comments for insert with check (auth.uid() = user_id and exists (select 1 from public.bets b where b.id = bet_id));
create policy "delete own comments" on public.comments for delete using (auth.uid() = user_id or exists (select 1 from public.bets b where b.id = bet_id and b.user_id = auth.uid()));

-- 2. "Copied" marks: copying someone's bet leaves a 'tail' reaction on it
alter table public.reactions drop constraint if exists reactions_emoji_check;
alter table public.reactions add constraint reactions_emoji_check check (emoji in ('fire','lol','clap','yikes','tail'));

-- 3. Friends' leaderboard over the last N days (0 = all time)
drop function if exists public.leaderboard_since(int);
create function public.leaderboard_since(days int default 0)
returns table (user_id uuid, display_name text, avatar_url text, plan text, badges text[], settled bigint, won bigint, staked numeric, profit numeric, best_odds numeric)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.plan, p.badges,
         count(b.id),
         count(b.id) filter (where b.result = 'won'),
         coalesce(sum(b.stake), 0),
         coalesce(sum(coalesce(b.returns, 0) - b.stake), 0),
         max(b.odds_dec) filter (where b.result = 'won')
  from public.profiles p left join public.bets b on b.user_id = p.id and b.result in ('won','lost','void')
    and (days <= 0 or coalesce(b.settled_at, b.placed_at) > now() - make_interval(days => days))
  where (p.id = auth.uid() or public.is_friend(p.id)) and (p.show_on_leaderboard or p.id = auth.uid())
  group by p.id, p.display_name, p.avatar_url, p.plan, p.badges
  order by 9 desc
$$;
revoke all on function public.leaderboard_since(int) from public, anon;
grant execute on function public.leaderboard_since(int) to authenticated;
