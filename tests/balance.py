"""
Balance check: pit skill builds against each other in every gambling event, no Shady Koala,
and count who wins. Uses the real scoring and tiebreaks (rules.rank), so it always matches
the game.

    python tests/balance.py                      # 10/0/0 vs 0/10/0 vs 0/0/10, 1000 seasons
    python tests/balance.py --seasons 5000 --seed 2
    python tests/balance.py --build 4/3/3 --build 0/10/0 --build 5/5/0   # STR/SPD/MCR

A season runs every event in rules.EVENTS once (the season draws 9 gambling events from a pool
of 9, so every season has all of them; only LUCK changes). A player "wins the season" here by
winning the most events; ties for most are shared. Money and betting are left out on purpose:
this only asks whether one build wins too many events.
"""
import argparse
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import rules as R  # noqa: E402

DEFAULT_BUILDS = ['10/0/0', '0/10/0', '0/0/10']


def parse_build(text):
    parts = [int(x) for x in text.split('/')]
    if len(parts) != 3 or any(p < 0 for p in parts) or sum(parts) > R.SKILL_POINTS:
        raise argparse.ArgumentTypeError(f'{text}: want STR/SPD/MCR adding up to at most {R.SKILL_POINTS}')
    return text, dict(zip(('str', 'spd', 'mcr'), parts))


def simulate(builds, seasons, rng):
    """Returns (event_wins {event: Counter(build)}, season_wins Counter, shared Counter)."""
    stats = dict(builds)
    events = [stop['event'] for stop in R.GAMBLE_STOPS]
    event_wins = {e: Counter() for e in events}
    season_wins, shared = Counter(), Counter()
    for _ in range(seasons):
        won = Counter()
        for event in events:
            winner = R.rank(stats, event, rng)[0][0]
            event_wins[event][winner] += 1
            won[winner] += 1
        top = max(won.values())
        leaders = [b for b in stats if won[b] == top]
        for b in leaders:
            (season_wins if len(leaders) == 1 else shared)[b] += 1
    return event_wins, season_wins, shared


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--build', action='append', type=parse_build, help='STR/SPD/MCR (repeat)')
    parser.add_argument('--seasons', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=27)
    args = parser.parse_args()
    builds = args.build or [parse_build(b) for b in DEFAULT_BUILDS]
    names = [name for name, _ in builds]
    if len(set(names)) != len(names):
        parser.error('each build must be different')

    event_wins, season_wins, shared = simulate(builds, args.seasons, random.Random(args.seed))
    width = max(len(n) for n in names) + 2
    head = f"{'Event':<32}" + ''.join(f'{n:>{width + 4}}' for n in names)
    print(f'{args.seasons} seasons, no Shady Koala. Event win rate per build (STR/SPD/MCR):\n')
    print(head)
    print('-' * len(head))
    total = Counter()
    for event, wins in event_wins.items():
        total.update(wins)
        print(f"{R.EVENTS[event]['name']:<32}" + ''.join(f'{wins[n] / args.seasons:>{width + 3}.0%} ' for n in names))
    print('-' * len(head))
    n_events = len(event_wins) * args.seasons
    print(f"{'All events':<32}" + ''.join(f'{total[n] / n_events:>{width + 3}.0%} ' for n in names))
    print(f"{'Events won per season (avg)':<32}" + ''.join(f'{total[n] / args.seasons:>{width + 4}.1f}' for n in names))
    print(f"{'Seasons won outright':<32}" + ''.join(f'{season_wins[n]:>{width + 4}}' for n in names))
    print(f"{'Seasons tied for most':<32}" + ''.join(f'{shared[n]:>{width + 4}}' for n in names))


if __name__ == '__main__':
    main()
