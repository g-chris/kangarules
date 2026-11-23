"""Run Down Under Gambler's Sweat It Out! Derby '27: python app.py   (art and debugging: --dev)"""
import os

from apge import PartyServer

import dev
import rules
from game import Derby

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def make_server(game=None, **kwargs):
    # Developer Mode (python app.py --dev, at /dev) edits the art in art/ and shows every screen
    return PartyServer(game or Derby(), base_dir=BASE_DIR, art=dev.ART, palette=rules.PALETTE,
                       screens=dev.SCREENS, **kwargs)


if __name__ == '__main__':
    make_server().run()
