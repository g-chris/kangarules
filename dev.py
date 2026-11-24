"""
Developer Mode for Derby '27 (python app.py --dev): every piece of art the game needs, and
a sample state for every screen, so art can be previewed where it's used and any screen
can be looked at without playing to it.

ART is the art list Developer Mode shows. Each Asset's `screens` are the SCREENS ids it
appears on (its live preview); tests/test_dev.py checks that the JS only asks for art that
is listed here and that every screen still builds.
"""
import random

from apge.art import Asset
from apge.dev import Screen

import rules as R

# ---- sample players ---------------------------------------------------------------------------

SAMPLE_STATS = [{'str': 5, 'spd': 3, 'mcr': 2}, {'str': 2, 'spd': 6, 'mcr': 2},
                {'str': 3, 'spd': 3, 'mcr': 4}, {'str': 0, 'spd': 5, 'mcr': 5}]
# (skin, hair) palette indices for the sample faces
SAMPLE_LOOKS = [(8, 7), (9, 0), (10, 6), (8, 3)]


def sample_head(i):
    """A simple face so sample screens look like a real game, different for each player."""
    skin, hair = (R.PIXEL_CHARS[k] for k in SAMPLE_LOOKS[i % len(SAMPLE_LOOKS)])
    n = R.HEAD_GRID
    rows = []
    for y in range(n):
        row = ''
        for x in range(n):
            dx, dy = x - 7.5, y - 8.5
            inside = dx * dx / 42 + dy * dy / 49 <= 1
            if not inside:
                row += '.'
            elif y <= 4 or (y <= 7 and abs(dx) > 5):
                row += hair
            elif y == 8 and abs(dx) in (2.5, 3.5):
                row += '0'    # eyes
            elif y == 12 and abs(dx) <= 2.5:
                row += '3'    # mouth
            else:
                row += skin
        rows.append(row)
    return ''.join(rows)


def cast(game):
    """Sample players who have drawn a head and spent their points, as if the lobby is done."""
    game.rng = random.Random(27)   # the same sample screen every time
    for i, p in enumerate(game.players.values()):
        p.public['head'] = sample_head(i)
        p.private['stats'] = dict(SAMPLE_STATS[i % len(SAMPLE_STATS)])
        p.public['character_done'] = True
        game.finish_order.append(p.id)


def players(game):
    return list(game.players.values())


# Sample screens use the design doc's route (no shuffle), so each event has a known stop and
# zone: the frisk sample needs Sumo in the Professional Stadium
ROUTE = R.build_season()
STOP = {stop['event']: i for i, stop in enumerate(ROUTE)}


def at_stop(game, event):
    """Start the season and arrive at the stop for `event` (its map screen)."""
    cast(game)
    game._start()
    game.season = list(ROUTE)
    game.public['season'] = R.season_map(game.season)
    game.public['stop'] = STOP[event] - 1
    game.next_stop()


def act(game, player, name, data):
    game._dispatch(player, name, data)   # the real action, with its phase and input checks


# ---- sample screens -----------------------------------------------------------------------------

def betting(event, then=None):
    def setup(game):
        at_stop(game, event)
        game.map_done()
        if then:
            then(game)
    return setup


def performing(event):
    def setup(game):
        betting(event)(game)
        game.finish_betting()
        if game.phase == 'frisk':
            game.frisk_done()
    return setup


def my_purchases(game):
    """The phone's player (the first) meets the Shady Koala and buys two things."""
    me, other = players(game)[:2]
    me.private['koala'] = {'state': 'open', 'bought': {}}
    act(game, me, 'koala_buy', {'item': 'kneecaps', 'target': other.id})
    act(game, me, 'koala_buy', {'item': 'bribe', 'target': me.id})
    act(game, me, 'koala_exit', {})


def my_bets(game):
    my_purchases(game)
    me, other = players(game)[:2]
    act(game, me, 'confirm_bets', {'bets': {me.id: 25, other.id: 10}})


def watching_my_bets(game):
    """The phone during the race: the bets and koala purchases the player made."""
    betting('foot_race')(game)
    my_bets(game)
    game.finish_betting()
    if game.phase == 'frisk':
        game.frisk_done()


def frisk(game):
    betting('sumo')(game)
    game.finish_betting()   # the Professional Stadium always frisks someone
    p = players(game)
    game.public['frisks'] = [{'id': p[1].id, 'name': p[1].name, 'caught': [
        {'item': R.KOALA_BY_ID['kneecaps']['name'], 'target': p[0].name}]}]


def payout(game):
    betting('foot_race')(game)
    for i, p in enumerate(players(game)):
        if p.private.get('koala'):
            act(game, p, 'koala_exit', {})   # a pending Psst! blocks the betting slip
        # A little on everyone, so the screen has winning bets to show
        act(game, p, 'confirm_bets', {'bets': {q.id: 10 * (1 + (i + j) % 3) for j, q in enumerate(players(game))}})
    if game.phase == 'frisk':
        game.frisk_done()
    game.perform_done()


def special(event, choices=None):
    def setup(game):
        at_stop(game, event)
        game.map_done()
        if choices:
            choices(game)
    return setup


def purse_choices(game):
    for p, pick in zip(players(game), ('steal', 'dont', 'dont', 'dont')):
        if not p.public['done']:
            act(game, p, 'purse_choice', {'choice': pick})


def auction_bid(game):
    act(game, players(game)[2], 'bid', {'amount': 40})


def auction_open(game):
    auction_bid(game)
    game.auction_timeout()


def auction_result(game):
    auction_open(game)
    game.auction_open_done()


def case_votes(game):
    for p, vote in zip(players(game), ('case', 'cash', 'case', 'case')):
        if not p.public['done']:
            act(game, p, 'case_vote', {'vote': vote})


def scalp_asks(game):
    for p, price in zip(players(game), (20, 30, 30, 50)):
        act(game, p, 'scalp_ask', {'price': price})


def game_over(game):
    cast(game)
    game._start()
    for p, (cash, borrowed) in zip(players(game), ((340, 100), (210, 0), (150, 40), (60, 0))):
        p.private.update(cash=cash, borrowed=borrowed, bets_won=len(p.name) % 4, money_lost=cash // 3)
    game.goto('game_over')


def final_beat(beat):
    """Seconds into the final results for a reveal beat (see renderFinal in host.js)."""
    return R.FINAL_REVEAL_SECONDS * beat + 0.5


def case_holder(game):
    return game.players[game.case_secret['holder']]


def case_voter(game):
    return next(p for p in players(game) if p.id != game.case_secret['holder'])


def koala_open(game):
    betting('foot_race')(game)
    me = players(game)[0]
    me.private['koala'] = {'state': 'open', 'bought': {}}


N = 4   # sample players per screen (Screen's default)
GAMBLES = R.GAMBLE_STOPS   # every gambling event that can turn up in a season

SCREENS = [
    Screen('lobby', 'Lobby', setup=cast, group='Lobby and map'),
    Screen('map', 'Map', setup=lambda g: at_stop(g, 'foot_race'), elapsed=1, group='Lobby and map'),
] + [
    Screen(f"bet-{stop['event']}", f"Betting · {stop['venue']}", setup=betting(stop['event']), elapsed=5,
           group='Betting') for stop in GAMBLES
] + [
    Screen('frisk', 'Random frisk', setup=frisk, group='Betting'),
    Screen('payout', 'Payout', setup=payout, group='Betting'),
] + [
    Screen(f"perform-{stop['event']}", R.EVENTS[stop['event']]['name'], setup=performing(stop['event']),
           elapsed=2.5, group='Events') for stop in GAMBLES
] + [
    Screen('purse', "Mother's Purse", setup=special('mothers_purse'), group='Specials'),
    Screen('purse-result', "Mother's Purse result", setup=special('mothers_purse', purse_choices), group='Specials'),
    Screen('auction', 'Card auction', setup=special('card_auction', auction_bid), elapsed=20, group='Specials'),
    Screen('auction-open', 'Opening the card pack', setup=special('card_auction', auction_open),
           elapsed=R.CARD_REVEAL_SECONDS - 2, group='Specials'),
    Screen('auction-result', 'Card auction result', setup=special('card_auction', auction_result), group='Specials'),
    Screen('case', 'Case or No Case', setup=special('case_or_no_case'), group='Specials'),
    Screen('case-result', 'Case or No Case result', setup=special('case_or_no_case', case_votes), group='Specials'),
    Screen('scalp', 'Ticket scalping', setup=special('ticket_scalping'), group='Specials'),
    Screen('scalp-result', 'Ticket scalping result', setup=special('ticket_scalping', scalp_asks), group='Specials'),
    Screen('final-standings', 'Final standings', setup=game_over, elapsed=final_beat(N), group='Final results'),
    Screen('final-loansharks', 'The loansharks collect', setup=game_over, elapsed=final_beat(N + 1), group='Final results'),
    Screen('final-winner', 'Winner and awards', setup=game_over, elapsed=final_beat(N + 2), group='Final results'),
] + [
    Screen(id, label, setup=setup, role='player', player=player, elapsed=elapsed, group='Phone')
    for id, label, setup, player, elapsed in [
        ('phone-stats', 'Spend skill points', lambda g: [p.public.update(head=sample_head(0)) for p in players(g)], None, 0),
        ('phone-bet', 'Betting slip (after the Shady Koala)', betting('foot_race', my_purchases), None, 0),
        ('phone-koala', 'Shady Koala', koala_open, None, 0),
        ('phone-bet-locked', 'Bets locked in', betting('foot_race', my_bets), None, 0),
        ('phone-watch', 'Watch the big screen (with my bets)', watching_my_bets, None, 0),
        ('phone-payout', 'Payout', payout, None, 0),
        ('phone-purse', "Mother's Purse", special('mothers_purse'), None, 0),
        ('phone-auction', 'Card auction', special('card_auction', auction_bid), None, 0),
        ('phone-case-holder', 'Case or No Case: holding the case', special('case_or_no_case'), case_holder, 0),
        ('phone-case-vote', 'Case or No Case: voting', special('case_or_no_case'), case_voter, 0),
        ('phone-scalp', 'Ticket scalping', special('ticket_scalping'), None, 0),
        ('phone-final-wait', 'Final results: waiting for the reveal', game_over, None, 0),
        ('phone-final', 'Final results', game_over, None, final_beat(N + 2)),
    ]
]

# ---- the art --------------------------------------------------------------------------------------

ART = [
    Asset('title', "Title logo: Down Under Gambler's Sweat It Out! Derby '27", 'Title and phone', (128, 48),
          screens=['lobby'], notes='Lobby, above the QR code'),
    Asset('big_screen', '"Watch the big screen" icon', 'Title and phone', (24, 16), screens=['phone-watch'],
          notes='Phones, whenever the action is on the TV'),

    Asset('agent_kevin', 'Agent Kevin L. Peterson, Kangarules Gambling Commission', 'Characters', (32, 48),
          screens=['frisk']),
    Asset('shady_koala', 'Shady Koala "Shenanigans"', 'Characters', (32, 40), screens=['phone-koala']),
    Asset('loansharks', 'Shrimp and Barbie, dingo loansharks', 'Characters', (64, 40),
          screens=['final-loansharks'], notes='Also on the phone loan sheet'),

    Asset('purse', "Mother's purse", 'Props', (32, 28), screens=['purse']),
    Asset('card_pack', 'Rugby Legends card pack', 'Props', (24, 32), screens=['auction']),
    Asset('card', 'Trading card', 'Props', (20, 28), screens=['auction-open']),
    Asset('card_holo', 'Holographic trading card', 'Props', (20, 28), screens=['auction-open']),
    Asset('briefcase', 'Silver briefcase', 'Props', (32, 24), screens=['case', 'phone-case-holder']),
    Asset('tickets', 'A fistful of tickets', 'Props', (32, 24), screens=['scalp']),
] + [
    Asset(R.venue_art(stop['venue']), f"{stop['venue']} ({stop['town']})", 'Venues', (64, 36),
          screens=[f"bet-{stop['event']}"], notes='Betting screen, next to the event description')
    for stop in GAMBLES
] + [
    Asset('summit', 'Summit and finish line', 'Event scenery', (128, 16), screens=['perform-speed_hike'],
          notes='A strip across the top of the Speed Hiking race'),
    Asset('dust_cloud', 'Fist fight dust cloud', 'Event scenery', (96, 32), screens=['perform-fist_fight']),
    Asset('sand_pitch', 'Sand curling pitch', 'Event scenery', (192, 32), screens=['perform-sand_curling'],
          notes='The ground strip under the player'),
    Asset('golf_hole', 'Mini golf hole and sculptures', 'Event scenery', (192, 32), screens=['perform-mini_golf'],
          notes='The ground strip under the player'),
    Asset('dohyo', 'Sumo dohyo ring', 'Event scenery', (96, 40), screens=['perform-sumo'],
          notes='Seen from above at an angle: the wrestlers stand on it'),
    Asset('half_court', 'Half basketball court', 'Event scenery', (192, 32), screens=['perform-half_court'],
          notes='The ground strip under the player'),
    Asset('hoop', 'Basketball hoop', 'Event scenery', (24, 24), screens=['perform-half_court']),
    Asset('opera_stage', 'Opera House stage', 'Event scenery', (128, 24), screens=['perform-note'],
          notes='A banner across the top of Holding A Note'),

    Asset('map', 'Map of Australia and New Zealand', 'Map', (192, 108), screens=['map'],
          notes='Covers longitude 110-181 E, latitude 8-48 S; stops are drawn on top'),
]
