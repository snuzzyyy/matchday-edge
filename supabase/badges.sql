-- Matchday Edge: badges (e.g. DEV) + protect plan and badges from being self-assigned.
-- Paste into Supabase > SQL Editor and press Run. Safe to run more than once.

alter table public.profiles add column if not exists badges text[] not null default '{}';

-- People can edit their own profile, but never their own plan or badges
drop policy if exists "own profile write" on public.profiles;
create policy "own profile write" on public.profiles for update
  using (auth.uid() = id)
  with check (
    auth.uid() = id
    and plan = (select p.plan from public.profiles p where p.id = auth.uid())
    and badges = (select p.badges from public.profiles p where p.id = auth.uid())
  );

-- Leaderboard also returns plan and badges
drop function if exists public.leaderboard();
create function public.leaderboard()
returns table (user_id uuid, display_name text, avatar_url text, plan text, badges text[], settled bigint, won bigint, staked numeric, profit numeric)
language sql stable security definer set search_path = public as $$
  select p.id, p.display_name, p.avatar_url, p.plan, p.badges,
         count(b.id) filter (where b.result in ('won','lost','void')),
         count(b.id) filter (where b.result = 'won'),
         coalesce(sum(b.stake) filter (where b.result in ('won','lost','void')), 0),
         coalesce(sum(coalesce(b.returns,0) - b.stake) filter (where b.result in ('won','lost','void')), 0)
  from public.profiles p left join public.bets b on b.user_id = p.id
  where (p.id = auth.uid() or public.is_friend(p.id)) and (p.show_on_leaderboard or p.id = auth.uid())
  group by p.id, p.display_name, p.avatar_url, p.plan, p.badges
  order by 9 desc
$$;
revoke all on function public.leaderboard() from public, anon;
grant execute on function public.leaderboard() to authenticated;

-- Give the owner Pro + the OWNER and DEV badges (matches the account by its friend code)
update public.profiles
set plan = 'pro', badges = array['owner','dev']
where friend_code = '690481';

-- Shows the result: you should see one row with plan = pro and badges = {owner,dev}
select display_name, plan, badges from public.profiles where friend_code = '690481';
