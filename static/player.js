// Phone screen. Everything a player hasn't sent yet (bet slip, skill points, a picked
// option) lives in `draft`, so state updates re-render freely without losing input.
const apge = APGE.connect();
const {esc, head, dd, signed, byId, winnings, finalReveal, art, stopTitle} = Common;
const $ = id => document.getElementById(id);

let pad = null;
let draft = {key: null};
let moneyStep = null;     // the +/- size picked on the betting slip / auction; kept between rounds
let wakeTimer = null;

/** Re-render at a set time (a reveal that happens without a state update). */
function wakeIn(ms) {
    clearTimeout(wakeTimer);
    wakeTimer = setTimeout(rerender, ms);
}

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
const sum = obj => Object.values(obj).reduce((a, b) => a + b, 0);

apge.mountJoinForm('join-form', {placeholder: 'Your name', button: 'Join'});

function draftFor(view) {
    const key = [view.phase, view.data.stop, (view.data.scalp || {}).round].join('|');
    if (draft.key !== key) draft = {key: key, redraw: draft.redraw};
    return draft;
}

function show(id) {
    ['join', 'draw', 'screen'].forEach(s => $(s).classList.toggle('apge-active', s === id));
}

function rerender() { if (apge.view) render(apge.view); }

/** Send an action; re-render on success (the state push follows, but drafts may have changed). */
function send(name, data, after) {
    return apge.action(name, data).then(ack => {
        if (ack.ok && after) after();
        rerender();
        return ack;
    });
}

const stepper = (act, value, label, extra) =>
    `<div class="stepper"><button class="step" data-act="${act}" data-dir="-1" ${extra || ''}>−</button>` +
    `<span class="value">${label !== undefined ? label : value}</span>` +
    `<button class="step" data-act="${act}" data-dir="1" ${extra || ''}>+</button></div>`;

/** The +/- size buttons under a money counter. */
function stepPicker(rules) {
    if (!rules.bet_steps.includes(moneyStep)) moneyStep = rules.money_step;
    return '<div class="steps"><span class="dim">+/− by</span>' + rules.bet_steps.map(s =>
        `<button class="stepsize ${s === moneyStep ? 'on' : ''}" data-act="step-size" data-step="${s}">${dd(s)}</button>`).join('') + '</div>';
}

const nameOf = (view, id) => (byId(view)[id] || {name: '?'}).name;

/** What I've bet on this event, so I know who to cheer for. */
function myBets(view, me) {
    const odds = view.data.odds, placed = Object.entries(me.private.bets || {});
    if (!placed.length) return '<p>No bets this time. Very wise. Or very boring.</p>';
    return '<h3>Your bets</h3><ul class="choices mine">' + placed.map(([pid, amt]) =>
        `<li>${head(byId(view)[pid], view.rules, 28)} <b>${esc(nameOf(view, pid))}</b>: ${dd(amt)} at ${odds[pid].label}` +
        ` <span class="dim">→ wins ${dd(winnings(amt, odds[pid], view.rules))}</span></li>`).join('') + '</ul>';
}

/** What I bought from the Shady Koala this event (confiscated if I was frisked). */
function myKoala(view, me) {
    const koala = me.private.koala, bought = koala ? Object.entries(koala.bought) : [];
    if (!bought.length) return '';
    const frisk = (view.data.frisks || []).find(f => f.id === me.id);
    const caught = frisk && frisk.caught.length ? ' <span class="red">(confiscated)</span>' : '';
    const items = view.rules.koala_items;
    return '<h3>Your Shady Koala purchases</h3><ul class="choices mine">' + bought.map(([id, target]) =>
        `<li><b>${esc(items.find(i => i.id === id).name)}</b> → ${esc(nameOf(view, target))}${caught}</li>`).join('') + '</ul>';
}

const watchMyRound = (view, me, line) => watch(view, line) + `<div class="center">${myBets(view, me)}${myKoala(view, me)}</div>`;

const continueButton = me => me.ready
    ? '<p class="done">Waiting for everyone else...</p>'
    : '<button class="apge-button wide" data-act="continue">Continue</button>';

const watch = (view, line) => `<div class="center">${art('big_screen', 'small')}
    <h2>${line || 'Watch the big screen!'}</h2><p class="dim">${stopTitle(view.data.season[view.data.stop])}</p></div>`;

// ---- lobby: draw a head, spend skill points, wait for the host ---------------------------

function lobby(view, me, d) {
    const rules = view.rules;
    if (!me.head || draft.redraw) {
        show('draw');
        if (!pad) {
            pad = PixelArt.mountPad($('pad'), {grid: rules.head_grid, palette: rules.palette,
                                                chars: rules.pixel_chars, value: me.head});
        }
        return null;
    }
    if (!me.character_done) {
        d.stats = d.stats || {str: 0, spd: 0, mcr: 0};
        const left = rules.skill_points - Object.values(d.stats).reduce((a, b) => a + b, 0);
        return `<div class="center">${head(me, rules, 96)}<h2>Spend your skill points</h2>
            <p class="big">Points left: <b class="gold">${left}</b></p>
            ${rules.stats.map(s => `<div class="statrow"><span>${s.label} (${s.id.toUpperCase()})</span>
                ${stepper('stat', d.stats[s.id], undefined, `data-stat="${s.id}"`)}</div>`).join('')}
            <p class="dim">Nobody else will ever see these. Lie about them freely.</p>
            <button class="apge-button wide" data-act="submit-stats">Submit</button>
            <button class="link" data-act="redraw">Redraw my head</button></div>`;
    }
    const vip = view.players.find(p => p.id === view.vip_id);
    const waiting = view.players.filter(p => !p.character_done).map(p => esc(p.name));
    if (apge.isVip()) {
        return `<div class="center">${head(me, rules, 96)}<h2>You're the HOST</h2>
            <p>${view.players.length} players joined.` + (waiting.length ? ` Still creating: ${waiting.join(', ')}` : ' Everyone is ready!') + `</p>
            <button class="apge-button wide" data-act="start" ${view.players.length < view.min_players ? 'disabled' : ''}>Start Game</button>
            ${view.players.length < view.min_players ? `<p class="dim">Need at least ${view.min_players} players.</p>` : ''}</div>`;
    }
    return `<div class="center">${head(me, rules, 96)}<h2>You're in!</h2>
        <p>${vip ? `Waiting for ${esc(vip.name)} (the HOST) to start the game...` : 'Waiting for the game to start...'}</p></div>`;
}

$('head-done').addEventListener('click', () => {
    const art = pad.get();
    if (!art.replace(/\./g, '') && !confirm('Go with a blank head?')) return;
    send('submit_head', {head: art}, () => { draft.redraw = false; });
});

// ---- gambling: the betting slip --------------------------------------------------------------

function bet(view, me, d) {
    const rules = view.rules, odds = view.data.odds, priv = me.private;
    d.bets = d.bets || {};
    const ev = view.data.event;
    if (me.done) {
        return `<div class="center"><h2>Bets locked in!</h2>${myBets(view, me)}${myKoala(view, me)}
            <p class="dim">Watch the big screen...</p></div>`;
    }
    // Koala purchases can shrink your cash after you've filled in the slip: trim the bets to fit
    let excess = sum(d.bets) - priv.cash;
    Object.keys(d.bets).forEach(k => {
        const cut = Math.min(Math.max(0, excess), d.bets[k]);
        d.bets[k] -= cut;
        excess -= cut;
    });
    const total = sum(d.bets);
    const lines = view.players.map(p => {
        const stake = d.bets[p.id] || 0;
        return `<div class="betline">${head(p, rules, 44)}<div class="who"><b>${esc(p.name)}</b><small>${odds[p.id].label}</small></div>
            ${stepper('bet', stake, dd(stake), `data-id="${p.id}"`)}
            <div class="help">${stake ? `(On win: ${dd(winnings(stake, odds[p.id], rules))})` : ''}</div></div>`;
    }).join('');
    const canBorrow = priv.cash < rules.starting_cash;
    const koala = myKoala(view, me);
    return `<h2 class="center">${esc(ev.name)}</h2><p class="center dim">${esc(ev.venue)}</p>
        <div class="slip">${lines}</div>
        ${stepPicker(rules)}
        <p class="center">Betting ${dd(total)} of ${dd(priv.cash)}</p>
        ${koala ? `<div class="center">${koala}</div>` : ''}
        <div class="loan-slot">${canBorrow ? '<button class="apge-button wide shark" data-act="loan-open">LOANSHARK</button>' : ''}</div>
        <button class="apge-button wide" data-act="confirm-bets">Confirm</button>`;
}

function betOverlay(view, me, d) {
    const rules = view.rules, priv = me.private, koala = priv.koala;
    if (me.done) return '';
    if (koala && koala.state === 'pending') {
        return '<button class="psst" data-act="koala-open">Psst!</button>';
    }
    if (koala && koala.state === 'open') {
        const players = byId(view);
        if (d.koalaItem) {
            const item = rules.koala_items.find(i => i.id === d.koalaItem);
            return `<div class="sheet">${art('shady_koala', 'small')}<h2>${esc(item.name)}: who?</h2>
                ${view.players.map(p => `<button class="pick" data-act="koala-target" data-id="${p.id}">${head(p, rules, 32)} ${esc(p.name)}</button>`).join('')}
                <button class="link" data-act="koala-back">Never mind</button></div>`;
        }
        return `<div class="sheet">${art('shady_koala')}<h2>"G'day. Need anything?"</h2>
            <p>You have ${dd(priv.cash)}</p>
            ${rules.koala_items.map(i => {
                const bought = koala.bought[i.id];
                return `<button class="item" data-act="koala-item" data-item="${i.id}" ${bought || i.price > priv.cash ? 'disabled' : ''}>
                    <b>${esc(i.name)}</b> · ${dd(i.price)}<br><small>${bought ? 'Bought → ' + esc(players[bought].name) : esc(i.effect)}</small></button>`;
            }).join('')}
            <button class="apge-button wide" data-act="koala-exit">EXIT</button></div>`;
    }
    if (d.loanOpen) {
        d.loan = d.loan || rules.loan_min;
        return `<div class="sheet">${art('loansharks')}<h2>"Short on cash, mate?"</h2>
            ${stepper('loan', d.loan, dd(d.loan))}
            <p class="red big">Shrimp and Barbie expect DOUBLE back at the end of the season: you'll owe ${dd(d.loan * rules.loan_multiplier)}.</p>
            <button class="apge-button wide shark" data-act="borrow">Borrow ${dd(d.loan)}</button>
            <button class="link" data-act="loan-close">Back to my betting slip</button></div>`;
    }
    return '';
}

// ---- specials ----------------------------------------------------------------------------------

function twoChoice(d, options, locked, help) {
    return options.map(([value, label]) => `<button class="choice ${d.pick === value ? 'on' : ''}" data-act="pick" data-value="${value}" ${locked ? 'disabled' : ''}>${label}</button>`).join('') +
        `<button class="apge-button wide ${locked ? 'on' : ''}" data-act="confirm-pick" ${locked || !d.pick ? 'disabled' : ''}>Confirm</button>` +
        (help ? `<p class="dim">${help}</p>` : '');
}

function purse(view, me, d) {
    const priv = me.private;
    if (priv.forced) {
        d.pick = 'steal';
        return `<div class="center"><h2>Mother's Purse</h2>${twoChoice(d, [['steal', 'STEAL'], ['dont', "DON'T STEAL"]], true,
            'Moral Courage stat too low to choose')}</div>`;
    }
    if (me.done) return `<div class="center"><h2>Mother's Purse</h2><p class="big">You chose ${priv.choice === 'steal' ? 'STEAL' : "DON'T STEAL"}.</p><p class="done">Locked in!</p></div>`;
    return `<div class="center"><h2>Mother's Purse</h2>${twoChoice(d, [['steal', 'STEAL'], ['dont', "DON'T STEAL"]], false)}</div>`;
}

function auction(view, me, d) {
    const a = view.data.auction, rules = view.rules, cash = me.private.cash;
    const lowest = a.leader ? a.high_bid + rules.money_step : rules.auction_opening_bid;
    if (!d.bid || d.bid < lowest) d.bid = lowest;
    const leading = a.leader === me.id;
    const [lo, hi] = rules.card_pack_value;
    return `<div class="center"><h2>Card Pack Auction</h2>
        <p>Estimated value: <b class="gold">${dd(lo)} – ${dd(hi)}</b></p>
        <p class="big">High bid: <b class="gold">${dd(a.high_bid || rules.auction_opening_bid)}</b>${a.leader_name ? ' by ' + esc(a.leader_name) : ''}</p>
        ${leading ? '<p class="done big">You\'re winning!</p>' : `
        ${stepper('bid', d.bid, dd(d.bid))}
        ${stepPicker(rules)}
        <button class="apge-button wide" data-act="place-bid" ${d.bid > cash ? 'disabled' : ''}>Bid ${dd(d.bid)}</button>
        ${lowest > cash ? '<p class="dim">You can\'t afford to raise.</p>' : ''}`}
        <p class="dim">You have ${dd(cash)}</p></div>`;
}

function caseScreen(view, me, d) {
    const c = view.data.case, priv = me.private;
    if (priv.case_value !== undefined) {
        return `<div class="center">${art('briefcase')}<h2>You have the case</h2>
            <p class="huge gold">${dd(priv.case_value)}</p>
            <p>Tell them it's worth whatever you like.</p></div>`;
    }
    if (me.done) return `<div class="center"><h2>Case or No Case</h2><p class="big">You voted for ${priv.vote === 'case' ? 'The CASE' : 'The CASH'}.</p><p class="done">Locked in!</p></div>`;
    return `<div class="center"><h2>${esc(c.holder_name)} has the case</h2>
        <p>Split the CASE (they get ${dd(c.cash)}) or split the ${dd(c.cash)} CASH (they get the case)?</p>
        ${twoChoice(d, [['case', 'The CASE'], ['cash', 'The CASH']], false)}</div>`;
}

function scalp(view, me, d) {
    const s = view.data.scalp, rules = view.rules;
    if (me.done) return `<div class="center"><h2>Ticket Scalping</h2><p class="big">Your price: ${dd(me.private.ask)}</p><p class="done">Locked in!</p></div>`;
    if (!d.price) d.price = s.face;
    return `<div class="center"><h2>Tickets! Round ${s.round} of ${s.rounds}</h2>
        <p>Face value: <b class="gold">${dd(s.face)}</b></p>
        ${stepper('price', d.price, dd(d.price))}
        <p class="dim">Lowest price nobody else matched sells - and you pocket it.</p>
        <button class="apge-button wide" data-act="submit-price">Submit</button></div>`;
}

function payoutScreen(view, me) {
    const pay = view.data.payout, w = byId(view)[pay.winner];
    const cut = pay.winner === me.id && pay.winner_cut
        ? `<p class="big">Winner's cut of the winning bets: <b class="gold">${signed(pay.winner_cut)}</b></p>` : '';
    return result(view, me, `${esc(w ? w.name : '?')} wins!`, cut);
}

function result(view, me, title, body) {
    const last = me.private.last;
    return `<div class="center"><h2>${title}</h2>${body || ''}
        ${last !== undefined ? `<p class="huge ${last >= 0 ? 'gold' : 'red'}">${signed(last)}</p>` : ''}
        <p>You have ${dd(me.private.cash)}</p>${continueButton(me)}</div>`;
}

function final(view, me) {
    const f = view.data.final;
    // Your place would spoil the big screen's reveal: hold it until the winner is announced
    const reveal = finalReveal(view, apge.phaseStarted);
    if (reveal.beat < reveal.winner) {
        wakeIn(reveal.msToWinner + 100);
        return watch(view, 'The final results are on the big screen!');
    }
    const place = f.after.findIndex(r => r.id === me.id);
    const mine = f.after[place];
    let html = `<div class="center"><h2>Season over!</h2>` + (mine ? `<p class="big">${Common.ordinal(place + 1)} place</p>
        <p>Cash ${dd(mine.cash)} · Owed to the loansharks ${dd(mine.debt)}</p><p class="huge gold">${dd(mine.final)}</p>` : '');
    if (apge.isVip()) {
        html += `<button class="apge-button wide" data-act="reset">One more game?</button>
                 <button class="apge-button wide secondary" data-act="quit">Quit</button>`;
    }
    return html + '</div>';
}

const SCREENS = {
    map: view => watch(view, 'On the road...'),
    bet: bet,
    frisk: (view, me) => watchMyRound(view, me, 'The Kangarules Gambling Commission is frisking someone...'),
    perform: (view, me) => watchMyRound(view, me),
    payout: payoutScreen,
    purse: purse,
    purse_result: (view, me) => result(view, me, "Mother's Purse"),
    auction: auction,
    auction_open: view => watch(view, 'Opening the pack...'),
    auction_result: (view, me) => result(view, me, 'Card Pack Auction', ''),
    case: caseScreen,
    case_result: (view, me) => result(view, me, 'Case or No Case'),
    scalp: scalp,
    scalp_result: (view, me) => result(view, me, 'Ticket Scalping'),
    game_over: final,
};

// ---- buttons --------------------------------------------------------------------------------

const ACTS = {
    stat(b, view) {
        const d = draft, dir = Number(b.dataset.dir), id = b.dataset.stat;
        const used = Object.values(d.stats).reduce((a, c) => a + c, 0);
        const next = d.stats[id] + dir;
        if (next >= 0 && next <= view.rules.max_stat && (dir < 0 || used < view.rules.skill_points)) d.stats[id] = next;
    },
    'submit-stats': () => send('submit_stats', draft.stats),
    redraw: () => { draft.redraw = true; },
    start(b, view) {
        if (!view.lobby_ready && !confirm('Not everyone has finished their character. Start anyway?')) return;
        apge.start();
    },
    bet(b, view) {
        // A big step that doesn't fit stops at what's left (or at zero) instead of doing nothing
        const id = b.dataset.id, stake = draft.bets[id] || 0;
        const room = view.me.private.cash - sum(draft.bets);
        draft.bets[id] = clamp(stake + moneyStep * Number(b.dataset.dir), 0, stake + Math.max(0, room));
    },
    'step-size': b => { moneyStep = Number(b.dataset.step); },
    'confirm-bets': () => send('confirm_bets', {bets: draft.bets}),
    'loan-open': () => { draft.loanOpen = true; },
    'loan-close': () => { draft.loanOpen = false; },
    loan(b, view) {
        const next = draft.loan + view.rules.money_step * Number(b.dataset.dir);
        if (next >= view.rules.loan_min && next <= view.rules.starting_cash) draft.loan = next;
    },
    borrow: () => send('borrow', {amount: draft.loan}, () => { draft.loanOpen = false; }),
    'koala-open': () => send('koala_open', {}),
    'koala-item': b => { draft.koalaItem = b.dataset.item; },
    'koala-back': () => { draft.koalaItem = null; },
    'koala-target': b => send('koala_buy', {item: draft.koalaItem, target: b.dataset.id}, () => { draft.koalaItem = null; }),
    'koala-exit': () => send('koala_exit', {}),
    pick: b => { draft.pick = b.dataset.value; },
    'confirm-pick': (b, view) => {
        if (view.phase === 'purse') send('purse_choice', {choice: draft.pick});
        if (view.phase === 'case') send('case_vote', {vote: draft.pick});
    },
    bid(b, view) {
        const a = view.data.auction, cash = view.me.private.cash;
        const lowest = a.leader ? a.high_bid + view.rules.money_step : view.rules.auction_opening_bid;
        draft.bid = clamp(draft.bid + moneyStep * Number(b.dataset.dir), lowest, Math.max(lowest, cash));
    },
    'place-bid': () => send('bid', {amount: draft.bid}),
    price(b, view) {
        const face = view.data.scalp.face;
        const next = draft.price + view.rules.money_step * Number(b.dataset.dir);
        if (next >= view.rules.money_step && next <= face * view.rules.scalp_max_multiplier) draft.price = next;
    },
    'submit-price': () => send('scalp_ask', {price: draft.price}),
    continue: () => apge.ready().then(rerender),
    reset: () => apge.reset(),
    quit: () => { if (confirm('Quit? Everyone goes back to the join screen.')) apge.quit(); },
};

document.addEventListener('click', e => {
    const b = e.target.closest('[data-act]');
    if (!b || b.disabled || !apge.view || !apge.view.me) return;
    const fn = ACTS[b.dataset.act];
    if (fn) { fn(b, apge.view); rerender(); }
});

// ---- render ------------------------------------------------------------------------------------

function header(view) {
    const me = view && view.me;
    if (!me) { $('me').innerHTML = ''; return; }
    const cash = me.private.cash;
    $('me').innerHTML = `${head(me, view.rules, 28)}<b>${esc(me.name)}</b>` +
        (apge.isVip() ? '<span class="badge">HOST</span>' : '') +
        (cash !== undefined ? `<span class="cash">${dd(cash)}</span>` : '');
}

function render(view) {
    header(view);
    const me = view.me;
    if (!me) {
        show('join');
        $('overlay').innerHTML = '';
        return;
    }
    const d = draftFor(view);
    let html;
    if (view.phase === 'lobby') {
        html = lobby(view, me, d);
        if (html === null) { $('overlay').innerHTML = ''; return; }
    } else {
        const screen = SCREENS[view.phase];
        html = screen ? screen(view, me, d) : watch(view);
    }
    show('screen');
    $('screen').innerHTML = html;
    $('overlay').innerHTML = view.phase === 'bet' ? betOverlay(view, me, d) : '';
}

apge.on('state', render);
apge.on('kicked', () => { draft = {key: null}; });
