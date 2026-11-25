"""
Down Under Gambler's Sweat It Out! Derby '27 - game data and pure rules.

Everything a playtest might want to tune lives here as a named constant, and every
rule is a plain function (no sockets, no timers) so it can be unit tested.
game.py wires these into phases; the clients get the numbers they need via
`client_rules()` and never retype them.
"""
import random
import re
from collections import Counter
from fractions import Fraction

from apge.art import PIXEL_CHARS as ART_CHARS

# ---- balance knobs ----------------------------------------------------------------

STARTING_CASH = 100
SKILL_POINTS = 10
MAX_STAT = SKILL_POINTS
STATS = (('str', 'STRENGTH'), ('spd', 'SPEED'), ('mcr', 'MORAL COURAGE'))
LUCK_LOW = 1
LUCK_HIGH = 10
MONEY_STEP = 10             # every +/- button moves money by this much (loans, ticket prices)
BET_STEPS = (1, 10, 100)    # the betting slip and card auction let you pick the +/- size
LOAN_AMOUNT = 5000          # the loansharks lend this much, take it or leave it, once per event
LOAN_MULTIPLIER = 2         # the loansharks want DOUBLE back at the end
MAX_NAME = 15

# Odds: run the event this many times with fresh LUCK and count wins
ODDS_SIMS = 100
ODDS_MAX_DENOMINATOR = 10   # keep fractions readable: 97/3 ok, 33/17 -> nearest x/10
ODDS_FLOOR = Fraction(1, 10)  # a sure thing still pays something
ODDS_CEILING = Fraction(50, 1)  # longest odds offered (99-1 longshots plus kneecaps broke the bank)
WINNER_CUT_PERCENT = 10     # the event's winner takes this share of every winning bet's winnings
MAX_TIEBREAKS = 25          # re-rolls before a dead heat is settled by coin flip

# ---- timers (seconds) -----------------------------------------------------------------

MAP_SECONDS = 5
BET_SECONDS = 75
FRISK_SECONDS = 8
RESULTS_SECONDS = 30        # Continue screens
PURSE_SECONDS = 45
AUCTION_SECONDS = 30
CARD_REVEAL_SECONDS = 16
CASE_SECONDS = 60
SCALP_SECONDS = 30
SCALP_ROUNDS = 4
FINAL_REVEAL_SECONDS = 4    # host pause per final-results beat (client-side pacing)
TIMER_WARNING_SECONDS = 10  # the host timer turns red and beeps once at this many seconds left
NEWS_LEAD_SECONDS = 2       # breaking news: the banner on its own before the first headline...
NEWS_SECONDS_EACH = 4       # ...then a new accident headline this often
BALLOON_SECONDS_EACH = 1    # before an event starts, a juice speech balloon pops up this often...
BALLOON_HOLD_SECONDS = 3    # ...and they all stay up this long before the starting gun

# ---- avatars -----------------------------------------------------------------------------

HEAD_GRID = 16              # heads are HEAD_GRID x HEAD_GRID pixel art
# Pixel art is a string: one char per cell, '.' = transparent, else an index into PALETTE.
# art_tools.py's 8 colours, plus skin tones and a few extras for faces.
PALETTE = [
    '#000000', '#ffffff', '#8c8c8c', '#dc2828', '#28b450', '#3c78dc', '#ffdc00', '#785028',
    '#f5c9a0', '#c68642', '#8d5524', '#ff8c00', '#ff69b4', '#7b3fa0',
]
PIXEL_CHARS = ART_CHARS[:len(PALETTE)]   # the same format as the game art (apge.art)
_HEAD_RE = re.compile('^[.%s]{%d}$' % (PIXEL_CHARS, HEAD_GRID * HEAD_GRID))
BLANK_HEAD = '.' * (HEAD_GRID * HEAD_GRID)


def valid_head(art):
    return isinstance(art, str) and bool(_HEAD_RE.match(art))


# ---- zones --------------------------------------------------------------------------------

# frisks: players frisked by the Kangarules Gambling Commission per gambling event
# (who the Shady Koala visits doesn't depend on the zone: see koala_visitors)
ZONES = {
    1: {'name': 'Youth Tournament', 'frisks': 0},
    2: {'name': 'Minor Leagues', 'frisks': 1},
    3: {'name': 'Professional Stadium', 'frisks': 1},
}

# ---- Shady Koala ("Shenanigans") ------------------------------------------------------------

# Prices are a percent of the buyer's cash, so the Koala is cheap for whoever is behind
KOALA_ITEMS = [
    {'id': 'accident', 'name': 'Have an Accident', 'percent': 15,
     'effect': "Pick a player to have an accident before the next event: a fall (-2 SPD and "
               "STR), a car (-4) or a bat to the kneecaps (-6). Equal odds"},
    {'id': 'juice', 'name': 'Juice', 'percent': 10,
     'effect': "Pick a player to juice up for the next event: a cup of joe (+2 SPD and STR), "
               "HGH (+4) or sand lobster venom (+6). Equal odds"},
    {'id': 'bribe', 'name': 'Bribe the Feds', 'percent': 5,
     'effect': "Pick a player for the Kangarules agent to watch: all Shady Koala effects "
               "on that player are negated for the next event"},
]
KOALA_BY_ID = {item['id']: item for item in KOALA_ITEMS}
KOALA_MIN_PRICE = 1         # nothing is free, even when you're nearly broke
KOALA_CHANCE = 0.5          # chance of a visit for anyone who isn't 1st or last

# What an accident or a juice turns out to be, picked at random with equal odds. `change` is
# added to the target's SPD and STR for the event; `text` is the host screen's flavour text.
# Accidents make the breaking news before the event, juice shows as speech balloons.
KOALA_OUTCOMES = {
    'accident': [
        {'id': 'fall', 'headline': 'Took a fall', 'change': -2,
         'text': '{name} took an unfortunate tumble . . .'},
        {'id': 'car', 'headline': 'Run Over by Car', 'change': -4,
         'text': '{name} got hit by a car!'},
        {'id': 'kneecaps', 'headline': 'Bat to Kneecaps', 'change': -6,
         'text': '{name} took a bat to the kneecaps!'},
    ],
    'juice': [
        {'id': 'joe', 'headline': 'Cup of Joe', 'change': 2, 'text': '{name} is looking peppy.'},
        {'id': 'hgh', 'headline': 'HGH', 'change': 4, 'text': '{name} is looking jacked.'},
        {'id': 'venom', 'headline': 'Sand Lobster Venom', 'change': 6,
         'text': '{name} is looking blistered and twitchy.'},
    ],
}
KOALA_STAT_FLOOR = 0        # accidents can't push a stat below this
AGAIN = ' [again]'          # added to a headline the player has had before this season


def koala_prices(cash):
    """What each item costs a buyer holding `cash` (rounded down to whole $Dd)."""
    return {item['id']: max(KOALA_MIN_PRICE, cash * item['percent'] // 100) for item in KOALA_ITEMS}


def koala_visitors(cash, rng):
    """Who the Shady Koala visits this event. cash: {player_id: cash in hand}.

    1st place never, last place always, everyone else on a KOALA_CHANCE coin flip. Ties share
    the place; when everyone is level (the first event) nobody is 1st or last, so all flip.
    """
    top, bottom = max(cash.values()), min(cash.values())
    visitors = set()
    for pid, amount in cash.items():
        if top != bottom and amount == top:
            continue
        if (top != bottom and amount == bottom) or rng.random() < KOALA_CHANCE:
            visitors.add(pid)
    return visitors


def resolve_koala(purchases, frisked):
    """Work out which Shady Koala purchases take effect.

    purchases: {buyer_id: {item_id: target_id}}
    frisked:   ids picked for a random Kangarules frisk

    Order of operations (later steps can't undo earlier ones):
      1. A frisked buyer loses ALL their purchases (made public on the host screen).
      2. Surviving bribes protect their targets from every accident/juice.
      3. Whatever's left applies (roll_koala picks what each one turns out to be).
    Returns {'caught': {buyer: {item: target}}, 'protected': set, 'applied': [(buyer, item, target)],
             'blocked': [(buyer, item, target)]}
    """
    caught = {b: dict(items) for b, items in purchases.items() if b in frisked and items}
    live = {b: items for b, items in purchases.items() if b not in frisked}
    protected = {items['bribe'] for items in live.values() if 'bribe' in items}
    applied, blocked = [], []
    for buyer, items in live.items():
        for item, target in items.items():
            if item == 'bribe':
                continue
            (blocked if target in protected else applied).append((buyer, item, target))
    return {'caught': caught, 'protected': protected, 'applied': applied, 'blocked': blocked}


def roll_koala(applied, rng):
    """What each accident and juice that got through turns out to be (equal odds).
    Returns [(target, item_id, outcome)], one per purchase, in random order so the host
    screen can't give away who bought first."""
    rolled = [(target, item, rng.choice(KOALA_OUTCOMES[item])) for _, item, target in applied]
    rng.shuffle(rolled)
    return rolled


def koala_headlines(rolled, names, history):
    """The host screen's lines for rolled Shady Koala effects: {item_id: [line, ...]}, each
    line {'id', 'headline', 'text', 'change'}. A player who has had the same outcome before
    this season (including earlier in this list) gets AGAIN on the end. `history` is a
    Counter of (player_id, outcome_id) for the season, updated here."""
    lines = {item: [] for item in KOALA_OUTCOMES}
    for target, item, outcome in rolled:
        key = (target, outcome['id'])
        text = outcome['text'].format(name=names[target]) + (AGAIN if history[key] else '')
        history[key] += 1
        lines[item].append({'id': target, 'headline': outcome['headline'], 'text': text,
                            'change': outcome['change']})
    return lines


def effective_stats(base, rolled):
    """Stats for one event after Shady Koala effects: every outcome's change is added to SPD
    and STR, then floored at KOALA_STAT_FLOOR (so the order never matters, and a negative
    stat can't turn a formula like STR x SPD upside down)."""
    stats = {pid: dict(s) for pid, s in base.items()}
    change = Counter()
    for target, _, outcome in rolled:
        change[target] += outcome['change']
    for pid, delta in change.items():
        if pid in stats:
            for key in ('spd', 'str'):
                stats[pid][key] = max(KOALA_STAT_FLOOR, stats[pid][key] + delta)
    return stats


# ---- gambling events ------------------------------------------------------------------------------
# score(s, luck): s = {'str', 'spd', 'mcr'}; one LUCK roll per player per score.
# visual: how the host animates it - 'race' (lanes, `direction`), 'elimination' (players drop
# out in reverse order, `variant` picks the look) or 'turns' (one at a time, score shown with `unit`).

def _whole(numerator, denominator):
    """numerator / denominator to the nearest whole number, halves up (negatives too), so
    fractional formulas still give the whole-number scores the host screen shows."""
    return (2 * numerator + denominator) // (2 * denominator)


def _half_court(s, luck):
    return _whole(s['str'] * 3 * s['spd'] + s['mcr'] + luck, 10)


# STR x 1.5 / x 2 rather than x 10 (2026-11-24): a 10-STR build won Fist Fight, Sand Curling
# and Sumo every time; now SPD and MCR builds can take Sand Curling and Sumo (tests/balance.py)
def _fist_fight(s, luck):
    return _whole(3 * s['str'] - 2 * s['spd'] - 2 * s['mcr'] + 2 * luck, 2)   # STR x 1.5 - SPD - MCR


def _sand_curling(s, luck):
    return _whole(15 * s['str'] + 12 * s['spd'] + 10 * luck, 10)   # STR x 1.5 + SPD x 1.2


def _sumo(s, luck):
    return _whole(4 * s['str'] + 3 * s['mcr'] + 2 * luck, 2)   # STR x 2 + MCR x 1.5


EVENTS = {
    'foot_race': {'name': 'Foot Race', 'visual': 'race', 'direction': 'right',
                  'score': lambda s, l: s['spd'] * 10 - s['str'] + l,
                  'setup': 'A footrace at half time of the under-10s field hockey.'},
    'speed_hike': {'name': 'Speed Hiking', 'visual': 'race', 'direction': 'up',
                   'score': lambda s, l: (s['spd'] + s['str']) + l * 2,
                   'setup': 'First to the top of the walking track wins.'},
    'fist_fight': {'name': 'Fist Fight', 'visual': 'elimination', 'variant': 'brawl',
                   'score': _fist_fight,
                   'setup': 'Last one standing wins. Nobody tell the parents.'},
    'sand_curling': {'name': 'Australian Rules Sand Curling', 'visual': 'turns', 'prop': 'kick',
                     'unit': 'meters', 'score': _sand_curling,
                     'setup': 'Kick the stone as far as you can down the sand.'},
    'mini_golf': {'name': 'Mini Golf', 'visual': 'turns', 'prop': 'golf', 'unit': 'strokes',
                  'lowest_wins': True,
                  'score': lambda s, l: 100 + s['str'] - s['spd'] * 2 - s['mcr'] * 4 - l,
                  'setup': 'Lowest score wins. Mind the sculptures.'},
    'mascot_race': {'name': 'Mascot Race', 'visual': 'race', 'direction': 'right', 'scale': 3,
                    'score': lambda s, l: s['spd'] * s['mcr'] + s['str'] + l,
                    'setup': 'Giant foam suits, one lap of the oval.'},
    'sumo': {'name': 'Sumo Wrestle', 'visual': 'elimination', 'variant': 'sumo', 'scale': 2,
             'score': _sumo,
             'setup': 'Push everyone else out of the ring.'},
    'half_court': {'name': 'Half-Court Shots', 'visual': 'turns', 'prop': 'shot',
                   'unit': 'half-court makes', 'score': _half_court,
                   'setup': 'Most half-court makes wins.'},
    'note': {'name': 'Holding A Note', 'visual': 'elimination', 'variant': 'note',
             'score': lambda s, l: (s['str'] + l) * 2 + s['spd'] + l + s['mcr'] * l,
             'setup': 'Hold the note longest. The acoustics are world class.'},
}


def roll_luck(rng):
    return rng.randint(LUCK_LOW, LUCK_HIGH)


def rank(stats, event_id, rng):
    """Finishing order for one running of an event.

    Returns (order, scores, tiebroken): order is best-first player ids, scores the first
    (displayed) score per player, tiebroken the ids whose place was settled by a re-roll.
    Ties re-roll LUCK for the tied players only, so nobody can drop out of their tied block.
    """
    event = EVENTS[event_id]
    score = event['score']
    lowest = event.get('lowest_wins', False)
    first = {pid: score(s, roll_luck(rng)) for pid, s in stats.items()}
    tiebroken = set()

    def settle(pids, scores, depth):
        ordered = []
        for value in sorted(set(scores[p] for p in pids), reverse=not lowest):
            tied = [p for p in pids if scores[p] == value]
            if len(tied) == 1:
                ordered += tied
            elif depth >= MAX_TIEBREAKS:
                rng.shuffle(tied)
                tiebroken.update(tied)
                ordered += tied
            else:
                tiebroken.update(tied)
                ordered += settle(tied, {p: score(stats[p], roll_luck(rng)) for p in tied}, depth + 1)
        return ordered

    return settle(list(stats), first, 0), first, tiebroken


def odds_calc(stats, event_id, rng, sims=ODDS_SIMS):
    """V1 odds: run the event `sims` times and turn win counts into fractional odds.

    Returns {player_id: Fraction} where Fraction(5, 2) means 5-2 (bet 2, win 5 + stake back).
    Swap this function out to change how odds work; payouts only use its output.
    """
    wins = Counter(rank(stats, event_id, rng)[0][0] for _ in range(sims))
    odds = {}
    for pid in stats:
        w = max(1, wins[pid])   # never-won still gets (long) odds rather than infinity
        fair = Fraction(sims - w, w).limit_denominator(ODDS_MAX_DENOMINATOR)
        odds[pid] = min(max(fair, ODDS_FLOOR), ODDS_CEILING)
    return odds


def odds_label(frac):
    return f'{frac.numerator}-{frac.denominator}'


def winner_cut(stake, frac):
    """The event winner's share of one winning bet: WINNER_CUT_PERCENT of its winnings."""
    winnings = (stake * frac.numerator) // frac.denominator
    return winnings * WINNER_CUT_PERCENT // 100


def payout(stake, frac):
    """Total returned on a winning bet: stake back plus winnings (rounded down), less the event
    winner's cut."""
    return stake + (stake * frac.numerator) // frac.denominator - winner_cut(stake, frac)


# ---- special events --------------------------------------------------------------------------------

PURSE_ALL_HONEST = 200    # everyone DON'T STEAL: each gets this
PURSE_LONE_THIEF = 1000   # exactly one STEAL: they get the whole purse
PURSE_PENALTY_PERCENT = 25   # more than one STEAL: EVERYONE loses this share of their cash
MCR_TO_CHOOSE = 2         # MCR must be ABOVE this to choose; otherwise you STEAL


def can_choose_morally(stats):
    return stats['mcr'] > MCR_TO_CHOOSE


def purse_payouts(choices, cash):
    """choices: {pid: 'steal'|'dont'}, cash: {pid: cash in hand} -> {pid: winnings}. When more
    than one player steals, everyone pays PURSE_PENALTY_PERCENT of their cash (rounded down)."""
    thieves = [p for p, c in choices.items() if c == 'steal']
    if not thieves:
        return {p: PURSE_ALL_HONEST for p in choices}
    if len(thieves) == 1:
        return {p: (PURSE_LONE_THIEF if p == thieves[0] else 0) for p in choices}
    return {p: -(cash[p] * PURSE_PENALTY_PERCENT // 100) for p in choices}


AUCTION_OPENING_BID = 10
COMMON_CARDS = 5
COMMON_CARD_VALUE = (10, 100)
HOLO_CARD_NAME = 'Dally Messenger Rookie Card'
HOLO_CARD_VALUE = (50, 2000)
# What a sealed pack can be worth, shown while bidding
CARD_PACK_VALUE = (COMMON_CARDS * COMMON_CARD_VALUE[0] + HOLO_CARD_VALUE[0],
                   COMMON_CARDS * COMMON_CARD_VALUE[1] + HOLO_CARD_VALUE[1])


def open_card_pack(rng):
    cards = [{'name': f'Card #{i + 1}/{COMMON_CARDS + 1}', 'value': rng.randint(*COMMON_CARD_VALUE)}
             for i in range(COMMON_CARDS)]
    cards.append({'name': HOLO_CARD_NAME, 'value': rng.randint(*HOLO_CARD_VALUE), 'holo': True})
    return cards


CASE_VALUE = (500, 10000)   # never shown to players: only the holder knows what's inside
CASE_CASH = 250             # "the CASH": this much for each voter (or for the holder)


def case_holder(stats, rng):
    """Highest MCR holds the case; ties picked at random."""
    best = max(s['mcr'] for s in stats.values())
    return rng.choice(sorted(p for p, s in stats.items() if s['mcr'] == best))


def case_decision(votes, rng):
    """Majority of the voters' 'case'/'cash'. A tie (or nobody voting) is a coin flip."""
    tally = Counter(votes.values())
    if tally['case'] == tally['cash']:
        return rng.choice(['case', 'cash']), True
    return ('case' if tally['case'] > tally['cash'] else 'cash'), False


def case_payouts(holder, voters, value, decision):
    """CASE: voters split the case (rounded down) and the holder gets CASE_CASH. CASH: every
    voter gets CASE_CASH and the holder gets the case."""
    if decision == 'case':
        share, holder_gets = (value // len(voters) if voters else 0), CASE_CASH
    else:
        share, holder_gets = CASE_CASH, value
    result = {p: share for p in voters}
    result[holder] = holder_gets
    return result


SCALP_FACE_VALUE = (150, 1500)
SCALP_MAX_MULTIPLIER = 2   # asks can go up to twice face value


def scalp_face_value(rng):
    lo, hi = SCALP_FACE_VALUE
    return rng.randrange(lo, hi + 1, MONEY_STEP)


def scalp_winner(asks):
    """Lowest ask that nobody else matched sells (and earns that much). None if every price tied."""
    counts = Counter(asks.values())
    for price in sorted(counts):
        if counts[price] == 1:
            return next(p for p, a in asks.items() if a == price)
    return None


# ---- the season --------------------------------------------------------------------------------------
# Every play-through has the same shape (which stops are gambling events or specials, and each
# stop's zone), filled with events drawn at random from the pools below, each at most once.
# Adding events to a pool means some won't appear in a given season. A gambling event brings
# its own town and venue; lat/lon place it on the host map, and specials sit between towns.

SPECIALS = {
    'mothers_purse': "Mother's Purse",
    'card_auction': 'Trading Card Auction',
    'case_or_no_case': 'Case or No Case',
    'ticket_scalping': 'Ticket Scalping',
}

GAMBLE_STOPS = [
    {'event': 'foot_race', 'town': 'Wanganui, NZ', 'venue': 'Wanganui Hockey Turf',
     'lat': -39.93, 'lon': 175.05},
    {'event': 'speed_hike', 'town': 'Hanmer Springs, NZ', 'venue': 'Conical Hill Walking Track',
     'lat': -42.52, 'lon': 172.83},
    {'event': 'fist_fight', 'town': 'Queenstown, NZ', 'venue': 'Queenstown Hill Walking Track',
     'lat': -45.03, 'lon': 168.66},
    {'event': 'sand_curling', 'town': 'Dubbo, AUS', 'venue': 'Barden Park',
     'lat': -32.25, 'lon': 148.60},
    {'event': 'mini_golf', 'town': 'Lightning Ridge, AUS',
     'venue': 'Peter Cookes Mini Golf & Sculpture Park', 'lat': -29.43, 'lon': 147.98},
    {'event': 'mascot_race', 'town': 'Adelaide, AUS', 'venue': 'Adelaide Oval',
     'lat': -34.93, 'lon': 138.60},
    {'event': 'sumo', 'town': 'Melbourne, AUS', 'venue': 'Lakeside Stadium',
     'lat': -37.81, 'lon': 144.96},
    {'event': 'half_court', 'town': 'Perth, AUS', 'venue': 'Optus Stadium',
     'lat': -31.95, 'lon': 115.86},
    {'event': 'note', 'town': 'Sydney, AUS', 'venue': 'Opera House',
     'lat': -33.87, 'lon': 151.21},
]

# (kind, zone) per stop: 13 stops, 9 gambling events and 4 specials
SEASON_SHAPE = [
    ('gamble', 1), ('special', 1), ('gamble', 1), ('gamble', 1),
    ('special', 2), ('gamble', 2), ('gamble', 2), ('special', 2), ('gamble', 2),
    ('gamble', 3), ('special', 3), ('gamble', 3), ('gamble', 3),
]


def build_season(rng=None):
    """The season's stops, in order. With an rng, the events are a random draw from the pools;
    without one, the pools in listed order (the design doc's route, for tests and samples)."""
    def draw(pool, kind):
        count = sum(1 for k, _ in SEASON_SHAPE if k == kind)
        return iter(rng.sample(pool, count) if rng else pool[:count])
    gambles = draw(GAMBLE_STOPS, 'gamble')
    specials = draw(list(SPECIALS), 'special')
    season = []
    for kind, zone in SEASON_SHAPE:
        if kind == 'gamble':
            season.append(dict(next(gambles), kind=kind, zone=zone))
        else:
            season.append({'kind': kind, 'event': next(specials), 'zone': zone})
    return season


def venue_art(venue):
    """Art id of a venue's picture (dev.ART lists one per venue)."""
    return 'venue_' + re.sub(r'[^a-z0-9]+', '_', venue.lower()).strip('_')


def stop_name(stop):
    if stop['kind'] == 'special':
        return SPECIALS[stop['event']]
    return EVENTS[stop['event']]['name']


def season_map(season):
    """Public description of the route for the host map. Specials get a spot between towns."""
    out = []
    for i, stop in enumerate(season):
        entry = {'kind': stop['kind'], 'name': stop_name(stop), 'zone': stop['zone'],
                 'zone_name': ZONES[stop['zone']]['name']}
        if stop['kind'] == 'gamble':
            entry.update(town=stop['town'], venue=stop['venue'], lat=stop['lat'], lon=stop['lon'])
        else:
            prev = next((s for s in reversed(season[:i]) if 'lat' in s), None)
            nxt = next((s for s in season[i + 1:] if 'lat' in s), None)
            ends = [s for s in (prev, nxt) if s] or [{'lat': -35.0, 'lon': 150.0}]
            entry.update(lat=sum(s['lat'] for s in ends) / len(ends),
                         lon=sum(s['lon'] for s in ends) / len(ends))
        out.append(entry)
    return out


def perform_seconds(event_id, n_players):
    """How long the host animation runs (the phase timer matches it)."""
    visual = EVENTS[event_id]['visual']
    if visual == 'race':
        return 9
    if visual == 'elimination':
        return 4 + 2 * max(1, n_players - 1)
    return 2 + 3 * n_players   # turns


def news_seconds(headlines):
    """How long the breaking news runs (0 headlines: it's skipped)."""
    return NEWS_LEAD_SECONDS + NEWS_SECONDS_EACH * headlines if headlines else 0


def balloon_seconds(balloons):
    """How long the juice speech balloons hold up the start of the event animation."""
    return BALLOON_HOLD_SECONDS + BALLOON_SECONDS_EACH * balloons if balloons else 0


def client_rules():
    """The numbers the phone and host pages need, sent in every view (one source of truth)."""
    return {
        'starting_cash': STARTING_CASH, 'skill_points': SKILL_POINTS, 'max_stat': MAX_STAT,
        'stats': [{'id': k, 'label': v} for k, v in STATS],
        'money_step': MONEY_STEP, 'loan_amount': LOAN_AMOUNT, 'loan_multiplier': LOAN_MULTIPLIER,
        'head_grid': HEAD_GRID, 'palette': PALETTE, 'pixel_chars': PIXEL_CHARS,
        'koala_items': KOALA_ITEMS, 'mcr_to_choose': MCR_TO_CHOOSE,
        'purse': {'honest': PURSE_ALL_HONEST, 'thief': PURSE_LONE_THIEF,
                  'penalty_percent': PURSE_PENALTY_PERCENT},
        'scalp_steps': [MONEY_STEP, 100],
        'case_cash': CASE_CASH, 'scalp_rounds': SCALP_ROUNDS,
        'scalp_max_multiplier': SCALP_MAX_MULTIPLIER, 'auction_opening_bid': AUCTION_OPENING_BID,
        'card_pack_value': list(CARD_PACK_VALUE), 'bet_steps': list(BET_STEPS),
        'winner_cut_percent': WINNER_CUT_PERCENT, 'final_reveal_seconds': FINAL_REVEAL_SECONDS,
        'news_lead_seconds': NEWS_LEAD_SECONDS, 'news_seconds_each': NEWS_SECONDS_EACH,
        'balloon_seconds_each': BALLOON_SECONDS_EACH,
    }


def new_rng(seed=None):
    return random.Random(seed)
