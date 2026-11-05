<div align="center">

# Hakari: a Discard Hold'em bot

**Synergy '26 Pokerbots, IIIT Bangalore. Team Hakari.**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![NumPy only](https://img.shields.io/badge/Dependencies-stdlib%20%2B%20NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org/)
[![One file](https://img.shields.io/badge/Submission-one%20bot.py%2C%201.4%20MB-2a78d6?style=for-the-badge)](submission/bot.py)
<br>
[![Round robin 91 of 104](https://img.shields.io/badge/14--bot%20round%20robin-91%20of%20104%20points-1baf7a?style=for-the-badge&labelColor=0b1016)](#results-at-a-glance)
[![0 forfeits](https://img.shields.io/badge/Forfeits%20in%20testing-0-4fd1e0?style=for-the-badge&labelColor=0b1016)](#robustness)
[![1/6 speed CPU](https://img.shields.io/badge/1%2F6--speed%20CPU-inside%20the%20bank-f5a524?style=for-the-badge&labelColor=0b1016)](#robustness)

</div>

This repository is team Hakari's entry for the Pokerbots event of Synergy '26. The game is Discard Hold'em: heads-up no-limit Hold'em with three hole cards, where each player throws one card away face up after the flop betting. The submission is a single file, [`submission/bot.py`](submission/bot.py). It uses only the Python standard library and NumPy.

The bot makes every decision by expected value. It estimates its equity against a range of opponent hands, and it learns from this opponent's actions how often they fold, call and raise. A precomputed game-theory strategy, trained with counterfactual regret minimisation (CFR), follows every hand. When that strategy would almost never make a move in the current spot, the move is dropped. The result plays like an exploitative bot that stays close to sound play.

**Contents:**
[Results at a glance](#results-at-a-glance) ·
[The game](#the-game) ·
[Quick start](#quick-start) ·
[Repository layout](#repository-layout) ·
[Rules compliance](#rules-compliance) ·
[How the bot decides](#how-the-bot-decides) ·
[The solver](#the-solver) ·
[How we tested](#how-we-tested) ·
[What changed and why](#what-changed-and-why) ·
[Robustness](#robustness) ·
[Limitations](#limitations) ·
[Citations](#third-party-code-and-citations) ·
[Team](#team)

## Results at a glance

All numbers come from matches on the organisers' engine, in the official two-leg format, on deals never used to tune the bot. The files in [`results/`](results/) hold the raw summaries. In those files the entry is called `cand20`, its test name.

**Stage 2 round robin of the 14 strongest test bots** (500 duplicate deals per match, 8 deal sets per pair, 728 matches, [`results/round_robin_stage2.txt`](results/round_robin_stage2.txt)):

| Rank | Bot | Match points | Capped chips |
|---:|---|---:|---:|
| 1 | **Hakari (this bot)** | **91.0 of 104** | **+76,217** |
| 2 | f11, rival written from the official documents | 69.0 | +43,930 |
| 3 | cfrS, our CFR solver playing alone | 66.0 | +6,014 |
| 4 | f7, a second, independent CFR solver | 65.0 | +39,468 |
| 5 | rival_a | 64.0 | +7,360 |
| 6 | f10, rival built to exploit common styles | 62.0 | +25,499 |

The bot beat every other bot head to head except f7, where it won 4 of 8. Over all test runs it wins about two thirds of long matches against f7, which is its hardest opponent.

- **Bots built to beat it.** Two bots were written with the full source code of this bot in hand, each attacking a different weakness. One bets small on every flop. This bot won 28 of 32 long matches against it. The other sets traps: it checks strong hands and raises later. It came out even, 16 of 32 long matches and 15 of 32 short ones, and it is a copy of this bot with only the trap added ([`results/exploiters_vs_cand20.txt`](results/exploiters_vs_cand20.txt)).
- **Robustness.** 0 forfeits and 0 engine notices in every test. On a CPU slowed to one sixth of its speed, it used 25.1 s of the 30 s bank per Stage 1 leg and 64.6 s of 75 s per Stage 2 leg ([`results/slow_core_cand20.txt`](results/slow_core_cand20.txt)).

## The game

| Rule | Value |
|---|---|
| Players | 2, heads-up no-limit |
| Hole cards | 3 each. After the flop betting both players discard 1 card at the same time, and both discards are shown. Turn and river are played with 2 hole cards. |
| Stacks and blinds | 200 chips, reset every hand. Blinds 1 and 2. |
| Raises | At most 4 bets or raises per street. The big blind counts as the first one preflop. |
| Match | Two legs, each with fresh bot processes. Leg 2 replays every deal of leg 1 with cards and seats swapped. Stage 1: 200 deals per leg, 30 s time bank per leg. Stage 2: 500 deals per leg, 75 s per leg. |
| Scoring | The bot with more chips over both legs wins the match: 1 point, 0.5 for a draw. Tie-break: capped chips per hand (each match clipped to plus or minus 400 in Stage 1, 1,000 in Stage 2). |
| Tournament | Stage 1: 6-round Swiss. Stage 2: the top 32 play a full round robin, with scores reset. |

## Quick start

The organisers' starter kit (`engine.py`, `random_bot.py`, the rulebook and the protocol) is not included here. It is their material, and it belongs in `docs/starter_kit/`.

1. Use Python 3.11 with NumPy.

   ```
   pip install numpy
   ```

2. Play a Stage 2 match against the organisers' example bot.

   ```
   python docs/starter_kit/engine.py submission/bot.py docs/starter_kit/example_bots/random_bot.py --stage 2 --seed 1 --python "$(which python3.11)"
   ```

3. Build the upload zip: `bot.py` alone at the top level, with a fixed 1980-01-01 time stamp.

   ```
   python build/mkzip.py submission/bot.py dist/submission.zip
   ```

The bot reads nothing from disk, so the zip holds one file. `submission/bot.py` has md5 `51bb8eb8a2a6fcaa87fb2db7a099bd3e`.

## Repository layout

| Path | Contents |
|---|---|
| [`submission/bot.py`](submission/bot.py) | The entry. Self-contained: the decision code, the preflop table and the trained solver strategy, embedded as compressed text. |
| [`build/`](build/) | How the entry was assembled: `build_veto.py` merges the solver into the decision code, `cleanup.py` removes the lead-lock code the two-leg rules made useless, `fix20.py` applies the last three fixes, `mkzip.py` makes the upload zip. |
| [`solver/`](solver/) | The CFR trainer (`train.py`), the abstraction it solves (`bot/abstraction.py`), a standalone solver bot, self-checks and [`NOTES.md`](solver/NOTES.md). `bot/strategy.py` here is a small untrained smoke table. The trained table is the one inside `submission/bot.py`. |
| [`lab/`](lab/) | The test harness: match runners, paired comparisons, the round robin, the divergence analysis, test-opponent generators and the release checks. See [How we tested](#how-we-tested). |
| [`lab/candidates/`](lab/candidates/) | Patches for changes that were tested and either rejected or are still being tested. |
| [`results/`](results/) | Result summaries cited in this README. |
| [`decisions.tsv`](decisions.tsv) | One row per decision: what, why, the evidence, and what happened. |
| [`pokerbots/`](pokerbots/), [`scripts/`](scripts/), [`tests/`](tests/) | The first framework: our own engine, hand evaluator, equity code and early bots, with unit tests. The final bot no longer imports it, but it holds the evaluator tests and the early experiments. |
| [`docs/RELEASE_DAY.md`](docs/RELEASE_DAY.md) | The checklist for an upload. |

## Rules compliance

| Rule | What this entry does |
|---|---|
| Python 3.11, standard library, NumPy and SciPy only | Standard library and NumPy. Tested under NumPy 2.4.6, 1.26 and 1.23 on Python 3.11 ([`results/numpy_versions_cand20.txt`](results/numpy_versions_cand20.txt)). |
| One `bot.py`, or a zip with `bot.py` at the top, at most 5 MB | One `bot.py` of 1.4 MB. The zip is 1.4 MB. |
| No writing files, no network, no subprocesses | None of these are used. All tables are embedded in the file and decoded in memory at start-up. |
| 1 vCPU, 1 GB RAM | Runs on one core. Peak memory 75 MB. |
| Time bank, crash means forfeit | The bot paces itself against the bank and gets simpler when time runs short (see [Robustness](#robustness)). Any exception inside a decision falls back to a legal check, fold or discard, so a bad message cannot crash it. |
| Own work, no copied bot code | All code was written by the team. The algorithms are published ones: CFR and its discounted variant, pseudo-harmonic action mapping, Bayesian range updates. See [Citations](#third-party-code-and-citations). |
| No state between legs | Each leg starts from the same priors. Nothing is written or read between legs. |

## How the bot decides

```mermaid
flowchart TD
    REQ["action_request<br/>from the engine"]:::io --> ST["Replay the history:<br/>pot, bets, raise count,<br/>opponent action classes"]:::step
    ST --> RNG["Opponent range<br/>(all 1326 two-card hands,<br/>or all 3-card hands before the discard)<br/>narrowed by every action<br/>and by the shown discard"]:::step
    ST --> OPP["Opponent model<br/>fold / call / raise counters<br/>by street, raise level, bet size<br/>backed off onto priors"]:::step
    RNG --> EQ["Equity against each slice<br/>of the range (NumPy, all runouts<br/>or sampled ones)"]:::step
    OPP --> EV["Expected value of<br/>fold, check, call and<br/>3 to 5 raise sizes"]:::step
    EQ --> EV
    ST --> SOL["Solver view:<br/>the CFR strategy's fold / call / raise<br/>shares in the matching abstract spot"]:::sol
    EV --> VETO{"Option kind the solver<br/>plays under 10% here?"}:::cut
    SOL --> VETO
    VETO -- "yes, drop it<br/>(if another is left)" --> PICK
    VETO -- no --> PICK["Softmax over the EVs<br/>temperature max(0.25, 0.012 x pot)"]:::step
    PICK --> OUT["action reply"]:::io

    classDef io fill:#0b1016,stroke:#4fd1e0,stroke-width:2px,color:#e6edf3
    classDef step fill:#16212c,stroke:#4fd1e0,color:#e6edf3
    classDef sol fill:#2a78d6,stroke:#1d5aa3,color:#ffffff
    classDef cut fill:#f5a524,stroke:#c4831a,color:#0b1016
```

1. **State.** Every request replays the history the engine sends. The bot tracks the pot, both bets, the raise count and the class of each opponent action: fold, check or call, or raise (small, medium, big, all-in). A test harness confirmed the tracked state matches the engine's on every request over 300 hands against 6 styles of opponent.
2. **Hand tables.** On each street, NumPy scores all 1,326 two-card hands on the current board. The turn and river are enumerated exactly. The flop samples 240 runouts, fewer if time runs short. Preflop and flop decisions use 3-card hands and a model of which two cards each player will keep.
3. **Opponent range.** A weight for every possible opponent hand. Each opponent action is read as a slice of the strength order. For example, a raise that this opponent makes 20% of the time keeps the strongest 20% of the remaining range, softened by a learnt rate of off-pattern plays such as bluffs and slow-plays. The shown discard removes hands the opponent would not have thrown that card from. The model of how this opponent discards (best keep, lowest card, or random) is learnt from showdowns.
4. **Opponent model.** Counters of the opponent's fold, call and raise choices, kept at three levels of detail (all streets, per street, per bet size). They start from priors and move towards this opponent's actual habits.
5. **Expected value.** Fold is 0. A call wins its equity share of the pot, adjusted for the streets still to come. A raise adds the chance the opponent folds now, and values their call and their re-raise separately. Raise sizes come from the pot (a third, two thirds, one pot, one and a half pots, all-in) and from the bet faced.
6. **Solver check.** The CFR strategy follows the same hand. If it plays an option kind (fold, check or call, raise) under 10% of the time in the matching spot, that kind is removed, as long as another option remains. Exploiting an opponent can then never take the bot far from sound play. Two cases switch the check off: a bet the solver's tree has no size for, and a spot that has left the tree.
7. **Choice.** A softmax over the remaining EVs. Options more than three temperatures below the best are never picked. The randomness stops an observant opponent from reading exact thresholds.

## The solver

The trainer and the abstraction are in [`solver/`](solver/), and [`solver/NOTES.md`](solver/NOTES.md) gives the details.

| Part | Choice |
|---|---|
| Cards, preflop | Exact suit-isomorphic class of the 3 hole cards: 1,755 buckets |
| Cards, flop | Mean and spread of the best two-card keep's percentile over 48 fixed runouts: 512 buckets |
| Cards, turn and river | Strength against the opponent's plausible kept hands: 192 buckets each |
| Bets | Preflop open 1 or 2 pots, first re-raise 0.75 pot. Postflop first bet 0.33, 0.66 or 1 pot, first raise 0.75 pot. Later raises are all-in only. All-in is always offered. |
| Tree | 6,476 public states, 3,392 decision nodes, 758,044 information sets |
| Training | Chance-sampled discounted CFR (alpha 1.5, beta 0, gamma 2) on 19.2 M pre-dealt deals, NumPy passes over the whole tree, 14 worker processes |
| Real bets onto the tree | Randomised pseudo-harmonic mapping between the two nearest abstract sizes, fixed for the rest of the hand |

Playing alone, the solver came third in the round robin above. It is hard to beat, and it never adapts to a weak opponent. Inside Hakari it serves as the safety check described above.

## How we tested

**Match format.** Every test match uses the organisers' engine and the official two-leg format. Each deal is played twice with cards and seats swapped, so card luck largely cancels out.

**Paired comparisons.** A change is tested by running the old and the new version on the same deal sets against the same opponents. Each result below gives the difference with its standard error (se), the size of the swing that luck alone can cause. A difference under 2 se is treated as no difference. Seeds are never reused once a decision has been made on them.

**Test field** (33 opponents):

| Group | Bots |
|---|---|
| CFR solvers | cfrS (ours, alone), cfr2 (a smaller solver), f7 and f9 (independent solvers) |
| Rivals written only from the organisers' documents | f1 to f11, each written separately with no view of our code. f10 targets common styles. f11 is the strongest of them. |
| Earlier rival bots | rival_a, rival_b, rival_c and two variants, plus locker, which folds out a leg once its lead covers the remaining blinds |
| Fixed styles | 14 simple bots: always call, always shove, maniac, nit, min-raiser, pot-odds caller, loose, tight and others |

**Test opponents for single weaknesses.** Wrappers rewrite one habit of a strong bot and leave the rest unchanged. The generators are in `lab/`: `minrr_gen.py` makes re-raises minimum-sized, `disc_gen.py` discards the lowest card as the starter kit does, `minbet_gen.py` bets the minimum. A fix has to win its targeted test and must not lose to the general field.

**Code reviews and bots built to beat it.** Several independent reviews each checked one part of the code by running it: state tracking, EV formulas, equity numbers against a brute-force count, and every assumption the solver makes. Two bots were also written with full access to the code to beat this one. Each finding became a candidate change and went through the paired tests.

**Main tools in `lab/`:**

| Tool | Job |
|---|---|
| `legrun.py`, `rrun.py` | Run many two-leg matches in parallel on the organisers' engine (one bot against many, or all pairs) |
| `legsum.py`, `mrsum.py`, `rrsum.py` | Paired comparison with standard errors, per-opponent tables, round-robin standings |
| `dup.py` | Duplicate-deal divergence: finds the first decision where we and the opponent chose differently with the same cards, and totals the chips that followed |
| `rr.py` | How deep re-raises are sized and answered |
| `gen_pre2.py` | Rebuilds the preflop table with exact card removal, with a brute-force self-test |
| `newcheck.sh`, `slow6.sh`, `npcheck.sh` | Release checks: organiser engine, unknown messages, start-up time, memory, slowed CPU, older NumPy |

## What changed and why

[`decisions.tsv`](decisions.tsv) holds the full log. The main steps:

| Change | Evidence | Result |
|---|---|---|
| Expected-value bot with an opponent model | Beats every rule-based style, but lost about 1.2 chips per hand to our CFR solver | Base of the entry |
| Hybrid: solver plays the first part of each match, the EV bot the rest | No gain over 1,000 hands against the solver | Rejected |
| Solver check on option kinds from the flop on, threshold 10% (2%, 5% and 10% tried) | 345 of 380 test matches won, against 326 for the EV bot alone | Kept |
| Solver check from preflop | +20 points (se 7.7) over 308 Stage 2 matches | Kept |
| Lead lock (fold out once the lead covers the blinds left) | Under the two-leg rules a leg cannot see the other leg's chips, so a lead is never safe | Removed; same moves proven on fixed seeds |
| Softmax temperature halved or doubled | Both directions came out "better" (+5, se 5.6 and +6, se 4.9), a sign of luck on shared deals | Rejected |
| A small re-raise late in a betting round was read as an all-in by the solver's tree, forcing folds | Against bots that re-raise small: +172 capped chips per match (se 86) and +3 points (se 2.6); no change against the general field (-4 points, se 9.4, over 488 matches) | Kept in the entry |
| Discard named by the card itself, not its position in the message | No effect with the current engine; protects against a reordered message | Kept |
| Solver check off after the flop against bots that discard by a fixed rule | Against such bots: -12 points (se 3.3) over 96 Stage 2 matches ([`results/cand21_rejected.txt`](results/cand21_rejected.txt)) | Rejected |
| Being tested | Exact card removal in the preflop table; slow-play rate learnt from the right count; three corrections to how real bets meet the solver's tree; no solver check with nothing to call | See `lab/candidates/` |

## Robustness

From [`results/engine_checks_cand20.txt`](results/engine_checks_cand20.txt), [`results/slow_core_cand20.txt`](results/slow_core_cand20.txt) and [`results/numpy_versions_cand20.txt`](results/numpy_versions_cand20.txt):

| Check | Result |
|---|---|
| Organiser engine, Stage 1 and Stage 2, against the starter and random bots | 0 notices, 0 lines on stderr |
| Time used, Stage 2 against the starter bot | About 28 s of the 75 s bank per leg |
| CPU slowed to one sixth (5 busy processes on the same core) | Stage 1: 25.1 s of 30 s per leg. Stage 2: 64.6 s of 75 s per leg. 0 notices. |
| Start-up to exit | 0.81 to 0.82 s (limit 5 s) |
| Peak memory | 75 MB (limit 1 GB) |
| Unknown message types and fields | Ignored, 0 notices |
| A 998-hand match | Clean |
| NumPy 1.26 and 1.23 | Clean |

How the bot handles time: the solver view runs only while the match is ahead of a schedule that spreads 80% of the bank evenly over the hands. Flop runouts shrink from 240 to 60 when the bank runs low. Below 1 s of bank it checks or folds. Replies take well under the 5 s per-reply limit.

## Limitations

- Every opponent we tested against was built by us or written for this test. None is a real entrant, so the strength of the real field is unknown.
- f7, an independent CFR solver, is the closest matchup: about two wins in three over long matches. A stronger solver than any we built could beat this bot.
- The bot that sets traps came out even with this bot. It may hold a small real edge (about 0.2 chips per hand), within luck so far. A fix is being tested.
- The opponent model starts from the same priors in both legs. Learning restarts with each fresh process, as the rules require.
- On a machine much slower than one sixth of our test server, the flop runouts and the solver view are cut back, and play gets simpler.

## Third-party code and citations

- NumPy, for all array work. No other library.
- Counterfactual regret minimisation: M. Zinkevich, M. Johanson, M. Bowling, C. Piccione, "Regret Minimization in Games with Incomplete Information", NeurIPS 2007.
- Discounted CFR: N. Brown, T. Sandholm, "Solving Imperfect-Information Games via Discounted Regret Minimization", AAAI 2019.
- Monte Carlo sampling for CFR: M. Lanctot, K. Waugh, M. Zinkevich, M. Bowling, "Monte Carlo Sampling for Regret Minimization in Extensive Games", NeurIPS 2009.
- Pseudo-harmonic action mapping: S. Ganzfried, T. Sandholm, "Action Translation in Extensive-Form Games with Large Action Spaces", IJCAI 2013.
- The organisers' starter kit and engine were used for testing. They are not redistributed here.

## Team

Team Hakari, Synergy '26 Pokerbots, IIIT Bangalore:

- Bhavya Jain
- Kanav Bhardwaj
