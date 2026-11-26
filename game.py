"""
Down Under Gambler's Sweat It Out! Derby '27 - phases and actions.

Flow (one season stop at a time; rules.build_season shuffles the stops each game):

    lobby (draw head, spend skill points) -> map -> stop -> map -> stop ... -> game_over

    gambling stop:  bet -> [frisk] -> [news] -> perform -> payout
                    (news: Shady Koala accidents as breaking news; juice shows as speech
                    balloons at the start of perform)
    specials:       purse -> purse_result
                    auction -> auction_open -> auction_result
                    case -> case_result
                    scalp -> scalp_result (x SCALP_ROUNDS)

Hidden information: cash, stats, bets, loans and Shady Koala purchases live in
player.private. Money from an event is only applied when its result screen opens, so a
phone's cash total never spoils a race that's still running on the big screen.
"""
import random
from collections import Counter

from apge import LOBBY, Game, Reject, action, on_all_ready, on_timeout, phase

import rules as R

# Per-stop state, cleared every time the map is shown
ROUND_PUBLIC = ('event', 'odds', 'frisks', 'news', 'performance', 'payout', 'purse', 'auction',
                'case', 'scalp')
ROUND_PRIVATE = ('bets', 'koala', 'choice', 'forced', 'vote', 'case_value', 'ask', 'last',
                 'loan_taken')

# Input phases that end early once every connected player is done: phase -> method name
FINISH_WHEN_ALL_DONE = {
    'bet': 'finish_betting',
    'purse': 'finish_purse',
    'case': 'finish_case',
    'scalp': 'finish_scalp',
}

# Nobody is choosing anything here, so the host timer never warns (no red, no beep)
WATCH_PHASES = ('map', 'frisk', 'news', 'perform', 'auction_open')

SPECIAL_FIRST_PHASE = {
    'mothers_purse': 'purse',
    'card_auction': 'auction',
    'case_or_no_case': 'case',
    'ticket_scalping': 'scalp',
}


def whole(value, lo, hi, what):
    """A whole number in [lo, hi] from a phone. Rejects bools (True is an int in Python)."""
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise Reject(f'{what} must be from {lo} to {hi}.')
    return value


def money(value, lo, hi, what, step=R.MONEY_STEP):
    if hi < lo:
        raise Reject(f"You can't afford that {what.lower()}.")
    amount = whole(value, lo, hi, what)
    if amount % step:
        raise Reject(f'{what} goes up in steps of {step}.')
    return amount


def choice(value, options, what):
    # Every option is a string; anything else (a list, a dict) would crash the `in` check
    if not isinstance(value, str) or value not in options:
        raise Reject(f'Pick {what}.')
    return value


class Derby(Game):
    title = "Down Under Gambler's Sweat It Out! Derby '27"
    min_players = 2
    max_players = 8
    max_name = R.MAX_NAME
    # The first player to finish their character runs the game from their phone
    vip_commands = ('start', 'reset', 'quit')

    def __init__(self, seed=None):
        super().__init__()
        self.rng = random.Random(seed)
        self.finish_order = []     # player ids in the order they finished their character
        self.season = []
        self.odds = {}
        self.koala_purchases = {}  # {buyer_id: {item_id: target_id}} - server only
        self.outcome = None        # finishing order etc. for the current gambling event
        self.koala_history = Counter()   # (player_id, outcome_id) seen this season, for [again]
        self.case_secret = None    # {'holder', 'value'} - server only

    # ---- views -----------------------------------------------------------------

    def public_view(self):
        view = super().public_view()
        view['rules'] = R.client_rules()
        view['timer_warning'] = None if self.phase in WATCH_PHASES else R.TIMER_WARNING_SECONDS
        return view

    # ---- lobby: character creation ------------------------------------------------

    def vip(self):
        for pid in self.finish_order:
            player = self.players.get(pid)
            if player and player.connected:
                return player
        return None

    def lobby_ready(self):
        return len(self.players) >= self.min_players and self.everyone(
            lambda p: p.public.get('character_done'), include_disconnected=False)

    @action('submit_head', phases=LOBBY)
    def submit_head(self, player, data):
        if player.public.get('character_done'):
            raise Reject('Your character is already finished.')
        art = data.get('head')
        if not R.valid_head(art):
            raise Reject("That drawing didn't come through - try again.")
        player.public['head'] = art

    @action('submit_stats', phases=LOBBY)
    def submit_stats(self, player, data):
        if 'head' not in player.public:
            raise Reject('Draw your head first!')
        if player.public.get('character_done'):
            raise Reject('Your character is already finished.')
        stats = {key: whole(data.get(key), 0, R.MAX_STAT, label) for key, label in R.STATS}
        if sum(stats.values()) > R.SKILL_POINTS:
            raise Reject(f'You only have {R.SKILL_POINTS} skill points.')
        catchphrase = R.clean_catchphrase(data.get('catchphrase', ''))
        if catchphrase is None:
            raise Reject(f'Keep your Victory Catchphrase to {R.MAX_CATCHPHRASE} characters.')
        player.private['stats'] = stats
        # Private until they win an event: then it pops up on the big screen
        player.private['catchphrase'] = catchphrase
        player.public['character_done'] = True
        self.finish_order.append(player.id)

    def on_start(self):
        for p in self.players.values():
            if not p.public.get('character_done'):
                # The host started without them: blank head and no points, but nobody is locked out
                p.public.setdefault('head', R.BLANK_HEAD)
                p.private['stats'] = {key: 0 for key, _ in R.STATS}
                p.public['character_done'] = True
                self.finish_order.append(p.id)
            p.private.update(cash=R.STARTING_CASH, borrowed=0, bets_won=0, money_lost=0)
        self.season = R.build_season(self.rng)
        self.koala_history = Counter()
        self.public['season'] = R.season_map(self.season)
        self.public['stop'] = -1
        self.next_stop()

    def on_reset(self):
        """One more game: same players and heads, fresh skill points and cash."""
        self.public = {}
        self.finish_order = []
        for p in self.players.values():
            head, catchphrase = p.public.get('head'), p.private.get('catchphrase')
            p.public = {'head': head} if head else {}
            # Kept, like the head: the character screen offers it again to keep or change
            p.private = {'catchphrase': catchphrase} if catchphrase else {}

    def on_quit(self):
        super().on_quit()
        self.finish_order = []

    def on_player_removed(self, player):
        # Kicked, or a leftover from a phone that joined again under a new name (APGE 0.4)
        if player.id in self.finish_order:
            self.finish_order.remove(player.id)

    # ---- helpers -------------------------------------------------------------------

    def current_stop(self):
        return self.season[self.public['stop']]

    def base_stats(self):
        return {pid: p.private['stats'] for pid, p in self.players.items()}

    def start_round(self):
        for p in self.players.values():
            for key in ROUND_PRIVATE:
                p.private.pop(key, None)
            p.public['done'] = False

    def all_done(self):
        # Nobody connected means nobody to wait for - but don't race ahead on an empty room
        return bool(self.connected_players()) and self.everyone(
            lambda p: p.public.get('done'), include_disconnected=False)

    def mark_done(self, player):
        if player.public.get('done'):
            raise Reject("You're locked in.")
        player.public['done'] = True

    def finish_if_all_done(self):
        """End the current input phase early if nobody connected is still choosing."""
        finish = FINISH_WHEN_ALL_DONE.get(self.phase)
        if finish and self.all_done():
            getattr(self, finish)()

    def on_player_disconnected(self, player):
        # The last holdout leaving mustn't make everyone wait out the timer
        self.finish_if_all_done()

    def credit(self, player, amount, net=None):
        """Pay a player; `last` is what their phone shows as this event's result."""
        player.private['cash'] += amount
        player.private['last'] = amount if net is None else net

    def next_stop(self):
        self.public['stop'] += 1
        if self.public['stop'] >= len(self.season):
            self.goto('game_over')
            return
        # A random player's avatar marks where everyone is on the map
        self.public['map_marker'] = self.rng.choice(list(self.players))
        self.goto('map')

    # ---- map ----------------------------------------------------------------------

    @phase('map', timer=R.MAP_SECONDS)
    def enter_map(self):
        for key in ROUND_PUBLIC:
            self.public.pop(key, None)
        for p in self.players.values():
            p.public['done'] = False

    @on_timeout('map')
    def map_done(self):
        stop = self.current_stop()
        if stop['kind'] == 'gamble':
            self.goto('bet')
        else:
            self.goto(SPECIAL_FIRST_PHASE[stop['event']])

    # ---- gambling: betting slip + Shady Koala + loansharks -----------------------------

    @phase('bet', timer=R.BET_SECONDS)
    def enter_bet(self):
        stop = self.current_stop()
        zone = R.ZONES[stop['zone']]
        event = R.EVENTS[stop['event']]
        self.start_round()
        self.odds = R.odds_calc(self.base_stats(), stop['event'], self.rng)
        number, of = R.gamble_number(self.season, self.public['stop'])
        self.public['event'] = {
            'number': number, 'of': of, 'id': stop['event'], 'name': event['name'], 'setup': event['setup'],
            'town': stop['town'], 'venue': stop['venue'], 'zone_name': zone['name'],
            'venue_art': R.venue_art(stop['venue']),
            'visual': event['visual'], 'direction': event.get('direction'),
            'variant': event.get('variant'), 'prop': event.get('prop'),
            'unit': event.get('unit'), 'scale': event.get('scale', 1),
            'lowest_wins': event.get('lowest_wins', False),
        }
        self.public['odds'] = {pid: {'num': f.numerator, 'den': f.denominator,
                                     'label': R.odds_label(f)} for pid, f in self.odds.items()}
        self.koala_purchases = {}
        cash = {pid: p.private['cash'] for pid, p in self.players.items()}
        for pid in R.koala_visitors(cash, self.rng):
            self.players[pid].private['koala'] = {'state': 'pending', 'bought': {}}

    @action('borrow', phases='bet')
    def borrow(self, player, data):
        # A fixed LOAN_AMOUNT, at most once per betting event (loan_taken clears each round)
        if player.public['done']:
            raise Reject('Your bets are already locked in.')
        if player.private.get('loan_taken'):
            raise Reject('Shrimp and Barbie only lend once per event.')
        player.private['cash'] += R.LOAN_AMOUNT
        player.private['borrowed'] += R.LOAN_AMOUNT
        player.private['loan_taken'] = True

    def koala_visit(self, player, *states):
        visit = player.private.get('koala')
        if not visit or visit['state'] not in states:
            raise Reject("The Shady Koala isn't talking to you.")
        return visit

    @action('koala_open', phases='bet')
    def koala_open(self, player, data):
        visit = self.koala_visit(player, 'pending')
        # Priced from the cash you hold when you open the menu (loans already taken count),
        # and fixed for the visit so one purchase doesn't make the next one cheaper
        visit.update(state='open', prices=R.koala_prices(player.private['cash']))

    @action('koala_buy', phases='bet')
    def koala_buy(self, player, data):
        visit = self.koala_visit(player, 'open')
        item = R.KOALA_BY_ID.get(data.get('item'))
        if not item:
            raise Reject('Pick something from the menu.')
        if item['id'] in visit['bought']:
            raise Reject('You already bought that one.')
        target = choice(data.get('target'), self.players, 'a player')
        price = visit['prices'][item['id']]
        if player.private['cash'] < price:
            raise Reject("You can't afford that.")
        player.private['cash'] -= price
        visit['bought'][item['id']] = target
        self.koala_purchases.setdefault(player.id, {})[item['id']] = target

    @action('koala_exit', phases='bet')
    def koala_exit(self, player, data):
        self.koala_visit(player, 'pending', 'open')['state'] = 'closed'

    @action('confirm_bets', phases='bet')
    def confirm_bets(self, player, data):
        if player.public['done']:
            raise Reject('Your bets are already locked in.')
        visit = player.private.get('koala')
        if visit and visit['state'] == 'pending':
            raise Reject('Psst! Someone wants a word first.')
        slip = data.get('bets')
        if not isinstance(slip, dict):
            raise Reject('Something was wrong with that betting slip.')
        cash = player.private['cash']
        bets = {}
        for pid, amount in slip.items():
            choice(pid, self.players, 'players who are racing')
            amount = money(amount, 0, cash, 'Bet', step=1)
            if amount:
                bets[pid] = amount
        if sum(bets.values()) > cash:
            raise Reject("You can't bet more than you have.")
        player.private['cash'] -= sum(bets.values())
        player.private['bets'] = bets
        if visit:
            visit['state'] = 'closed'
        player.public['done'] = True
        self.finish_if_all_done()

    @on_timeout('bet')
    def bet_timeout(self):
        self.finish_betting()   # unconfirmed slips are simply no bets

    def finish_betting(self):
        stop = self.current_stop()
        ids = list(self.players)
        frisked = set(self.rng.sample(ids, min(R.ZONES[stop['zone']]['frisks'], len(ids))))
        koala = R.resolve_koala(self.koala_purchases, frisked)
        # (a target kicked since the purchase has nobody left to hit)
        rolled = R.roll_koala([a for a in koala['applied'] if a[2] in self.players], self.rng)
        stats = R.effective_stats(self.base_stats(), rolled)
        order, scores, tiebroken = R.rank(stats, stop['event'], self.rng)
        names = {pid: p.name for pid, p in self.players.items()}
        # Who was hit or juiced (and with what) goes public; who paid for it never does
        lines = R.koala_headlines(rolled, names, self.koala_history)
        self.outcome = {'order': order, 'scores': scores, 'tiebroken': tiebroken,
                        'news': lines['accident'], 'balloons': lines['juice']}
        if not frisked:
            self.break_news()
            return
        name = names.get
        self.public['frisks'] = [
            {'id': pid, 'name': name(pid),
             'caught': [{'item': R.KOALA_BY_ID[item]['name'], 'target': name(target)}
                        for item, target in koala['caught'].get(pid, {}).items()]}
            for pid in ids if pid in frisked]
        self.goto('frisk')

    @phase('frisk', timer=R.FRISK_SECONDS)
    def enter_frisk(self):
        pass

    @on_timeout('frisk')
    def frisk_done(self):
        self.break_news()

    def break_news(self):
        """Accidents make the breaking news before the event; with none, straight to it."""
        news = self.outcome['news']
        if news:
            self.goto('news', timer=R.news_seconds(len(news)))
        else:
            self.start_perform()

    @phase('news')
    def enter_news(self):
        self.public['news'] = self.outcome['news']

    @on_timeout('news')
    def news_done(self):
        self.start_perform()

    def start_perform(self):
        o = self.outcome
        o['animation'] = R.perform_seconds(self.current_stop()['event'], len(self.players))
        o['intro'] = R.balloon_seconds(len(o['balloons']))
        winner = self.players.get(o['order'][0])
        said = winner.private.get('catchphrase') if winner else None
        o['catchphrase'] = [{'id': winner.id, 'text': said}] if said else []
        o['outro'] = R.CATCHPHRASE_SECONDS if said else 0
        self.goto('perform', timer=o['intro'] + o['animation'] + o['outro'])

    @phase('perform')
    def enter_perform(self):
        o = self.outcome
        # The juice speech balloons pop up over the starting line for `intro` seconds, the
        # event runs for `duration`, then the winner's Victory Catchphrase for `outro`
        self.public['performance'] = {
            'order': o['order'], 'scores': o['scores'], 'tiebroken': sorted(o['tiebroken']),
            'balloons': o['balloons'], 'intro': o['intro'], 'duration': o['animation'],
            'catchphrase': o['catchphrase'], 'outro': o['outro']}

    @on_timeout('perform')
    def perform_done(self):
        self.goto('payout')

    @phase('payout', timer=R.RESULTS_SECONDS, ready=True)
    def enter_payout(self):
        winner = self.outcome['order'][0]
        odds = self.odds[winner]
        winning, cut = [], 0
        for p in self.players.values():
            bets = p.private.get('bets', {})
            lost = sum(amount for pid, amount in bets.items() if pid != winner)
            p.private['money_lost'] += lost
            won = R.payout(bets[winner], odds) if winner in bets else 0
            if won:
                p.private['bets_won'] += 1
                cut += R.winner_cut(bets[winner], odds)
                winning.append({'id': p.id, 'name': p.name, 'stake': bets[winner], 'payout': won})
            self.credit(p, won, net=won - sum(bets.values()))
        # The event's winner takes their cut of every winning bet (their own included)
        champ = self.players.get(winner)
        if champ:
            self.credit(champ, cut, net=champ.private['last'] + cut)
        self.public['payout'] = {'winner': winner, 'odds': R.odds_label(odds),
                                 'order': self.outcome['order'], 'winning_bets': winning,
                                 'winner_cut': cut}

    @on_all_ready('payout')
    def payout_done(self):
        self.next_stop()

    # ---- special: Mother's Purse ---------------------------------------------------------

    @phase('purse', timer=R.PURSE_SECONDS)
    def enter_purse(self):
        self.start_round()
        for p in self.players.values():
            if not R.can_choose_morally(p.private['stats']):
                p.private.update(choice='steal', forced=True)
                p.public['done'] = True
        self.finish_if_all_done()

    def finish_purse(self):
        self.goto('purse_result')

    @action('purse_choice', phases='purse')
    def purse_choice(self, player, data):
        picked = choice(data.get('choice'), ('steal', 'dont'), 'STEAL or DON\'T STEAL')
        self.mark_done(player)
        player.private['choice'] = picked
        self.finish_if_all_done()

    @on_timeout('purse')
    def purse_timeout(self):
        self.finish_purse()

    @phase('purse_result', timer=R.RESULTS_SECONDS, ready=True)
    def enter_purse_result(self):
        # No answer counts as DON'T STEAL
        choices = {pid: p.private.get('choice', 'dont') for pid, p in self.players.items()}
        won = R.purse_payouts(choices, {pid: p.private['cash'] for pid, p in self.players.items()})
        for pid, p in self.players.items():
            self.credit(p, won[pid])
        # A 25% loss would reveal everyone's cash, so the host only says that everyone lost it
        penalty = sum(1 for c in choices.values() if c == 'steal') > 1
        self.public['purse'] = [{'id': pid, 'name': p.name, 'choice': choices[pid],
                                 'won': None if penalty else won[pid],
                                 'forced': bool(p.private.get('forced'))}
                                for pid, p in self.players.items()]

    @on_all_ready('purse_result')
    def purse_result_done(self):
        self.next_stop()

    # ---- special: Trading Card Auction -------------------------------------------------------

    @phase('auction', timer=R.AUCTION_SECONDS)
    def enter_auction(self):
        self.start_round()
        self.public['auction'] = {'high_bid': None, 'leader': None, 'leader_name': None}

    @action('bid', phases='auction')
    def bid(self, player, data):
        auction = self.public['auction']
        if auction['leader'] == player.id:
            raise Reject("You're already the high bidder.")
        lowest = (R.AUCTION_OPENING_BID if auction['leader'] is None
                  else auction['high_bid'] + R.MONEY_STEP)
        amount = money(data.get('amount'), lowest, player.private['cash'], 'Bid', step=1)
        auction.update(high_bid=amount, leader=player.id, leader_name=player.name)

    @on_timeout('auction')
    def auction_timeout(self):
        if self.public['auction']['leader'] is None:
            self.goto('auction_result')   # nobody bid: nothing to open
        else:
            self.goto('auction_open')

    @phase('auction_open', timer=R.CARD_REVEAL_SECONDS)
    def enter_auction_open(self):
        cards = R.open_card_pack(self.rng)
        self.public['auction'].update(cards=cards, total=sum(c['value'] for c in cards))

    @on_timeout('auction_open')
    def auction_open_done(self):
        self.goto('auction_result')

    @phase('auction_result', timer=R.RESULTS_SECONDS, ready=True)
    def enter_auction_result(self):
        auction = self.public['auction']
        if auction['leader'] in self.players:
            winner = self.players[auction['leader']]
            winner.private['cash'] -= auction['high_bid']
            self.credit(winner, auction['total'], net=auction['total'] - auction['high_bid'])

    @on_all_ready('auction_result')
    def auction_result_done(self):
        self.next_stop()

    # ---- special: Case or No Case ----------------------------------------------------------------

    @phase('case', timer=R.CASE_SECONDS)
    def enter_case(self):
        self.start_round()
        holder = self.players[R.case_holder(self.base_stats(), self.rng)]
        value = self.rng.randint(*R.CASE_VALUE)
        self.case_secret = {'holder': holder.id, 'value': value}
        holder.private['case_value'] = value
        holder.public['done'] = True   # the holder has no buttons
        self.public['case'] = {'holder': holder.id, 'holder_name': holder.name, 'cash': R.CASE_CASH}
        self.finish_if_all_done()

    def finish_case(self):
        self.goto('case_result')

    @action('case_vote', phases='case')
    def case_vote(self, player, data):
        if player.id == self.case_secret['holder']:
            raise Reject("You're holding the case - convince them!")
        picked = choice(data.get('vote'), ('case', 'cash'), 'The CASE or The CASH')
        self.mark_done(player)
        player.private['vote'] = picked
        self.finish_if_all_done()

    @on_timeout('case')
    def case_timeout(self):
        self.finish_case()

    @phase('case_result', timer=R.RESULTS_SECONDS, ready=True)
    def enter_case_result(self):
        holder, value = self.case_secret['holder'], self.case_secret['value']
        voters = [pid for pid in self.players if pid != holder]
        votes = {pid: self.players[pid].private['vote'] for pid in voters
                 if 'vote' in self.players[pid].private}
        decision, coin_flip = R.case_decision(votes, self.rng)
        won = R.case_payouts(holder, voters, value, decision)
        for pid, p in self.players.items():
            self.credit(p, won.get(pid, 0))
        self.public['case'].update(
            decision=decision, coin_flip=coin_flip,
            votes=[{'name': self.players[pid].name, 'vote': votes.get(pid)} for pid in voters],
            share=won[voters[0]] if voters else 0,
            # If they took the cash, how much was in the case stays the holder's secret
            value=value if decision == 'case' else None)

    @on_all_ready('case_result')
    def case_result_done(self):
        self.next_stop()

    # ---- special: Ticket Scalping ------------------------------------------------------------------

    @phase('scalp', timer=R.SCALP_SECONDS)
    def enter_scalp(self):
        self.start_round()
        previous = (self.public.get('scalp') or {}).get('round', 0)
        self.public['scalp'] = {'round': previous + 1, 'rounds': R.SCALP_ROUNDS,
                                'face': R.scalp_face_value(self.rng)}

    @action('scalp_ask', phases='scalp')
    def scalp_ask(self, player, data):
        face = self.public['scalp']['face']
        price = money(data.get('price'), R.MONEY_STEP, face * R.SCALP_MAX_MULTIPLIER, 'Price')
        self.mark_done(player)
        player.private['ask'] = price
        self.finish_if_all_done()

    def finish_scalp(self):
        self.goto('scalp_result')

    @on_timeout('scalp')
    def scalp_timeout(self):
        self.finish_scalp()

    @phase('scalp_result', timer=R.RESULTS_SECONDS, ready=True)
    def enter_scalp_result(self):
        asks = {pid: p.private['ask'] for pid, p in self.players.items() if 'ask' in p.private}
        winner = R.scalp_winner(asks)
        if winner:
            self.credit(self.players[winner], asks[winner])
        self.public['scalp'].update(
            winner=winner, winner_name=self.players[winner].name if winner else None,
            price=asks.get(winner),
            asks=sorted(({'name': self.players[pid].name, 'price': price}
                         for pid, price in asks.items()), key=lambda a: a['price']))

    @on_all_ready('scalp_result')
    def scalp_result_done(self):
        if self.public['scalp']['round'] < R.SCALP_ROUNDS:
            # Keep the round counter; enter_scalp reads it
            scalp = self.public['scalp']
            self.public['scalp'] = {'round': scalp['round']}
            self.goto('scalp')
        else:
            self.next_stop()

    # ---- season over --------------------------------------------------------------------------------

    @phase('game_over')
    def enter_game_over(self):
        rows = []
        for p in self.players.values():
            debt = p.private['borrowed'] * R.LOAN_MULTIPLIER
            rows.append({'id': p.id, 'name': p.name, 'cash': p.private['cash'], 'debt': debt,
                         'final': p.private['cash'] - debt, 'bets_won': p.private['bets_won'],
                         'money_lost': p.private['money_lost']})
        after = sorted(rows, key=lambda r: -r['final'])
        top = after[0]['final']
        self.public['final'] = {
            'before': sorted(rows, key=lambda r: r['cash']),   # last place first, for the reveal
            'after': after,
            'winners': [r['name'] for r in after if r['final'] == top],
            'awards': [award for award in (
                self._award(rows, 'bets_won', 'Sharpest Punter', lambda n: f"{n} bet{'' if n == 1 else 's'} won"),
                self._award(rows, 'money_lost', 'Biggest Mug', lambda n: f'$Dd {n} lost on bets'),
            ) if award],
        }

    @staticmethod
    def _award(rows, key, title, describe):
        best = max(r[key] for r in rows)
        if best <= 0:
            return None
        return {'title': title, 'names': [r['name'] for r in rows if r[key] == best],
                'value': best, 'label': describe(best)}
