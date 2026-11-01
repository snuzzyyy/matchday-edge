# Matchday Edge: notes for Claude

Read **HANDOVER.md** first. **§0 is the first job (NBA player bets in the acca builder, swapping legs, more than 3 legs).** §11 lists mistakes not to repeat.

Key rules:
- The whole app is `site/index.html`. The live site is GitHub Pages (`gh-pages`), deployed by `.github/workflows/update.yml` on every push to `main` and every 20 minutes (which also runs `engine/build.py` and `engine/settle.py`).
- The owner isn't technical: do the work yourself, keep replies short and plain, and give click-by-click steps only for things that need their accounts (Supabase SQL on one line, GitHub secrets/uploads).
- Dark mode only. Keep the artwork and icons. Say "Friends", not "mates". UK fractional odds and UK times.
- Test at 400px and 360px width with Playwright before pushing (route ESPN through curl, mock Supabase; see HANDOVER.md §9). Run the JS syntax check after every edit.
- Never put `//` comments in the middle of a code line; grep a CSS class name before adding it; filter "my" queries by `user_id`.
- Never commit secrets (keystores, passwords, Supabase secret keys) to this public repo, and never ask for them in chat.
- Don't run background monitors that post chat messages; the site updates itself.
