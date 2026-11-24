"""
Developer Mode checks: every sample screen still builds, and the art list (dev.ART), the
sample screens and the art the JS asks for all agree.

    python -m unittest tests.test_dev
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

import dev  # noqa: E402
import rules as R  # noqa: E402
from app import make_server  # noqa: E402

# How the JS names art: art('id'), art(c, 'id'), APGE.art.draw(c, 'id', ...), {art: 'id'},
# and the holo-or-plain card choice
JS_ART = re.compile(r"(?:\bart\((?:c, )?|APGE\.art\.\w+\((?:c, )?|\bart: )'([a-z0-9_]+)'")
JS_CARD = re.compile(r"\? '([a-z0-9_]+)' : '([a-z0-9_]+)'\, x")


def js_art_ids():
    found = set()
    for name in ('common.js', 'host.js', 'player.js', 'stage.js'):
        with open(os.path.join(ROOT, 'static', name), encoding='utf-8') as f:
            text = f.read()
        found.update(JS_ART.findall(text))
        for pair in JS_CARD.findall(text):
            found.update(pair)
    return found


class DevModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(dev=True)

    def test_every_sample_screen_builds(self):
        for screen_id in self.server.dev.screens:
            with self.subTest(screen_id):
                view = self.server.dev.build_view(screen_id)
                json.dumps(view)

    def test_sample_screens_show_the_phase_they_are_named_for(self):
        build = self.server.dev.build_view
        self.assertEqual(build('frisk')['phase'], 'frisk')
        self.assertEqual(build('auction-open')['phase'], 'auction_open')
        self.assertTrue(build('payout')['data']['payout']['winning_bets'])
        self.assertEqual(build('phone-koala')['me']['private']['koala']['state'], 'open')
        holder = build('phone-case-holder')
        self.assertIn('case_value', holder['me']['private'])
        for stop in dev.GAMBLES:
            self.assertEqual(build('perform-' + stop['event'])['phase'], 'perform')

    def test_every_art_preview_screen_exists(self):
        for asset in dev.ART:
            with self.subTest(asset.id):
                self.assertTrue(asset.screens, 'no screen to preview it on')
                for screen_id in asset.screens:
                    self.assertIn(screen_id, self.server.dev.screens)

    def test_the_js_only_asks_for_listed_art_and_all_listed_art_is_used(self):
        listed = {a.id for a in dev.ART}
        venues = {R.venue_art(stop['venue']) for stop in R.GAMBLE_STOPS}
        used = js_art_ids()
        self.assertEqual(used - listed, set(), 'the JS draws art dev.ART does not list')
        self.assertEqual(listed - used - venues, set(), 'dev.ART lists art nothing draws')
        self.assertEqual(venues - listed, set(), 'a venue has no art entry')

    def test_bet_view_names_its_venue_art(self):
        view = self.server.dev.build_view('bet-note')
        self.assertEqual(view['data']['event']['venue_art'], 'venue_opera_house')


if __name__ == '__main__':
    unittest.main()
