-- Betting balance: one row per person. Private unless they switch "Show my balance to friends" on.
create table if not exists public.wallets (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  amount numeric not null default 0,
  set_at timestamptz not null default now(),
  is_public boolean not null default false,
  updated_at timestamptz not null default now()
);
alter table public.wallets enable row level security;
drop policy if exists "wallet own" on public.wallets;
drop policy if exists "wallet friends read" on public.wallets;
create policy "wallet own" on public.wallets for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "wallet friends read" on public.wallets for select using (is_public and public.is_friend(user_id));
