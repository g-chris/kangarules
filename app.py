"""Run Down Under Gambler's Sweat It Out! Derby '27: python app.py"""
import os

from flask import render_template

from apge import PartyServer

import rules
from game import Derby

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def make_server(game=None, **kwargs):
    server = PartyServer(game or Derby(), base_dir=BASE_DIR, **kwargs)

    # The pixel art tool: same editor the players draw their heads with, for making game art
    @server.app.route('/art')
    def art_tool():
        return render_template('art.html', title=server.game.title, palette=rules.PALETTE,
                               pixel_chars=rules.PIXEL_CHARS, head_grid=rules.HEAD_GRID)

    return server


if __name__ == '__main__':
    make_server().run()
