"""
Unit tests for rules.py: scoring, ties, odds, Shady Koala order of operations and the
special-event payouts.   python -m unittest discover tests
"""
import os
import random
import sys
import unittest
from collections import Counter
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
            'fist_fight': -1,     # 2*1.5 - 5 - 3 + 4 = -1
            'sand_curling': 13,   # 2*1.5 + 5*1.2 + 4 = 13
            'mini_golf': 100 + 2 - 5 * 2 - 3 * 4 - 4,
            'mascot_race': 5 * 3 + 2 + 4,
            'sumo': 13,           # 2*2 + 3*1.5 + 4 = 12.5 -> 13
            'half_court': 4,   # (2*3*5 + 3 + 4) / 10 = 3.7 -> 4
            'note': (2 + 4) * 2 + 5 + 4 + 3 * 4,
        }
        for event_id, value in expected.items():
            self.assertEqual(R.EVENTS[event_id]['score'](s, luck), value, event_id)

    def test_half_court_rounds_halves_up(self):
        self.assertEqual(R.EVENTS['half_court']['score'](stats(mcr=4), 1), 1)   # 5/10 -> 1
        self.assertEqual(R.EVENTS['half_court']['score'](stats(mcr=3), 1), 0)   # 4/10 -> 0

    def test_fractional_formulas_round_halves_up(self):
        self.assertEqual(R.EVENTS['fist_fight']['score'](stats(str_=1), 1), 3)     # 2.5 -> 3
        self.assertEqual(R.EVENTS['fist_fight']['score'](stats(str_=1, spd=5), 1), -2)   # -2.5 -> -2
        self.assertEqual(R.EVENTS['sand_curling']['score'](stats(spd=1), 1), 2)   # 2.2 -> 2
        self.assertEqual(R.EVENTS['sumo']['score'](stats(mcr=1), 1), 3)           # 2.5 -> 3

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
        self.assertEqual(odds['slow'], R.ODDS_CEILING)    # never won: capped long odds, not 99-1

    def test_even_match_is_close_to_evens(self):
        field = {'a': stats(spd=5), 'b': stats(spd=5)}
        odds = R.odds_calc(field, 'foot_race', random.Random(2), sims=2000)
        for frac in odds.values():
            self.assertTrue(Fraction(2, 3) <= frac <= Fraction(3, 2), frac)

    def test_odds_never_longer_than_the_ceiling(self):
        field = {'fast': stats(spd=10)}
        field.update({f'slow{i}': stats() for i in range(7)})
        odds = R.odds_calc(field, 'foot_race', random.Random(4))
        self.assertEqual(R.ODDS_CEILING, Fraction(50, 1))
        self.assertTrue(all(R.ODDS_FLOOR <= f <= R.ODDS_CEILING for f in odds.values()), odds)

    def test_payout_returns_stake_plus_winnings_less_the_winners_cut(self):
        self.assertEqual(R.payout(20, Fraction(5, 2)), 20 + 50 - 5)
        self.assertEqual(R.winner_cut(20, Fraction(5, 2)), 5)
        self.assertEqual(R.payout(10, Fraction(1, 10)), 11)   # $Dd 1 of winnings: no cut
        self.assertEqual(R.payout(10, Fraction(1, 3)), 13)    # rounds down
        self.assertEqual(R.payout(100, Fraction(50, 1)), 100 + 5000 - 500)
        self.assertEqual(R.winner_cut(7, Fraction(3, 1)), 2)   # 10% of 21, rounded down

    def test_labels(self):
        self.assertEqual(R.odds_label(Fraction(5, 2)), '5-2')


class KoalaTests(unittest.TestCase):
    base = {'a': stats(spd=5, str_=1), 'b': stats(spd=5, str_=1), 'c': stats(spd=5, str_=1)}

    @staticmethod
    def outcome(item, outcome_id):
        return next(o for o in R.KOALA_OUTCOMES[item] if o['id'] == outcome_id)

    def test_accidents_and_juice_have_three_outcomes_at_equal_odds(self):
        self.assertEqual([o['change'] for o in R.KOALA_OUTCOMES['accident']], [-2, -4, -6])
        self.assertEqual([o['change'] for o in R.KOALA_OUTCOMES['juice']], [2, 4, 6])
        seen = Counter()
        rng = random.Random(5)
        for _ in range(900):
            for _, item, outcome in R.roll_koala([('a', 'accident', 'b'), ('a', 'juice', 'c')], rng):
                seen[outcome['id']] += 1
        self.assertEqual(set(seen), {'fall', 'car', 'kneecaps', 'joe', 'hgh', 'venom'})
        self.assertTrue(all(250 < n < 350 for n in seen.values()), seen)

    def test_roll_keeps_each_target_and_item(self):
        rolled = R.roll_koala([('a', 'accident', 'b'), ('c', 'juice', 'a')], random.Random(1))
        self.assertEqual(sorted((t, i) for t, i, _ in rolled), [('a', 'juice'), ('b', 'accident')])

    def test_outcomes_change_speed_and_strength(self):
        rolled = [('b', 'accident', self.outcome('accident', 'fall')),
                  ('a', 'juice', self.outcome('juice', 'venom'))]
        eff = R.effective_stats(self.base, rolled)
        self.assertEqual((eff['b']['spd'], eff['b']['str']), (3, 0))   # STR 1 - 2 stops at 0
        self.assertEqual((eff['a']['spd'], eff['a']['str']), (11, 7))
        self.assertEqual(eff['a']['mcr'], self.base['a']['mcr'])
        self.assertEqual(self.base['a']['spd'], 5, 'base stats must not change')

    def test_outcomes_on_one_player_stack_before_the_floor(self):
        # -6 then +4: summed first (5 - 6 + 4 = 3), so the order they're applied never matters
        rolled = [('c', 'accident', self.outcome('accident', 'kneecaps')),
                  ('c', 'juice', self.outcome('juice', 'hgh'))]
        self.assertEqual(R.effective_stats(self.base, rolled)['c']['spd'], 3)
        self.assertEqual(R.effective_stats(self.base, rolled[::-1])['c']['spd'], 3)
        two_cars = [('c', 'accident', self.outcome('accident', 'car'))] * 2
        self.assertEqual(R.effective_stats(self.base, two_cars)['c']['spd'], 0)

    def test_headlines_split_by_item_and_say_again_for_a_repeat(self):
        names = {'a': 'Shazza', 'b': 'Davo'}
        history = Counter()
        car, joe = self.outcome('accident', 'car'), self.outcome('juice', 'joe')
        lines = R.koala_headlines([('a', 'accident', car), ('a', 'juice', joe), ('a', 'accident', car),
                                   ('b', 'accident', car)], names, history)
        self.assertEqual([line['text'] for line in lines['accident']],
                         ['Shazza got hit by a car!', 'Shazza got hit by a car! [again]', 'Davo got hit by a car!'])
        self.assertEqual(lines['juice'], [{'id': 'a', 'headline': 'Cup of Joe', 'change': 2,
                                           'text': 'Shazza is looking peppy.'}])
        # ...and in a later event of the same season
        later = R.koala_headlines([('b', 'accident', car)], names, history)
        self.assertEqual(later['accident'][0]['text'], 'Davo got hit by a car! [again]')
        fall = self.outcome('accident', 'fall')
        self.assertEqual(R.koala_headlines([('b', 'accident', fall)], names, history)['accident'][0]['text'],
                         'Davo took an unfortunate tumble . . .')

    def test_bribe_protects_target_from_everyone(self):
        res = R.resolve_koala({'a': {'accident': 'c'}, 'c': {'bribe': 'c'}, 'b': {'juice': 'c'}},
                              frisked=set())
        self.assertEqual(res['applied'], [])
        self.assertEqual(len(res['blocked']), 2)
        rolled = R.roll_koala(res['applied'], random.Random(2))
        self.assertEqual(R.effective_stats(self.base, rolled)['c'], self.base['c'])

    def test_frisk_negates_all_purchases_including_bribes(self):
        purchases = {'a': {'accident': 'b'}, 'b': {'bribe': 'b', 'juice': 'b'}}
        res = R.resolve_koala(purchases, frisked={'b'})
        self.assertEqual(res['caught'], {'b': {'bribe': 'b', 'juice': 'b'}})
        self.assertEqual(res['applied'], [('a', 'accident', 'b')])   # b's bribe was confiscated

    def test_prices_are_a_percent_of_the_buyers_cash(self):
        self.assertEqual(R.koala_prices(100), {'accident': 15, 'juice': 10, 'bribe': 5})
        self.assertEqual(R.koala_prices(1999), {'accident': 299, 'juice': 199, 'bribe': 99})
        self.assertEqual(R.koala_prices(0), {'accident': 1, 'juice': 1, 'bribe': 1})   # never free

    def test_visits_go_to_whoever_is_behind(self):
        cash = {'first': 500, 'mid1': 200, 'mid2': 200, 'last': 10}
        seen = Counter()
        for seed in range(400):
            seen.update(R.koala_visitors(cash, random.Random(seed)))
        self.assertEqual(seen['first'], 0)
        self.assertEqual(seen['last'], 400)
        for mid in ('mid1', 'mid2'):
            self.assertTrue(150 < seen[mid] < 250, seen)   # about half the time

    def test_koala_ties_share_the_place(self):
        rng = random.Random(1)
        for _ in range(50):
            visitors = R.koala_visitors({'a': 300, 'b': 300, 'c': 20, 'd': 20}, rng)
            self.assertEqual(visitors, {'c', 'd'})
        level = Counter()
        for _ in range(400):
            level.update(R.koala_visitors({'a': 100, 'b': 100}, rng))   # first event: all flip
        self.assertTrue(all(150 < level[p] < 250 for p in 'ab'), level)

    def test_frisking_a_clean_player_catches_nothing(self):
        res = R.resolve_koala({'a': {'juice': 'a'}}, frisked={'b'})
        self.assertEqual(res['caught'], {})
        self.assertEqual(res['applied'], [('a', 'juice', 'a')])


class SpecialEventTests(unittest.TestCase):
    def test_purse(self):
        cash = {'a': 1000, 'b': 4001, 'c': 0}
        self.assertEqual(R.purse_payouts({'a': 'dont', 'b': 'dont'}, cash), {'a': 200, 'b': 200})
        self.assertEqual(R.purse_payouts({'a': 'steal', 'b': 'dont'}, cash), {'a': 1000, 'b': 0})
        # More than one thief: EVERYONE loses 25% of their cash, rounded down
        self.assertEqual(R.purse_payouts({'a': 'steal', 'b': 'steal', 'c': 'dont'}, cash),
                         {'a': -250, 'b': -1000, 'c': 0})

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
            self.assertTrue(150 <= face <= 1500 and face % R.MONEY_STEP == 0, face)

    def test_case_holder_is_highest_mcr(self):
        field = {'a': stats(mcr=2), 'b': stats(mcr=7), 'c': stats(mcr=7)}
        holders = {R.case_holder(field, random.Random(i)) for i in range(30)}
        self.assertEqual(holders, {'b', 'c'})

    def test_case_payouts(self):
        # CASE: the voters split what's inside (rounded down), the holder gets $Dd 250
        self.assertEqual(R.case_payouts('h', ['a', 'b', 'c'], 7001, 'case'),
                         {'a': 2333, 'b': 2333, 'c': 2333, 'h': 250})
        # CASH: every voter gets $Dd 250, the holder gets the case
        self.assertEqual(R.case_payouts('h', ['a', 'b', 'c'], 7001, 'cash'),
                         {'a': 250, 'b': 250, 'c': 250, 'h': 7001})
        self.assertEqual(R.CASE_VALUE, (500, 10000))

    def test_case_majority_and_coin_flip(self):
        rng = random.Random(0)
        self.assertEqual(R.case_decision({'a': 'case', 'b': 'case', 'c': 'cash'}, rng), ('case', False))
        decision, flipped = R.case_decision({'a': 'case', 'b': 'cash'}, rng)
        self.assertTrue(flipped)
        self.assertIn(decision, ('case', 'cash'))

    def test_card_pack(self):
        cards = R.open_card_pack(random.Random(5))
        self.assertEqual(len(cards), 6)
        self.assertTrue(all(10 <= c['value'] <= 100 for c in cards[:5]))
        self.assertEqual(cards[5]['name'], R.HOLO_CARD_NAME)
        self.assertTrue(50 <= cards[5]['value'] <= 2000)
        self.assertEqual(R.CARD_PACK_VALUE, (100, 2500))   # shown while bidding
        rng = random.Random(6)
        for _ in range(200):
            total = sum(c['value'] for c in R.open_card_pack(rng))
            self.assertTrue(100 <= total <= 2500, total)


class DataTests(unittest.TestCase):
    def test_heads(self):
        self.assertTrue(R.valid_head(R.BLANK_HEAD))
        self.assertTrue(R.valid_head('0' * R.HEAD_GRID ** 2))
        self.assertFalse(R.valid_head('z' * R.HEAD_GRID ** 2))
        self.assertFalse(R.valid_head('0' * (R.HEAD_GRID ** 2 - 1)))
        self.assertFalse(R.valid_head(None))

    def test_unshuffled_season_is_the_design_doc_route(self):
        season = R.build_season()
        self.assertEqual(len(season), 13)
        self.assertEqual([s['zone'] for s in season], [1] * 4 + [2] * 5 + [3] * 4)
        self.assertEqual([s['event'] for s in season], [
            'foot_race', 'mothers_purse', 'speed_hike', 'fist_fight', 'card_auction', 'sand_curling',
            'mini_golf', 'case_or_no_case', 'mascot_race', 'sumo', 'ticket_scalping', 'half_court', 'note'])

    def test_shuffled_seasons_keep_the_shape(self):
        orders = set()
        for seed in range(20):
            season = R.build_season(random.Random(seed))
            self.assertEqual([(s['kind'], s['zone']) for s in season], R.SEASON_SHAPE)
            events = [s['event'] for s in season]
            self.assertEqual(len(events), len(set(events)), 'an event came up twice')
            for stop in season:
                table = R.EVENTS if stop['kind'] == 'gamble' else R.SPECIALS
                self.assertIn(stop['event'], table)
                if stop['kind'] == 'gamble':
                    self.assertIn('venue', stop)
            for entry in R.season_map(season):
                self.assertIn('lat', entry)
            orders.add(tuple(events))
        self.assertGreater(len(orders), 15, 'seasons should differ from game to game')

    def test_a_bigger_pool_leaves_some_events_out(self):
        extra = dict(R.GAMBLE_STOPS[0], event='foot_race_2')
        pool = R.GAMBLE_STOPS + [extra]
        original = R.GAMBLE_STOPS
        try:
            R.GAMBLE_STOPS = pool
            season = R.build_season(random.Random(1))
        finally:
            R.GAMBLE_STOPS = original
        gambles = [s for s in season if s['kind'] == 'gamble']
        self.assertEqual(len(gambles), 9)


if __name__ == '__main__':
    unittest.main()
