"""
Unit tests for rules.py: scoring, ties, odds, Shady Koala order of operations and the
special-event payouts.   python -m unittest discover tests
"""
import os
import random
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import rules as R  # noqa: E402


def stats(str_=0, spd=0, mcr=0):
    return {'str': str_, 'spd': spd, 'mcr': mcr}


class FixedLuck(random.Random):
    """randint always returns `value` (LUCK becomes a constant)."""
    def __init__(self, value):
        super().__init__(0)
        self.value = value

    def randint(self, a, b):
        return self.value


class ScoringTests(unittest.TestCase):
    def test_design_doc_formulas(self):
        s = stats(str_=2, spd=5, mcr=3)
        luck = 4
        expected = {
            'foot_race': 5 * 10 - 2 + 4,
            'speed_hike': (5 + 2) + 4 * 2,
            'fist_fight': 2 * 10 - 5 - 3 + 4,
            'sand_curling': 2 * 3 + 5 * 2 + 4,
            'mini_golf': 100 + 2 - 5 * 2 - 3 * 4 - 4,
            'mascot_race': 5 * 3 + 2 + 4,
            'sumo': 2 * 10 + 3 * 2 + 4,
            'half_court': 4,   # (2*3*5 + 3 + 4) / 10 = 3.7 -> 4
            'note': (2 + 4) * 2 + 5 + 4 + 3 * 4,
        }
        for event_id, value in expected.items():
            self.assertEqual(R.EVENTS[event_id]['score'](s, luck), value, event_id)

    def test_half_court_rounds_halves_up(self):
        self.assertEqual(R.EVENTS['half_court']['score'](stats(mcr=4), 1), 1)   # 5/10 -> 1
        self.assertEqual(R.EVENTS['half_court']['score'](stats(mcr=3), 1), 0)   # 4/10 -> 0

    def test_lowest_score_wins_mini_golf(self):
        field = {'good': stats(spd=5, mcr=5), 'bad': stats(str_=10)}
        order, _, _ = R.rank(field, 'mini_golf', FixedLuck(5))
        self.assertEqual(order, ['good', 'bad'])

    def test_fastest_wins_foot_race(self):
        field = {'slow': stats(spd=1), 'fast': stats(spd=9), 'mid': stats(spd=5)}
        order, scores, tied = R.rank(field, 'foot_race', FixedLuck(5))
        self.assertEqual(order, ['fast', 'mid', 'slow'])
        self.assertEqual(scores['fast'], 95)
        self.assertEqual(tied, set())


class TieBreakTests(unittest.TestCase):
    def test_tied_players_stay_in_their_block(self):
        # a and b tie for 1st on the first roll; c is far behind and must stay last
        rolls = iter([5, 5, 1, 2, 9])   # first scores a,b,c; then re-roll a,b only

        class Scripted(random.Random):
            def randint(self, lo, hi):
                return next(rolls)
        field = {'a': stats(spd=5), 'b': stats(spd=5), 'c': stats(spd=1)}
        order, scores, tied = R.rank(field, 'foot_race', Scripted())
        self.assertEqual(order, ['b', 'a', 'c'])
        self.assertEqual(scores, {'a': 55, 'b': 55, 'c': 11})   # displayed scores are the first
        self.assertEqual(tied, {'a', 'b'})

    def test_endless_tie_is_settled(self):
        field = {'a': stats(), 'b': stats()}
        order, _, tied = R.rank(field, 'foot_race', FixedLuck(3))
        self.assertEqual(sorted(order), ['a', 'b'])
        self.assertEqual(tied, {'a', 'b'})


class OddsTests(unittest.TestCase):
    def test_favourite_gets_shorter_odds(self):
        field = {'fast': stats(spd=8), 'slow': stats(spd=2, str_=8)}
        odds = R.odds_calc(field, 'foot_race', random.Random(1))
        self.assertLess(odds['fast'], odds['slow'])
        self.assertEqual(odds['fast'], R.ODDS_FLOOR)       # always wins: 1-10
        self.assertEqual(odds['slow'], Fraction(99, 1))   # never won: long odds, not infinite

    def test_even_match_is_close_to_evens(self):
        field = {'a': stats(spd=5), 'b': stats(spd=5)}
        odds = R.odds_calc(field, 'foot_race', random.Random(2), sims=2000)
        for frac in odds.values():
            self.assertTrue(Fraction(2, 3) <= frac <= Fraction(3, 2), frac)

    def test_payout_returns_stake_plus_winnings(self):
        self.assertEqual(R.payout(20, Fraction(5, 2)), 70)
        self.assertEqual(R.payout(10, Fraction(1, 10)), 11)
        self.assertEqual(R.payout(10, Fraction(1, 3)), 13)   # rounds down

    def test_labels(self):
        self.assertEqual(R.odds_label(Fraction(5, 2)), '5-2')


class KoalaTests(unittest.TestCase):
    base = {'a': stats(spd=5, str_=1), 'b': stats(spd=5, str_=1), 'c': stats(spd=5, str_=1)}

    def test_kneecaps_and_hgh(self):
        res = R.resolve_koala({'a': {'kneecaps': 'b', 'hgh': 'a'}}, frisked=set())
        eff = R.effective_stats(self.base, res['applied'])
        self.assertEqual(eff['b']['spd'], 0)
        self.assertEqual((eff['a']['spd'], eff['a']['str']), (10, 6))
        self.assertEqual(self.base['a']['spd'], 5, 'base stats must not change')

    def test_kneecaps_beat_hgh_on_the_same_player(self):
        res = R.resolve_koala({'a': {'kneecaps': 'c'}, 'b': {'hgh': 'c'}}, frisked=set())
        eff = R.effective_stats(self.base, res['applied'])
        self.assertEqual((eff['c']['spd'], eff['c']['str']), (0, 6))

    def test_bribe_protects_target_from_everyone(self):
        res = R.resolve_koala({'a': {'kneecaps': 'c'}, 'c': {'bribe': 'c'}, 'b': {'hgh': 'c'}},
                              frisked=set())
        self.assertEqual(res['applied'], [])
        self.assertEqual(len(res['blocked']), 2)
        self.assertEqual(R.effective_stats(self.base, res['applied'])['c'], self.base['c'])

    def test_frisk_negates_all_purchases_including_bribes(self):
        purchases = {'a': {'kneecaps': 'b'}, 'b': {'bribe': 'b', 'hgh': 'b'}}
        res = R.resolve_koala(purchases, frisked={'b'})
        self.assertEqual(res['caught'], {'b': {'bribe': 'b', 'hgh': 'b'}})
        self.assertEqual(res['applied'], [('a', 'kneecaps', 'b')])   # b's bribe was confiscated

    def test_frisking_a_clean_player_catches_nothing(self):
        res = R.resolve_koala({'a': {'hgh': 'a'}}, frisked={'b'})
        self.assertEqual(res['caught'], {})
        self.assertEqual(res['applied'], [('a', 'hgh', 'a')])


class SpecialEventTests(unittest.TestCase):
    def test_purse(self):
        self.assertEqual(R.purse_payouts({'a': 'dont', 'b': 'dont'}), {'a': 20, 'b': 20})
        self.assertEqual(R.purse_payouts({'a': 'steal', 'b': 'dont'}), {'a': 100, 'b': 0})
        self.assertEqual(R.purse_payouts({'a': 'steal', 'b': 'steal', 'c': 'dont'}),
                         {'a': 0, 'b': 0, 'c': 0})

    def test_moral_courage_must_be_above_two(self):
        self.assertFalse(R.can_choose_morally(stats(mcr=2)))
        self.assertTrue(R.can_choose_morally(stats(mcr=3)))

    def test_scalp_lowest_unique_ask_wins(self):
        self.assertEqual(R.scalp_winner({'a': 50, 'b': 60, 'c': 70}), 'a')
        self.assertEqual(R.scalp_winner({'a': 50, 'b': 50, 'c': 70}), 'c')
        self.assertIsNone(R.scalp_winner({'a': 50, 'b': 50, 'c': 70, 'd': 70}))
        self.assertIsNone(R.scalp_winner({'a': 50, 'b': 50}))
        self.assertIsNone(R.scalp_winner({}))

    def test_scalp_face_value_is_on_the_money_grid(self):
        rng = random.Random(3)
        for _ in range(200):
            face = R.scalp_face_value(rng)
            self.assertTrue(10 <= face <= 250 and face % R.MONEY_STEP == 0)

    def test_case_holder_is_highest_mcr(self):
        field = {'a': stats(mcr=2), 'b': stats(mcr=7), 'c': stats(mcr=7)}
        holders = {R.case_holder(field, random.Random(i)) for i in range(30)}
        self.assertEqual(holders, {'b', 'c'})

    def test_case_payouts(self):
        self.assertEqual(R.case_payouts('h', ['a', 'b'], 250, 'case'), {'a': 125, 'b': 125, 'h': 100})
        self.assertEqual(R.case_payouts('h', ['a', 'b', 'c'], 250, 'cash'),
                         {'a': 33, 'b': 33, 'c': 33, 'h': 250})

    def test_case_majority_and_coin_flip(self):
        rng = random.Random(0)
        self.assertEqual(R.case_decision({'a': 'case', 'b': 'case', 'c': 'cash'}, rng), ('case', False))
        decision, flipped = R.case_decision({'a': 'case', 'b': 'cash'}, rng)
        self.assertTrue(flipped)
        self.assertIn(decision, ('case', 'cash'))

    def test_card_pack(self):
        cards = R.open_card_pack(random.Random(5))
        self.assertEqual(len(cards), 6)
        self.assertTrue(all(1 <= c['value'] <= 10 for c in cards[:5]))
        self.assertEqual(cards[5]['name'], R.HOLO_CARD_NAME)
        self.assertTrue(10 <= cards[5]['value'] <= 200)


class DataTests(unittest.TestCase):
    def test_heads(self):
        self.assertTrue(R.valid_head(R.BLANK_HEAD))
        self.assertTrue(R.valid_head('0' * R.HEAD_GRID ** 2))
        self.assertFalse(R.valid_head('z' * R.HEAD_GRID ** 2))
        self.assertFalse(R.valid_head('0' * (R.HEAD_GRID ** 2 - 1)))
        self.assertFalse(R.valid_head(None))

    def test_season_matches_design_doc(self):
        self.assertEqual(len(R.SEASON), 13)
        self.assertEqual([s['zone'] for s in R.SEASON], [1] * 4 + [2] * 5 + [3] * 4)
        for stop in R.SEASON:
            table = R.EVENTS if stop['kind'] == 'gamble' else R.SPECIALS
            self.assertIn(stop['event'], table)
        for entry in R.season_map(R.SEASON):
            self.assertIn('lat', entry)


if __name__ == '__main__':
    unittest.main()
