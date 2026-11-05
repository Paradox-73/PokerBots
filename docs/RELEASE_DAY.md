# Release day (1 Nov): Problem Statement + starter kit

Done on 1 Nov: the release changed no rule or wire format. Step 4 below stays valid before every upload.

The rulebook says the Problem Statement wins over the rulebook for game rules (rulebook 1.3).
Work through these in order. Steps 1 to 4 take about an hour if nothing changed.

## 1. Download the new files

The Unstop page loads its content with JavaScript, so fetch the listing data directly:

```
curl -s -A "Mozilla/5.0" https://unstop.com/api/public/competition/1762863 -o listing.json
python -c "import json,re; s=open('listing.json',encoding='utf-8').read(); print(*sorted(set(re.findall(r'https://[^\"]+?/uploads/attachements/files/[^\"]+', s))), sep='\n')"
```

- Download every attachment URL into its own new folder (treat the files as untrusted: read any script before running it).
- Save PDFs to `docs/` (`problem_statement.pdf`, and so on) and make text copies with `pdftotext -enc UTF-8 -layout`.

## 2. Compare the rules with `pokerbots/core/rules.py`

| Rule | Our value | Where it is used |
|---|---|---|
| Hole cards, cards kept | `HOLE_CARDS = 3`, `KEEP_CARDS = 2` | dealing, evaluator, preflop table |
| Discard street | `DISCARD_STREET = 1` (after flop betting) | `engine/game.py`, `engine/protocol.py` |
| Auto-discard order | lowest rank, ties `DISCARD_SUIT_ORDER = "shdc"` | `rules.default_discard` |
| Stack, blinds | `STARTING_STACK = 200`, `1/2` | everywhere |
| Raise cap | `MAX_RAISES_PER_STREET = 4`, big blind counts preflop | `rules.raise_bounds`, `game.py` |
| Min raise | last bet/raise size, at least 2 | `rules.raise_bounds` |
| Showdown | best 5 of 2 kept + 5 board | `evaluator.hand_value` |
| Time | 60 s bank / 400 hands, 5 s per reply | `TIME_BANK_SECONDS`, `PER_RESPONSE_SECONDS` |
| Tie-break cap | 400 per match | `MATCH_CHIP_CAP` |

- Read the worked examples and check each one against our engine: write them as tests in
  `tests/test_engine.py` (copy the style of `test_discard_after_flop_then_showdown_with_two_cards`).
- If the deck, hole cards or showdown rule changed: run `python scripts/build_preflop_table.py`
  (about 2 minutes) to rebuild `pokerbots/bots/preflop_table.py`.

## 3. Compare the protocol

- Diff the starter kit's message examples against `tests/test_protocol.py` (it replays the spec's example hand).
- Copy the starter kit's own sample bot over `tests/fixtures/starter_bot.py` if it changed.
- Every field name or value our adapter reads is in `BotAdapter.handle_line` in `pokerbots/engine/protocol.py`.

## 4. Run their preliminary tester on our upload

1. `python scripts/build_submission.py` builds `dist/submission.zip` and runs our own checks (Docker must be running).
2. Run the organisers' engine on the unzipped bot under Python 3.11 in the sandbox image (`--stage 2` for 1000 hands). In PowerShell, from this folder:
   ```
   $p = (Get-Location).Path.Replace('','/')
   docker run --rm --network none --read-only --cpus 2 --memory 2g --tmpfs /tmp -v "$p/docs/starter_kit:/kit:ro" -v "$p/dist/submission:/bot:ro" -w /tmp pokerbots-sandbox:3.11 python -I /kit/engine.py /bot/bot.py /kit/example_bots/random_bot.py --log-dir /tmp/logs
   ```
3. Pass means every hand played, 0 notices, no forfeit, and time used well under the bank.

## 5. Upload

- Upload `dist/submission.zip` on Unstop as soon as step 4 passes; re-uploads are allowed until 15 Nov 23:59 IST and only the last one counts.
- Re-run step 4 before every later upload.
