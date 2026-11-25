"""
Browser check: Playwright drives the real host page and three phone-sized player pages
through character creation, a gambling event, every special event, one of each event
animation and the final results, failing on any JavaScript error.

    pip install playwright && python -m playwright install chromium
    python tests/test_browser.py [--shots DIR]     # DIR gets a screenshot of every screen

Bots (test_bots.py) test the server; this catches what only a browser shows.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from apge.testing import free_port  # noqa: E402

import rules as R  # noqa: E402
from app import make_server as make_party_server  # noqa: E402
from game import Derby  # noqa: E402

PHONE = {'width': 390, 'height': 844}
TV = {'width': 1280, 'height': 720}
NAMES = ['Shazza', 'Davo', 'Kylie']


class Check:
    def __init__(self, shots):
        self.shots = shots
        self.errors = []
        self.count = 0

    def watch(self, page, label):
        page.on('pageerror', lambda e: self.errors.append(f'{label}: {e}'))
        page.on('console', lambda m: m.type == 'error' and self.errors.append(f'{label} console: {m.text}'))

    def shot(self, page, name):
        if self.shots:
            self.count += 1
            page.screenshot(path=os.path.join(self.shots, f'{self.count:02d}-{name}.png'))


def wait_phase(game, phase, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if game.phase == phase:
            time.sleep(0.4)   # let the pages render the new state
            return
        time.sleep(0.05)
    raise AssertionError(f'never reached {phase} (stuck in {game.phase})')


def use_design_doc_route(game):
    """Test hook: swap the shuffled season for the unshuffled one, so each event is at a known
    stop and zone (Sand Curling needs zone 2's frisk). Call while the first map is showing."""
    with game.lock:
        game.season = R.build_season()
        game.public['season'] = R.season_map(game.season)
        game.mark_dirty()
        game._flush()


STOP = {stop['event']: i for i, stop in enumerate(R.build_season())}


def jump_to(game, stop_index):
    """Test hook: make the next map stop `stop_index` (skips the stops in between)."""
    with game.lock:
        game.public['stop'] = stop_index - 1
        game.next_stop()
        game._flush()


def skip(game):
    with game.lock:
        game._skip()
        game._flush()


def tap(page, selector, nth=0):
    page.locator(selector).nth(nth).click()
    time.sleep(0.15)


def main(shots=None):
    if shots:
        os.makedirs(shots, exist_ok=True)
    check = Check(shots)
    game = Derby(seed=7)
    # Real speed, so screenshots catch the animations mid-flight; long timers get skipped
    port = free_port()
    party = make_party_server(game, port=port)
    httpd = make_server('127.0.0.1', port, party.app, threaded=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{port}'

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        host = browser.new_page(viewport=TV)
        check.watch(host, 'host')
        host.goto(url + '/')
        phones = []
        for name in NAMES:
            ctx = browser.new_context(viewport=PHONE, has_touch=True)
            page = ctx.new_page()
            check.watch(page, name)
            page.goto(url + '/player')
            page.fill('#join-form input', name)
            page.click('#join-form button')
            phones.append(page)
        time.sleep(0.5)
        check.shot(phones[0], 'phone-draw')

        # The playtest's phantom players: Kylie's phone opens a fresh tab and joins as someone
        # else, then the old tab goes away. The old Kylie must not stay in the game
        fresh = phones[2].context.new_page()
        check.watch(fresh, 'Kylie (new tab)')
        fresh.goto(url + '/player')
        fresh.fill('#join-form input', 'Kyles')
        fresh.click('#join-form button')
        time.sleep(0.4)
        phones[2].close()
        phones[2] = fresh
        time.sleep(0.6)
        names = sorted(p.name for p in game.players.values())
        assert names == ['Davo', 'Kyles', 'Shazza'], f'phantom player left behind: {names}'
        # ...and then changes her name back with the header's Change name button
        tap(fresh, '[data-act=rename-open]')
        fresh.fill('#rename-input', 'Kylie')
        check.shot(fresh, 'phone-rename')
        tap(fresh, '[data-act=rename-save]')
        time.sleep(0.3)
        assert sorted(p.name for p in game.players.values()) == sorted(NAMES), 'rename failed'
        assert 'Kylie' in fresh.inner_text('#me'), 'phone header still shows the old name'
        assert fresh.locator('#rename-input').count() == 0, 'rename sheet did not close'

        # Character creation: draw a few pixels, then spend points (different builds)
        builds = [{'spd': 6, 'str': 2, 'mcr': 2}, {'str': 5, 'mcr': 5}, {'mcr': 4, 'spd': 3}]
        for i, page in enumerate(phones):
            box = page.locator('#pad canvas').bounding_box()
            for k in range(6):
                page.mouse.click(box['x'] + box['width'] * (0.3 + 0.07 * k), box['y'] + box['height'] * (0.4 + 0.02 * i))
            page.click('#head-done')
            time.sleep(0.3)
            for stat, n in builds[i].items():
                for _ in range(n):
                    page.locator(f'[data-act=stat][data-stat={stat}][data-dir="1"]').click()
            if i == 0:
                check.shot(page, 'phone-stats')
            page.click('[data-act=submit-stats]')
            time.sleep(0.3)
        assert game.lobby_ready(), 'everyone finished but lobby is not ready'
        assert game.vip().name == NAMES[0], 'first finisher should be the VIP'
        check.shot(host, 'host-lobby')
        check.shot(phones[0], 'phone-vip-lobby')
        assert phones[0].locator('[data-act=start]').count() == 1, 'VIP has no Start button'
        assert phones[1].locator('[data-act=start]').count() == 0, 'non-VIP has a Start button'

        # VIP starts from their phone
        tap(phones[0], '[data-act=start]')
        wait_phase(game, 'map')
        use_design_doc_route(game)
        # Shazza leads and Kylie trails, so the Koala never visits Shazza and always visits Kylie
        with game.lock:
            for name, cash in zip(NAMES, (150, 100, 60)):
                game.player_by_name(name).private['cash'] = cash
        check.shot(host, 'host-map')
        wait_phase(game, 'bet')
        check.shot(host, 'host-odds')
        assert phones[0].locator('.psst').count() == 0, 'the leader got a Shady Koala visit'
        assert phones[2].locator('.psst').count() == 1, 'last place got no Shady Koala visit'
        visited = [phones[2]]
        check.shot(visited[0], 'phone-psst')
        tap(visited[0], '.psst')
        check.shot(visited[0], 'phone-koala')
        assert '$Dd 9' in visited[0].inner_text('.sheet'), 'an accident should cost 15% of $Dd 60'
        tap(visited[0], '[data-act=koala-item][data-item=juice]')
        tap(visited[0], '[data-act=koala-target]', 0)   # Shazza gets juiced...
        tap(visited[0], '[data-act=koala-item][data-item=accident]')
        tap(visited[0], '[data-act=koala-target]', 1)   # ...and Davo has an accident
        tap(visited[0], '[data-act=koala-exit]')
        assert 'Juice' in visited[0].inner_text('#screen'), 'koala purchase not on the slip'
        if phones[1].locator('.psst').count():   # Davo, in the middle, gets a coin flip
            tap(phones[1], '.psst')
            tap(phones[1], '[data-act=koala-exit]')
        for i, page in enumerate(phones):
            if i == 2:
                tap(page, '[data-act=step-size][data-step="1"]')   # bet in ones
            for _ in range(i + 1):
                page.locator('[data-act=bet][data-dir="1"]').nth(i).click()
            if i == 1:
                check.shot(page, 'phone-slip')
            tap(page, '[data-act=confirm-bets]')
        bets = [game.player_by_name(n).private.get('bets') for n in NAMES]
        ids = [game.player_by_name(n).id for n in NAMES]
        assert bets == [{ids[0]: 10}, {ids[1]: 20}, {ids[2]: 3}], f'step buttons bet wrong: {bets}'
        # The accident makes the breaking news; the juice pops up as a balloon at the start
        wait_phase(game, 'news')
        time.sleep(R.NEWS_LEAD_SECONDS + 0.3)
        news = host.inner_text('#above')
        assert 'BREAKING NEWS' in news.upper() and 'Davo' in news, f'no accident headline: {news}'
        assert 'Kylie' not in news, 'the news gave away who paid for the accident'
        check.shot(host, 'host-news')
        assert 'Breaking news' in phones[0].inner_text('#screen'), 'phone not pointing at the news'
        wait_phase(game, 'perform')
        assert 'Your bets' in phones[1].inner_text('#screen'), 'phone hides its bets during the race'
        assert 'Juice' in visited[0].inner_text('#screen'), 'koala purchase hidden during the race'
        check.shot(phones[1], 'phone-watch-bets')
        time.sleep(1.5)
        check.shot(host, 'host-balloons')
        time.sleep(R.balloon_seconds(1) + 4)
        check.shot(host, 'host-race')
        wait_phase(game, 'payout')
        check.shot(host, 'host-payout')
        check.shot(phones[0], 'phone-payout')
        for page in phones:
            tap(page, '[data-act=continue]')

        # Mother's Purse
        wait_phase(game, 'purse')
        check.shot(host, 'host-purse')
        for page in phones:
            if page.locator('[data-act=pick]:not([disabled])').count():
                tap(page, '[data-act=pick][data-value=dont]')
                tap(page, '[data-act=confirm-pick]')
        check.shot(phones[0], 'phone-purse')
        wait_phase(game, 'purse_result')
        check.shot(host, 'host-purse-result')

        # The host timer: red with one beep as it passes rules.TIMER_WARNING_SECONDS
        host.mouse.click(5, 300)   # browsers only allow sound once the page has been clicked
        host.evaluate("""() => { window.beeps = 0; const beep = APGE.sound.beep;
                                 APGE.sound.beep = o => { window.beeps++; return beep(o); }; }""")
        with game.lock:
            game.start_timer(R.TIMER_WARNING_SECONDS + 1.5)
            game._flush()
        time.sleep(1)
        assert 'apge-urgent' not in host.get_attribute('#timer', 'class'), 'timer red too early'
        time.sleep(2.5)
        assert 'apge-urgent' in host.get_attribute('#timer', 'class'), 'timer not red at 10s left'
        time.sleep(1)
        assert host.evaluate('window.beeps') == 1, 'expected exactly one beep'
        assert host.locator('#sound').is_hidden(), 'sound hint still up after a click'
        check.shot(host, 'host-timer-warning')

        # A loan: always on offer, a fixed amount, once per betting event
        jump_to(game, STOP['fist_fight'])   # elimination animation, zone 1
        wait_phase(game, 'bet')
        shark_phone = phones[1]
        if shark_phone.locator('.psst').count():
            tap(shark_phone, '.psst')
            tap(shark_phone, '[data-act=koala-exit]')
        tap(shark_phone, '[data-act=loan-open]')
        check.shot(shark_phone, 'phone-loanshark')
        tap(shark_phone, '[data-act=borrow]')
        assert game.players[game.finish_order[1]].private['borrowed'] == R.LOAN_AMOUNT, 'loan not recorded'
        assert shark_phone.locator('[data-act=loan-open]').count() == 0, 'second loan offered this event'
        skip(game)
        wait_phase(game, 'perform')
        time.sleep(5)
        check.shot(host, 'host-fistfight')

        # Trading Card Auction
        jump_to(game, STOP['card_auction'])
        wait_phase(game, 'auction')
        assert '2,500' in phones[0].inner_text('#screen'), 'no card pack value estimate'
        tap(phones[0], '[data-act=place-bid]')
        tap(phones[2], '[data-act=place-bid]')
        check.shot(host, 'host-auction')
        check.shot(phones[0], 'phone-auction')
        skip(game)
        wait_phase(game, 'auction_open')
        time.sleep(9)
        check.shot(host, 'host-cards')
        wait_phase(game, 'auction_result')
        check.shot(host, 'host-auction-result')

        # Sand curling (turns animation), zone 2 with a frisk
        jump_to(game, STOP['sand_curling'])
        wait_phase(game, 'bet')
        for page in phones:
            if page.locator('.psst').count():
                tap(page, '.psst')
                tap(page, '[data-act=koala-item][data-item=bribe]')
                tap(page, '[data-act=koala-target]', 0)
                tap(page, '[data-act=koala-exit]')
            tap(page, '[data-act=confirm-bets]')
        wait_phase(game, 'frisk')
        check.shot(host, 'host-frisk')
        wait_phase(game, 'perform')
        # A frame can arrive with t a hair below zero; that used to throw and blank the turns
        # animation for the whole event (Sand Curling "sometimes" missing)
        host.evaluate("""() => { const c = document.createElement('canvas').getContext('2d');
                                 Stage.eventScene(apge.view)(c, 800, 450, -0.004); }""")
        time.sleep(4.5)
        check.shot(host, 'host-turns')

        # Case or No Case
        jump_to(game, STOP['case_or_no_case'])
        wait_phase(game, 'case')
        holder = game.case_secret['holder']
        for page, name in zip(phones, NAMES):
            if game.player_by_name(name).id == holder:
                check.shot(page, 'phone-case-holder')
            else:
                tap(page, '[data-act=pick][data-value=case]')
                tap(page, '[data-act=confirm-pick]')
        check.shot(host, 'host-case')
        wait_phase(game, 'case_result')
        check.shot(host, 'host-case-result')

        # Ticket Scalping, one round
        jump_to(game, STOP['ticket_scalping'])
        wait_phase(game, 'scalp')
        check.shot(host, 'host-scalp')
        face = game.public['scalp']['face']
        for i, page in enumerate(phones):
            if i == 2:
                tap(page, '[data-act=step-size][data-kind=scalp][data-step="100"]')
            for _ in range(i):
                tap(page, '[data-act=price][data-dir="-1"]')
            tap(page, '[data-act=submit-price]')
        asks = [game.player_by_name(n).private.get('ask') for n in NAMES]
        lowest = R.MONEY_STEP   # a big step down stops at the lowest ask instead of going under
        assert asks == [face, face - 10, max(lowest, face - 200)], f'scalp step buttons asked wrong: {asks}'
        wait_phase(game, 'scalp_result')
        check.shot(host, 'host-scalp-result')

        # Holding a Note (elimination with notes), then the season finale
        jump_to(game, STOP['note'])
        wait_phase(game, 'bet')
        skip(game)
        wait_phase(game, 'frisk')
        check.shot(host, 'host-frisk-zone3')
        wait_phase(game, 'perform')
        time.sleep(5)
        check.shot(host, 'host-note')
        jump_to(game, len(R.SEASON_SHAPE))
        wait_phase(game, 'game_over')
        time.sleep(R.FINAL_REVEAL_SECONDS * (len(NAMES) + 1) + 1)
        check.shot(host, 'host-final-loansharks')
        check.shot(phones[0], 'phone-final-wait')
        assert 'place' not in phones[0].inner_text('#screen'), 'phone spoiled the final reveal'
        time.sleep(R.FINAL_REVEAL_SECONDS)
        check.shot(host, 'host-final')
        check.shot(phones[0], 'phone-final')
        assert phones[0].locator('[data-act=reset]').count() == 1, 'VIP has no One more game button'

        # One more game: back to skill points with the same heads
        tap(phones[0], '[data-act=reset]')
        time.sleep(0.6)
        assert game.phase == 'lobby'
        assert phones[1].locator('[data-act=submit-stats]').count() == 1, 'not back on skill points'
        check.shot(phones[1], 'phone-one-more-game')
        browser.close()

    httpd.shutdown()
    if check.errors:
        print('JavaScript errors:\n  ' + '\n  '.join(check.errors))
        return False
    print(f'Browser check passed ({check.count} screenshots{" in " + shots if shots else ""})')
    return True


if __name__ == '__main__':
    out = sys.argv[sys.argv.index('--shots') + 1] if '--shots' in sys.argv else None
    sys.exit(0 if main(out) else 1)
