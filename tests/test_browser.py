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
        check.shot(host, 'host-map')
        wait_phase(game, 'bet')
        check.shot(host, 'host-odds')
        visited = [p for p in phones if p.locator('.psst').count()]
        assert len(visited) == R.ZONES[1]['koala_visits'], 'zone 1 should send exactly one Psst'
        check.shot(visited[0], 'phone-psst')
        tap(visited[0], '.psst')
        check.shot(visited[0], 'phone-koala')
        tap(visited[0], '[data-act=koala-item][data-item=hgh]')
        tap(visited[0], '[data-act=koala-target]', 0)
        tap(visited[0], '[data-act=koala-exit]')
        for i, page in enumerate(phones):
            for _ in range(i + 1):
                page.locator('[data-act=bet][data-dir="1"]').nth(i).click()
            if i == 1:
                check.shot(page, 'phone-slip')
            tap(page, '[data-act=confirm-bets]')
        wait_phase(game, 'perform')
        time.sleep(5.5)
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

        # A loan: spend down below starting cash, then visit the loansharks next betting round
        with game.lock:
            game.players[game.finish_order[1]].private['cash'] = 40
            game.mark_dirty()
            game._flush()
        jump_to(game, 3)   # Fist Fight (elimination animation), zone 1
        wait_phase(game, 'bet')
        shark_phone = phones[1]
        if shark_phone.locator('.psst').count():
            tap(shark_phone, '.psst')
            tap(shark_phone, '[data-act=koala-exit]')
        tap(shark_phone, '[data-act=loan-open]')
        tap(shark_phone, '[data-act=loan][data-dir="1"]')
        check.shot(shark_phone, 'phone-loanshark')
        tap(shark_phone, '[data-act=borrow]')
        assert game.players[game.finish_order[1]].private['borrowed'] == 20, 'loan not recorded'
        skip(game)
        wait_phase(game, 'perform')
        time.sleep(5)
        check.shot(host, 'host-fistfight')

        # Trading Card Auction
        jump_to(game, 4)
        wait_phase(game, 'auction')
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
        jump_to(game, 5)
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
        time.sleep(4.5)
        check.shot(host, 'host-turns')

        # Case or No Case
        jump_to(game, 7)
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
        jump_to(game, 10)
        wait_phase(game, 'scalp')
        check.shot(host, 'host-scalp')
        for i, page in enumerate(phones):
            for _ in range(i):
                tap(page, '[data-act=price][data-dir="-1"]')
            tap(page, '[data-act=submit-price]')
        wait_phase(game, 'scalp_result')
        check.shot(host, 'host-scalp-result')

        # Holding a Note (elimination with notes), then the season finale
        jump_to(game, 12)
        wait_phase(game, 'bet')
        skip(game)
        wait_phase(game, 'frisk')
        check.shot(host, 'host-frisk-zone3')
        wait_phase(game, 'perform')
        time.sleep(5)
        check.shot(host, 'host-note')
        jump_to(game, len(R.SEASON))
        wait_phase(game, 'game_over')
        time.sleep(R.FINAL_REVEAL_SECONDS * (len(NAMES) + 1) + 1)
        check.shot(host, 'host-final-loansharks')
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
