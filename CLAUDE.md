# Matchday Edge: notes for Claude

Read **HANDOVER.md** first. It covers the architecture, features, Supabase, the Android app, testing tricks and the owner's preferences.

Key rules:
- The whole app is `site/index.html`. The live site is GitHub Pages (`gh-pages`), deployed by `.github/workflows/update.yml` on every push to `main`.
- Owner is non-technical: do the work yourself, keep replies short and plain, and give click-by-click steps only for things that need their accounts (Supabase SQL, GitHub permissions).
- Dark mode only. Keep the artwork and icons. Say "Friends", not "mates". UK fractional odds and UK times.
- Test at 400px and 360px width with Playwright before pushing (route ESPN requests through curl; see HANDOVER.md §9).
- Never commit secrets (keystores, passwords, service_role keys) to this public repo.
- Don't run background monitors that post chat messages; the site updates itself.
