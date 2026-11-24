# Down Under Gambler's Sweat It Out! Derby '27

An all-ages party game about betting on your mates. Make a stick-figure character, draw
their head, then bet on each other in half-time "fan games" across a season of New Zealand
and Australian sport. Bribe a koala, dodge the Kangarules Gambling Commission, borrow from
the loansharks. The player with the most Didgeridollars after the loansharks collect wins.

One computer hosts on the TV; everyone else plays on their phone's browser on the same
Wi-Fi. Built on [APGE](https://github.com/g-chris/apge).

> Draft 0.1: all the rules from the design doc's critical path work, but the art is
> placeholder boxes for now.

## Run it

```bash
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The host screen opens at http://localhost:8080. Players scan the QR code, pick a name,
draw their head and spend 10 skill points. The first player to finish is the HOST and
gets the Start button on their phone.

Until APGE v0.3.0 is tagged on GitHub, install the engine from a local checkout instead:
`pip install -e "../apge[testing]"`.

## How to play

- **Skills**: STRENGTH, SPEED and MORAL COURAGE. Nobody else sees yours. Lie freely.
- **Betting**: at each stop, everyone sees the odds (50-1 at the longest) and bets on
  whoever they like, or nobody, in steps of $Dd 1, 10 or 100. You start with $Dd 100.
  Whoever wins the event takes 10% of the winnings on every winning bet.
- **The season** is 13 stops, and the events come in a different order every game.
- **Shady Koala**: some players get a "Psst!" and can buy a Bat to Kneecaps, an HGH
  Injection or Bribe the Feds, priced at 15%, 10% and 5% of the cash you're holding. The
  Koala never visits whoever is in 1st place, always visits last place, and visits
  everyone else half the time.
- **Kangarules Gambling Commission**: from the Minor Leagues on, random players are
  frisked before each event. Everything they bought is confiscated, in front of everyone.
- **Loansharks**: want to go big? Once per betting event, Shrimp and Barbie will lend you
  $Dd 5,000. They want DOUBLE back at the end of the season.
- **Special events** between towns: Mother's Purse, a trading card auction, Case or No
  Case, and ticket scalping.

## Making art (Developer Mode)

```bash
python app.py --dev
```

This opens Developer Mode at http://localhost:8080/dev on the computer running the game
(packaged builds don't have it).

- **Art**: every picture the game needs, in columns (category, art, versions). Draw in the
  same pixel editor players use for their heads, at any canvas size, or import a PNG.
  **Save**, **Save As** (a new version, or a starting point for different art) and **Use in
  game** (which version the game shows). The live preview shows the drawing on every
  screen it appears on, before you save.
- **Screens**: every host and phone screen with sample players, for checking how things
  look without playing to that point.

Art is saved in `art/`; commit it. Anything without a version in game shows its
`[ART: ...]` placeholder.

## Files

| File | What it is |
|---|---|
| `CONVENTIONS.txt` | How we work, plus the GAME DESIGN summary and the draft decisions to confirm |
| `rules.py` | Every tunable number (STARTING_CASH, LUCK range, timers, prices...) and the rules as plain functions |
| `game.py` | Phases and actions: what happens when |
| `templates/` + `static/` | Host screen (`host.js`, `stage.js` canvas), phone (`player.js`); the pixel editor comes from APGE |
| `dev.py` | Developer Mode: the list of art the game needs, and a sample state for every screen |
| `art/` | The game's art (made in Developer Mode) |
| `tests/test_rules.py` | Unit tests for scoring, odds, the Shady Koala and specials |
| `tests/test_bots.py` | Bots play whole seasons: `python tests/test_bots.py --quick` |
| `tests/test_dev.py` | Every sample screen builds; the art list matches what the JS draws |
| `tests/test_dev_browser.py` | Playwright drives Developer Mode (draw, save, Save As, import) and loads every sample screen |
| `tests/test_browser.py` | Playwright drives the real pages: `pip install playwright && python -m playwright install chromium`, then `python tests/test_browser.py --shots shots/` |
| `ChangeLog.txt` | Version history |
