-- Matchday Edge / Accabox: the Accabox bot. Ready-made accas are saved before kick-off, settled by the server, and only winners are visible. Safe to run more than once.
create table if not exists public.bot_accas (
  id text primary key,
  day date not null,
  sport text not null,
  title text not null,
  level text not null,
  legs jsonb not null,
  odds_dec numeric(10,3) not null,
  chance numeric(6,4),
  kickoff timestamptz,
  result text not null default 'open' check (result in ('open','won','lost','void')),
  settled_at timestamptz,
  created_at timestamptz not null default now()
);
alter table public.bot_accas enable row level security;
drop policy if exists "bot winners are public" on public.bot_accas;
drop policy if exists "owner sees all bot accas" on public.bot_accas;
create policy "bot winners are public" on public.bot_accas for select to authenticated using (result = 'won');
create policy "owner sees all bot accas" on public.bot_accas for select to authenticated using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.badges && array['owner','dev']));
create or replace function public.bot_snapshot(rows jsonb) returns int
language plpgsql security definer set search_path = public as $$
declare n int := 0; r jsonb;
begin
  if not exists (select 1 from public.profiles p where p.id = auth.uid() and p.badges && array['owner','dev']) then raise exception 'Only the Accabox team can save bot accas'; end if;
  for r in select * from jsonb_array_elements(rows) loop
    insert into public.bot_accas (id, day, sport, title, level, legs, odds_dec, chance, kickoff)
    values (r->>'id', (r->>'day')::date, r->>'sport', r->>'title', r->>'level', r->'legs', (r->>'odds_dec')::numeric, (r->>'chance')::numeric, (r->>'kickoff')::timestamptz)
    on conflict (id) do nothing;
    if found then n := n + 1; end if;
  end loop;
  return n;
end $$;
revoke all on function public.bot_snapshot(jsonb) from public, anon;
grant execute on function public.bot_snapshot(jsonb) to authenticated;
