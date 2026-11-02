-- Matchday Edge: free bets. Adds the free part of a bet's stake, and makes the leaderboards count only real money. Safe to run more than once.
alter table public.bets add column if not exists free_stake numeric(10,2) not null default 0;
drop function if exists public.leaderboard();
create function public.leaderboard()
returns table (user_id uuid, display_name text, avatar_url text, plan text, badges text[], settled bigint, won bigint, staked numeric, profit numeric)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.plan, p.badges,
         count(b.id) filter (where b.result in ('won','lost','void')),
         count(b.id) filter (where b.result = 'won'),
         coalesce(sum(b.stake - b.free_stake) filter (where b.result in ('won','lost','void')), 0),
         coalesce(sum(coalesce(b.returns,0) - (b.stake - b.free_stake)) filter (where b.result in ('won','lost','void')), 0)
  from public.profiles p left join public.bets b on b.user_id = p.id
  where (p.id = auth.uid() or public.is_friend(p.id)) and (p.show_on_leaderboard or p.id = auth.uid())
  group by p.id, p.display_name, p.avatar_url, p.plan, p.badges
  order by 9 desc
$$;
revoke all on function public.leaderboard() from public, anon;
grant execute on function public.leaderboard() to authenticated;
drop function if exists public.leaderboard_since(int);
create function public.leaderboard_since(days int default 0)
returns table (user_id uuid, display_name text, avatar_url text, plan text, badges text[], settled bigint, won bigint, staked numeric, profit numeric, best_odds numeric)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.plan, p.badges,
         count(b.id),
         count(b.id) filter (where b.result = 'won'),
         coalesce(sum(b.stake - b.free_stake), 0),
         coalesce(sum(coalesce(b.returns, 0) - (b.stake - b.free_stake)), 0),
         max(b.odds_dec) filter (where b.result = 'won')
  from public.profiles p left join public.bets b on b.user_id = p.id and b.result in ('won','lost','void')
    and (days <= 0 or coalesce(b.settled_at, b.placed_at) > now() - make_interval(days => days))
  where (p.id = auth.uid() or public.is_friend(p.id)) and (p.show_on_leaderboard or p.id = auth.uid())
  group by p.id, p.display_name, p.avatar_url, p.plan, p.badges
  order by 9 desc
$$;
revoke all on function public.leaderboard_since(int) from public, anon;
grant execute on function public.leaderboard_since(int) to authenticated;
drop function if exists public.top_players(int);
create function public.top_players(days int default 30)
returns table (user_id uuid, display_name text, avatar_url text, badges text[], plan text, settled bigint, won bigint, staked numeric, profit numeric, bets_public boolean, i_follow boolean)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.badges, p.plan,
    count(*) as settled,
    count(*) filter (where b.result = 'won'),
    coalesce(sum(b.stake - b.free_stake), 0),
    coalesce(sum(coalesce(b.returns, 0) - (b.stake - b.free_stake)), 0) as profit,
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
revoke all on function public.top_players(int) from public, anon;
grant execute on function public.top_players(int) to authenticated;
