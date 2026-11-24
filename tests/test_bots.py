"""
Virtual-user tests: bots play whole seasons with timers sped up 20x.

    python tests/test_bots.py            # full matrix, 3 seeds per scenario
    python tests/test_bots.py --quick    # 1 seed

New phase or action -> teach DerbyBot.decide() in the same change.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from apge.testing import Bot, run_matrix, standard_scenarios  # noqa: E402

import rules as R  # noqa: E402
from game import Derby  # noqa: E402

STEP = R.MONEY_STEP


class DerbyBot(Bot):
    """Plays one action per state change; the next state update triggers the next move."""

    def decide(self, view):
        me, data, phase = view['me'], view['data'], view['phase']
        private = me['private']
        handler = getattr(self, 'play_' + phase, None)
        return handler(view, me, private, data) if handler else None

    def play_lobby(self, view, me, private, data):
        if 'head' not in me:
            art = ''.join(self.rng.choice('.' + R.PIXEL_CHARS) for _ in range(R.HEAD_GRID ** 2))
            return [('submit_head', {'head': art})]
        if not me.get('character_done'):
            points = [0, 0, 0]
            for _ in range(self.rng.randint(0, R.SKILL_POINTS)):
                points[self.rng.randrange(3)] += 1
            return [('submit_stats', dict(zip(('str', 'spd', 'mcr'), points)))]

    def play_bet(self, view, me, private, data):
        if me.get('done'):
            return None
        koala = private.get('koala')
        others = [p['id'] for p in view['players']]
        if koala and koala['state'] == 'pending':
            return [('koala_open', {})]
        if koala and koala['state'] == 'open':
            unbought = [i for i in R.KOALA_ITEMS if i['id'] not in koala['bought']
                        and koala['prices'][i['id']] <= private['cash']]
            if unbought and self.rng.random() < 0.6:
                item = self.rng.choice(unbought)
                return [('koala_buy', {'item': item['id'], 'target': self.rng.choice(others)})]
            return [('koala_exit', {})]
        if not private.get('loan_taken') and self.rng.random() < 0.15:
            return [('borrow', {})]   # always LOAN_AMOUNT, once per event
        bets, left = {}, private['cash']
        for pid in others:
            if self.rng.random() < 0.5:
                # Bets go in any whole amount (the slip's 1 / 10 / 100 step buttons)
                bets[pid] = self.rng.randint(0, max(0, left // 2))
                left -= bets[pid]
        return [('confirm_bets', {'bets': bets})]

    def play_purse(self, view, me, private, data):
        if not me.get('done'):
            return [('purse_choice', {'choice': self.rng.choice(['steal', 'dont'])})]

    def play_auction(self, view, me, private, data):
        auction = data['auction']
        if auction['leader'] == me['id'] or self.rng.random() < 0.5:
            return None
        lowest = R.AUCTION_OPENING_BID if auction['leader'] is None else auction['high_bid'] + STEP
        bid = lowest + self.rng.choice([0, 1, 7, 100])
        if bid <= private['cash']:
            return [('bid', {'amount': bid})]

    def play_case(self, view, me, private, data):
        if not me.get('done') and 'case_value' not in private:
            return [('case_vote', {'vote': self.rng.choice(['case', 'cash'])})]

    def play_scalp(self, view, me, private, data):
        if not me.get('done'):
            face = data['scalp']['face']
            return [('scalp_ask', {'price': self.rng.randrange(STEP, face + 1, STEP)})]


def invariant(game):
    for p in game.players.values():
        private = p.private
        if 'cash' in private:
            assert private['cash'] >= 0, f"{p.name} has negative cash {private['cash']}"
            assert private['borrowed'] >= 0
        if 'stats' in private:
            assert sum(private['stats'].values()) <= R.SKILL_POINTS, f'{p.name} has too many points'
        for pid, amount in private.get('bets', {}).items():
            assert pid in game.players and isinstance(amount, int) and amount > 0, f'bad bet {amount}'
    # Hidden information must never reach the public state
    for key in ('cash', 'stats', 'bets', 'borrowed', 'koala', 'case_value'):
        for p in game.players.values():
            assert key not in p.public, f'{key} leaked into {p.name}.public'
    if game.phase != game.end_phase:
        assert 'final' not in game.public, 'final standings shown before the season ended'


if __name__ == '__main__':
    seeds = 1 if '--quick' in sys.argv else 3
    scenarios = standard_scenarios(DerbyBot, players=4, ghost_phases=[
        'bet', 'payout', 'purse', 'auction', 'case', 'scalp'])
    ok = run_matrix(Derby, scenarios, seeds=seeds, invariant=invariant)
    sys.exit(0 if ok else 1)
