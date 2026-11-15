"""
Game-logic tests: drive Derby directly (no sockets) through specific situations.
    python -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from apge import Player, Reject  # noqa: E402

import rules as R  # noqa: E402
from game import Derby  # noqa: E402

HEAD = '0' * R.HEAD_GRID ** 2


class DerbyTestCase(unittest.TestCase):
    def setUp(self):
        self.game = Derby(seed=3)
        self.game.time_scale = 1000   # timers never fire during a test
        self.ann, self.bob, self.cat = (self.join(n) for n in ('Ann', 'Bob', 'Cat'))

    def join(self, name):
        p = Player(name, name + '-token')
        self.game.players[p.id] = p
        return p

    def act(self, player, name, **data):
        return self.game._dispatch(player, name, data)

    def create(self, player, str_=0, spd=0, mcr=0):
        self.act(player, 'submit_head', head=HEAD)
        self.act(player, 'submit_stats', str=str_, spd=spd, mcr=mcr)

    def start_at_betting(self, builds=((0, 9, 1), (5, 0, 5), (2, 2, 6))):
        for p, b in zip((self.ann, self.bob, self.cat), builds):
            self.create(p, *b)
        self.game._start()
        self.assertEqual(self.game.phase, 'map')
        self.game._expire_phase()
        self.assertEqual(self.game.phase, 'bet')
        for p in self.game.players.values():   # keep the Shady Koala out of the way
            p.private.pop('koala', None)


class LobbyTests(DerbyTestCase):
    def test_first_to_finish_is_vip(self):
        self.create(self.bob, spd=3)
        self.create(self.ann)
        self.assertEqual(self.game.vip(), self.bob)
        self.assertFalse(self.game.lobby_ready())
        self.create(self.cat)
        self.assertTrue(self.game.lobby_ready())

    def test_skill_points_are_validated(self):
        self.act(self.ann, 'submit_head', head=HEAD)
        for bad in ({'str': 11, 'spd': 0, 'mcr': 0}, {'str': 4, 'spd': 4, 'mcr': 3},
                    {'str': True, 'spd': 0, 'mcr': 0}, {'str': -1, 'spd': 0, 'mcr': 0},
                    {'str': '5', 'spd': 0, 'mcr': 0}):
            with self.assertRaises(Reject):
                self.act(self.ann, 'submit_stats', **bad)
        self.assertNotIn('stats', self.ann.private)

    def test_must_draw_before_stats(self):
        with self.assertRaises(Reject):
            self.act(self.ann, 'submit_stats', str=1, spd=1, mcr=1)

    def test_starting_early_gives_stragglers_a_blank_character(self):
        self.create(self.ann, spd=5)
        self.game._start()
        self.assertEqual(self.bob.private['stats'], {'str': 0, 'spd': 0, 'mcr': 0})
        self.assertEqual(self.bob.public['head'], R.BLANK_HEAD)
        self.assertEqual(self.bob.private['cash'], R.STARTING_CASH)


class BettingTests(DerbyTestCase):
    def test_bets_are_validated(self):
        self.start_at_betting()
        for bad in ({'bets': {self.bob.id: 110}}, {'bets': {self.bob.id: 15}},
                    {'bets': {self.bob.id: 60, self.cat.id: 60}}, {'bets': {'nobody': 10}},
                    {'bets': {self.bob.id: True}}, {'bets': [10]}, {}):
            with self.assertRaises(Reject):
                self.act(self.ann, 'confirm_bets', **bad)
        self.assertEqual(self.ann.private['cash'], R.STARTING_CASH)
        self.assertFalse(self.ann.public['done'])

    def test_last_holdout_disconnecting_ends_betting(self):
        self.start_at_betting()
        self.act(self.ann, 'confirm_bets', bets={})
        self.act(self.bob, 'confirm_bets', bets={})
        self.assertEqual(self.game.phase, 'bet')
        self.cat.connected = False
        self.game.on_player_disconnected(self.cat)
        self.assertIn(self.game.phase, ('frisk', 'perform'))

    def test_winning_bet_pays_the_offered_odds(self):
        self.start_at_betting()
        self.game.odds = {pid: R.Fraction(5, 2) for pid in self.game.players}
        for p in (self.ann, self.bob, self.cat):
            self.act(p, 'confirm_bets', bets={self.ann.id: 20, self.bob.id: 10} if p is self.cat else {})
        self.game.outcome['order'] = [self.ann.id, self.bob.id, self.cat.id]
        self.game.goto('payout')
        self.assertEqual(self.cat.private['cash'], 100 - 30 + 20 + 50)
        self.assertEqual(self.cat.private['bets_won'], 1)
        self.assertEqual(self.cat.private['money_lost'], 10)
        self.assertEqual(self.cat.private['last'], 40)
        self.assertEqual(self.game.public['payout']['winning_bets'][0]['payout'], 70)

    def test_koala_purchase_targets_must_be_players(self):
        self.start_at_betting()
        self.ann.private['koala'] = {'state': 'pending', 'bought': {}}
        with self.assertRaises(Reject):
            self.act(self.ann, 'confirm_bets', bets={})   # must answer the Psst first
        self.act(self.ann, 'koala_open')
        with self.assertRaises(Reject):
            self.act(self.ann, 'koala_buy', item='hgh', target=[self.bob.id])
        self.act(self.ann, 'koala_buy', item='kneecaps', target=self.bob.id)
        self.assertEqual(self.ann.private['cash'], 50)
        with self.assertRaises(Reject):
            self.act(self.ann, 'koala_buy', item='kneecaps', target=self.cat.id)
        self.assertEqual(self.game.koala_purchases, {self.ann.id: {'kneecaps': self.bob.id}})

    def test_loans_only_below_starting_cash(self):
        self.start_at_betting()
        with self.assertRaises(Reject):
            self.act(self.ann, 'borrow', amount=50)
        self.ann.private['cash'] = 30
        self.act(self.ann, 'borrow', amount=100)
        self.assertEqual((self.ann.private['cash'], self.ann.private['borrowed']), (130, 100))
        with self.assertRaises(Reject):
            self.act(self.ann, 'borrow', amount=10)


class PrivacyAndResetTests(DerbyTestCase):
    def test_views_only_carry_your_own_secrets(self):
        self.start_at_betting()
        view = self.game.player_view(self.ann)
        self.assertEqual(view['me']['private']['stats'], self.ann.private['stats'])
        flat = repr(view['players']) + repr(view['data'])
        for secret in ('cash', 'stats', 'borrowed'):
            self.assertNotIn(f"'{secret}'", flat)
        self.assertNotIn("'private'", repr(self.game.host_view()))

    def test_one_more_game_keeps_heads_and_clears_stats(self):
        self.start_at_betting()
        self.game._reset()
        self.assertEqual(self.ann.public, {'head': HEAD})
        self.assertEqual(self.ann.private, {})
        self.assertIsNone(self.game.vip())


class SpecialsTests(DerbyTestCase):
    def go(self, phase):
        for p, b in zip((self.ann, self.bob, self.cat), ((0, 5, 5), (5, 5, 0), (1, 1, 3))):
            self.create(p, *b)
        self.game._start()
        self.game.goto(phase)

    def test_low_moral_courage_is_forced_to_steal(self):
        self.go('purse')
        self.assertEqual(self.bob.private['choice'], 'steal')
        self.assertTrue(self.bob.public['done'])
        self.assertNotIn('choice', self.ann.private)
        self.act(self.ann, 'purse_choice', choice='dont')
        self.act(self.cat, 'purse_choice', choice='dont')
        self.assertEqual(self.game.phase, 'purse_result')
        self.assertEqual(self.bob.private['cash'], R.STARTING_CASH + R.PURSE_LONE_THIEF)

    def test_auction_winner_pays_and_collects(self):
        self.go('auction')
        self.act(self.ann, 'bid', amount=10)
        with self.assertRaises(Reject):
            self.act(self.ann, 'bid', amount=20)    # already winning
        with self.assertRaises(Reject):
            self.act(self.bob, 'bid', amount=10)    # must beat the high bid
        self.act(self.bob, 'bid', amount=30)
        self.game.goto('auction_open')
        total = self.game.public['auction']['total']
        self.game.goto('auction_result')
        self.assertEqual(self.bob.private['cash'], R.STARTING_CASH - 30 + total)
        self.assertEqual(self.ann.private['cash'], R.STARTING_CASH)

    def test_case_value_stays_secret_if_they_take_the_cash(self):
        self.go('case')
        holder = self.game.players[self.game.case_secret['holder']]
        self.assertEqual(holder, self.ann)   # highest MCR
        self.assertNotIn('value', self.game.public['case'])
        self.act(self.bob, 'case_vote', vote='cash')
        self.act(self.cat, 'case_vote', vote='cash')
        self.assertEqual(self.game.phase, 'case_result')
        self.assertIsNone(self.game.public['case']['value'])
        self.assertEqual(self.bob.private['cash'], R.STARTING_CASH + R.CASE_CASH // 2)

    def test_scalping_runs_four_rounds(self):
        self.go('scalp')
        for round_no in range(1, R.SCALP_ROUNDS + 1):
            self.assertEqual(self.game.public['scalp']['round'], round_no)
            self.game._expire_phase()             # timer: nobody priced
            self.assertEqual(self.game.phase, 'scalp_result')
            self.game._complete_ready()
        self.assertEqual(self.game.phase, 'map')


if __name__ == '__main__':
    unittest.main()
