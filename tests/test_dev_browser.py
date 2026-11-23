"""
Browser check for Developer Mode: Playwright draws in the art editor, checks the live preview
shows the unsaved drawing, then uses Save, Save As (into another asset), New blank, Use in
game, Resize and Import PNG, and loads every sample screen, failing on any JavaScript error.
Art is saved to a temporary folder, never the game's art/.

    pip install playwright && python -m playwright install chromium
    python tests/test_dev_browser.py [--shots DIR]
"""
import io
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from apge.testing import free_port  # noqa: E402

from app import make_server as make_party_server  # noqa: E402
from test_browser import PHONE, TV, Check  # noqa: E402

DESK = {'width': 1500, 'height': 950}


def stroke(page, color):
    """Draw a diagonal line across the editor canvas in a palette colour."""
    page.click(f'.swatch[data-color="{color}"]')
    page.click('[data-tool="pencil"]')
    box = page.locator('.pad-canvas').bounding_box()
    page.mouse.move(box['x'] + 4, box['y'] + 4)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] - 4, box['y'] + box['height'] - 4, steps=10)
    page.mouse.up()


def wait_for(fn, what, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return
        time.sleep(0.1)
    raise AssertionError(f'timed out waiting for {what}')


def dialog_ok(page, dialog):
    page.click(f'#{dialog} button[value=ok]')
    time.sleep(0.8)


def main(shots=None):
    if shots:
        os.makedirs(shots, exist_ok=True)
    check = Check(shots)
    party = make_party_server(port=free_port(), dev=True)
    art_dir = tempfile.mkdtemp(prefix='derby-art-')
    party.art.root = art_dir
    art = party.art
    httpd = make_server('127.0.0.1', party.port, party.app, threaded=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{party.port}'

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=DESK)
        check.watch(page, 'dev')
        page.on('dialog', lambda d: d.accept())   # "throw away unsaved changes?" confirms

        # Columns: category -> art -> a blank new version at the asset's starting size
        page.goto(url + '/dev')
        page.click('[data-category="Characters"]')
        page.click('[data-asset="agent_kevin"]')
        page.wait_for_selector('.pad-canvas')
        assert page.locator('#col-versions li.unsaved').count() == 1, 'no unsaved new version listed'
        assert '32×48' in page.inner_text('.ws-version'), 'blank version is not the asset size'

        # The live preview (the real frisk screen) shows the drawing before it's saved
        stroke(page, 3)
        frame = page.frame_locator('#previews iframe').first
        wait_for(lambda: (frame.locator('img.art-img').count() and
                          frame.locator('img.art-img').get_attribute('src').startswith('data:')),
                 'the preview to show the unsaved drawing')
        check.shot(page, 'dev-drawing')

        # Save: first version, straight into the game since nothing else is
        page.click('[data-do=save]')
        wait_for(lambda: art.selected('agent_kevin') == 'v1', 'agent v1 in game')
        assert page.locator('[data-do=save]').is_disabled(), 'Save enabled with nothing to save'

        # Save again overwrites the same version
        stroke(page, 5)
        page.click('[data-do=save]')
        time.sleep(0.8)
        assert art.version_ids('agent_kevin') == ['v1'], art.version_ids('agent_kevin')
        assert '5' in ''.join(art.read_version('agent_kevin', 'v1')['frames'][0])

        # Save As into another asset: the koala starts from the agent's drawing
        page.click('[data-do=save-as]')
        page.select_option('#dlg-save-as select[name=asset]', 'shady_koala')
        assert page.is_checked('#dlg-save-as input[name=select]'), 'Use in game should default on for empty art'
        page.fill('#dlg-save-as input[name=label]', 'from the agent')
        dialog_ok(page, 'dlg-save-as')
        koala = art.read_version('shady_koala', 'v1')
        assert (koala['from'], koala['label'], art.selected('shady_koala')) == ('agent_kevin/v1', 'from the agent', 'v1'), koala
        # (location.href, not page.url: Playwright misses some hash-only location.replace calls)
        wait_for(lambda: 'shady_koala/v1' in page.evaluate('location.href'), 'Save As to open the new version')

        # New blank + Use in game; resize the canvas
        page.goto(url + '/dev#art/agent_kevin')
        page.wait_for_selector('.pad-canvas')
        page.click('[data-do=new]')
        stroke(page, 4)
        page.click('[data-do=resize]')
        page.fill('#dlg-resize input[name=width]', '40')
        page.select_option('#dlg-resize select[name=anchor]', '0.5,1')
        dialog_ok(page, 'dlg-resize')
        assert '40×48' in page.inner_text('.ws-version')
        page.click('[data-do=save]')
        wait_for(lambda: art.version_ids('agent_kevin') == ['v1', 'v2'], 'agent v2')
        assert art.selected('agent_kevin') == 'v1', 'a second version should not replace the one in game'
        assert art.read_version('agent_kevin', 'v2')['width'] == 40
        page.click('[data-do=select]')
        wait_for(lambda: art.selected('agent_kevin') == 'v2', 'Use in game')

        # Import a PNG, then Save As turns it into editable pixel art in the palette
        buf = io.BytesIO()
        Image.new('RGBA', (12, 10), (250, 210, 5, 255)).save(buf, format='PNG')
        page.set_input_files('#import', files=[{'name': 'sketch.png', 'mimeType': 'image/png', 'buffer': buf.getvalue()}])
        wait_for(lambda: art.version_ids('agent_kevin') == ['v1', 'v2', 'v3'], 'imported v3')
        page.wait_for_selector('.png-view img')
        assert page.locator('[data-do=save]').is_disabled(), 'imported pictures must not be overwritable'
        check.shot(page, 'dev-imported')
        page.click('[data-do=save-as]')
        page.uncheck('#dlg-save-as input[name=select]')
        dialog_ok(page, 'dlg-save-as')
        v4 = art.read_version('agent_kevin', 'v4')
        yellow = art.chars[art.palette.index('#ffdc00')]
        assert v4['kind'] == 'pixel' and set(''.join(v4['frames'][0])) == {yellow}, v4
        assert art.selected('agent_kevin') == 'v2'

        # Every page now gets the saved art; the real host page draws it on the frisk screen
        host = browser.new_page(viewport=TV)
        check.watch(host, 'frisk')
        host.goto(url + '/?apge-preview=frisk')
        host.wait_for_selector('img.art-img')
        assert host.locator('img.art-img').get_attribute('src').startswith('/apge-art/agent_kevin.png'), 'frisk not using saved art'
        check.shot(host, 'frisk-with-art')
        host.close()

        # Screens tab, then every sample screen on its own, at its real size
        page.click('[data-tab=screens]')
        assert page.locator('#gallery figure').count() == len(party.dev.screens)
        check.shot(page, 'dev-screens')
        for screen in party.dev.screens.values():
            p = browser.new_page(viewport=TV if screen.role == 'host' else PHONE)
            check.watch(p, screen.id)
            p.goto(url + screen.to_json()['url'])
            time.sleep(0.6)
            if p.locator('.apge-preview-error').count():
                check.errors.append(f'{screen.id}: ' + p.inner_text('.apge-preview-error')[:300])
            check.shot(p, 'screen-' + screen.id)
            p.close()
        browser.close()

    httpd.shutdown()
    with open(os.path.join(art_dir, 'agent_kevin', 'asset.json')) as f:
        assert json.load(f) == {'selected': 'v2'}
    if check.errors:
        print('FAILED - browser errors:')
        for e in check.errors:
            print('  ' + e)
        sys.exit(1)
    print(f'OK - Developer Mode works; {len(party.dev.screens)} sample screens, no JavaScript errors'
          + (f'; {check.count} screenshots in {shots}' if shots else ''))


if __name__ == '__main__':
    shots_dir = sys.argv[sys.argv.index('--shots') + 1] if '--shots' in sys.argv else None
    main(shots_dir)
