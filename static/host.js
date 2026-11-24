// Host (TV) screen. Each phase picks a layout and fills #above / the canvas / #below.
const apge = APGE.connect();
const {esc, head, dd, byId, finalReveal, art, stopTitle} = Common;

const $ = id => document.getElementById(id);
let joinUrl = '';
let revealTimer = null;

Stage.mount($('stage'));
// Red with a single beep at rules.timer_warning seconds left, while players are choosing
// (the server sends null for screens where nobody is)
apge.bindCountdown('timer', null, {urgentAt: view => view.timer_warning, onUrgent: () => APGE.sound.beep()});
fetch('/apge-info').then(r => r.json()).then(info => { joinUrl = info.player_url; if (apge.view) render(apge.view); })
    .catch(() => {});

apge.on('state', render);

function layout(name) {
    if (document.body.dataset.layout !== name) {
        document.body.dataset.layout = name;
        Stage.fit();
    }
}

function fill(above, below, caption) {
    $('above').innerHTML = above || '';
    $('below').innerHTML = below || '';
    $('stage-caption').innerHTML = caption || '';
}

function elapsedInTimer(view) {
    return view.timer ? view.timer.duration - view.timer.remaining : 0;
}

/** Who has locked in, as a row of heads with ticks (never what they chose). Continue screens
 * tick on `ready`; input screens on the game's `done` flag. */
function progress(view, label) {
    const rules = view.rules, field = view.ready_check ? 'ready' : 'done';
    return `<div class="progress"><span>${esc(label || 'Locked in')}:</span>` + view.players.map(p =>
        `<span class="chip ${p[field] ? 'yes' : ''} ${p.connected ? '' : 'offline'}">${head(p, rules, 28)}${esc(p.name)}${p[field] ? ' ✓' : ''}</span>`).join('') + '</div>';
}

function roster(view) {
    return '<div class="roster">' + view.players.map(p =>
        `<div class="card ${p.connected ? '' : 'offline'}">${head(p, view.rules, 64)}<b>${esc(p.name)}</b></div>`).join('') + '</div>';
}

const SCREENS = {
    lobby(view) {
        layout('board');
        const rules = view.rules;
        const done = view.players.filter(p => p.character_done);
        const making = view.players.length - done.length;
        const vip = view.players.find(p => p.id === view.vip_id);
        const cards = done.map(p => `<div class="card pop">${head(p, rules, 96)}<b>${esc(p.name)}</b>` +
            (p.id === view.vip_id ? '<span class="badge">HOST</span>' : '') + '</div>').join('');
        fill(`
            <div class="lobby">
                <div class="lobby-left">
                    ${art('title', 'title-art')}
                    <img class="qr" src="/apge-qr.png" alt="Scan to join">
                    <p class="url">${esc(joinUrl)}</p>
                </div>
                <div class="lobby-right">
                    <div class="roster">${cards || '<p class="dim">Scan the code to make your character!</p>'}</div>
                    <p class="count">${done.length} player${done.length === 1 ? '' : 's'} ready` +
                    (making ? ` · ${making} still creating` : '') + `</p>
                    ${vip ? `<p class="big gold">${esc(vip.name)} is the HOST<br>HOST START WHEN READY</p>` : ''}
                </div>
            </div>`);
    },

    map(view) {
        layout('map');
        const stop = view.data.season[view.data.stop];
        Stage.scene('map-' + view.data.stop, Stage.mapScene(view));
        const zone = `<small>${esc(stop.zone_name)}</small>`;
        fill('', roster(view), `<div class="caption">${stopTitle(stop)}<br>${zone}</div>`);
    },

    bet(view) {
        layout('board');
        const ev = view.data.event, odds = view.data.odds, rules = view.rules;
        const rows = view.players.map(p => `<tr><td>${head(p, rules, 40)}</td><td>${esc(p.name)}</td>` +
            `<td class="odds">${odds[p.id].label}</td><td>${p.done ? '✓' : ''}</td></tr>`).join('');
        fill(`<div class="oddsbox"><h2>${esc(ev.name)} · Odds</h2><table>${rows}</table>
                <p class="dim">Place your bets on your phone!</p></div>`,
            `<div class="setup">${art(ev.venue_art)}<div><h2>${esc(ev.name)}</h2>
                <p>${esc(ev.venue)} · ${esc(ev.town)} · ${esc(ev.zone_name)}</p>
                <p class="big">${esc(ev.setup)}</p>${ev.lowest_wins ? '<p class="gold">Lowest score wins!</p>' : ''}</div></div>`);
    },

    frisk(view) {
        layout('board');
        const rows = view.data.frisks.map(f => `<div class="frisk"><h3>${esc(f.name)}</h3>` +
            (f.caught.length ? '<ul>' + f.caught.map(c => `<li>Confiscated: <b>${esc(c.item)}</b> on ${esc(c.target)}</li>`).join('') + '</ul>'
                : '<p class="gold">Clean as a whistle.</p>') + '</div>').join('');
        fill(`<div class="center">${art('agent_kevin', 'agent')}
              <h2>Random frisk!</h2><div class="frisks">${rows}</div></div>`);
    },

    perform(view) {
        layout('stage');
        const ev = view.data.event;
        Stage.scene('perform-' + view.data.stop, Stage.eventScene(view), elapsedInTimer(view));
        fill(`<h2 class="center">${esc(ev.name)} · ${esc(ev.venue)}</h2>`);
    },

    payout(view) {
        layout('board');
        const pay = view.data.payout, perf = view.data.performance, ev = view.data.event;
        const players = byId(view), rules = view.rules, winner = players[pay.winner];
        const unit = ev.unit ? ' ' + ev.unit : '';
        const order = pay.order.map((id, i) => `<li>${head(players[id], rules, 32)} ${esc(players[id].name)}` +
            (ev.visual === 'turns' ? ` <span class="dim">${perf.scores[id]}${esc(unit)}</span>` : '') +
            (perf.tiebroken.includes(id) ? ' <span class="dim">(tiebreak)</span>' : '') + '</li>').join('');
        const bets = pay.winning_bets.length ? '<ul class="bets">' + pay.winning_bets.map(b =>
            `<li><b>${esc(b.name)}</b> bet ${dd(b.stake)} → collects <b class="gold">${dd(b.payout)}</b></li>`).join('') + '</ul>'
            : '<p class="dim">No winning bets. The house thanks you.</p>';
        const cut = pay.winner_cut
            ? `<p class="big">${esc(winner.name)} takes ${rules.winner_cut_percent}% of the winnings: <b class="gold">${dd(pay.winner_cut)}</b></p>` : '';
        fill(`<div class="result">
                <div class="winner">${head(winner, rules, 140)}<h1>${esc(winner.name)} wins!</h1><p>at ${esc(pay.odds)}</p>${cut}</div>
                <div><h3>Finishing order</h3><ol>${order}</ol><h3>Winning bets</h3>${bets}</div>
              </div>`, progress(view, 'Continue'));
    },

    purse(view) {
        layout('board');
        const r = view.rules.purse;
        fill(`<div class="center">${art('purse', 'prop')}<h1>Mother's Purse</h1>
            <p class="big">Players may either STEAL or DON'T STEAL out of your mother's purse.</p>
            <ul class="rules-list">
                <li>If ALL players pick DON'T STEAL, then ALL players get ${dd(r.honest)}</li>
                <li>If ONLY 1 player picks STEAL, then that player gets ${dd(r.thief)}</li>
                <li>If MORE THAN 1 player picks STEAL, then ALL players get $Dd 0</li>
            </ul></div>`, progress(view));
    },

    purse_result(view) {
        layout('board');
        const players = byId(view);
        const rows = view.data.purse.map(r => `<li>${head(players[r.id], view.rules, 36)} <b>${esc(r.name)}</b>: ` +
            `${r.choice === 'steal' ? 'STEAL' : "DON'T STEAL"}${r.forced ? ' <span class="dim">(no moral courage)</span>' : ''}` +
            ` → <b class="gold">${dd(r.won)}</b></li>`).join('');
        fill(`<div class="center"><h1>Mother's Purse</h1><ul class="choices">${rows}</ul></div>`, progress(view, 'Continue'));
    },

    auction(view) {
        layout('board');
        const a = view.data.auction;
        fill(`<div class="center">${art('card_pack', 'prop')}
            <h1>Rugby Legends Trading Card Pack [Sealed] Auction</h1>
            <p class="huge" id="auction-clock"></p>
            <p class="big">Estimated value: <b class="gold">${dd(view.rules.card_pack_value[0])} – ${dd(view.rules.card_pack_value[1])}</b></p>
            <p class="big">Current Winner: <b>${a.leader_name ? esc(a.leader_name) : ''}</b></p>
            <p class="huge gold">High Bid: ${dd(a.high_bid || view.rules.auction_opening_bid)}</p></div>`);
        $('auction-clock').textContent = Math.ceil(apge.timeRemaining() || 0) + 's';
    },

    auction_open(view) {
        layout('stage');
        Stage.scene('cards-' + view.data.stop, Stage.cardsScene(view, view.timer ? view.timer.duration : 16), elapsedInTimer(view));
        fill(`<h2 class="center">${esc(view.data.auction.leader_name)} opens the pack...</h2>`);
    },

    auction_result(view) {
        layout('board');
        const a = view.data.auction;
        const body = a.leader_name
            ? `<p class="big">${esc(a.leader_name)} paid ${dd(a.high_bid)} for a pack worth <b class="gold">${dd(a.total)}</b></p>
               <p class="huge ${a.total >= a.high_bid ? 'gold' : 'red'}">${a.total >= a.high_bid ? 'Bargain!' : 'Ouch.'}</p>`
            : '<p class="big">No bids. The pack goes back in the drawer.</p>';
        fill(`<div class="center"><h1>Trading Card Auction</h1>${body}</div>`, progress(view, 'Continue'));
    },

    case(view) {
        layout('board');
        const c = view.data.case, name = esc(c.holder_name);
        fill(`<div class="center">${art('briefcase', 'prop')}<p class="huge gold">${dd(c.cash)}</p>
            <p class="big">${name} has the case. Do the other players want to split <b>the CASE</b> (and ${name} gets ${dd(c.cash)})
            OR split <b>the ${dd(c.cash)} CASH</b> (and ${name} gets the case)?</p>
            <p class="dim">Only ${name} knows what's inside. Ask them. Trust them. Or don't.</p></div>`, progress(view, 'Voted'));
    },

    case_result(view) {
        layout('board');
        const c = view.data.case;
        const votes = c.votes.map(v => `<li>${esc(v.name)}: ${v.vote ? (v.vote === 'case' ? 'The CASE' : 'The CASH') : '<span class="dim">no vote</span>'}</li>`).join('');
        const took = c.decision === 'case' ? 'the CASE' : 'the CASH';
        const reveal = c.decision === 'case'
            ? `<p class="huge gold">The case held ${dd(c.value)}</p><p class="big">${esc(c.holder_name)} gets ${dd(c.cash)}; everyone else gets ${dd(c.share)}</p>`
            : `<p class="big">Everyone else splits the cash: ${dd(c.share)} each.</p><p class="big">${esc(c.holder_name)} keeps the case... and the secret.</p>`;
        fill(`<div class="center"><h1>They took ${took}!</h1>${c.coin_flip ? '<p class="dim">(Tied vote - settled by coin flip)</p>' : ''}
            <ul class="choices">${votes}</ul>${reveal}</div>`, progress(view, 'Continue'));
    },

    scalp(view) {
        layout('board');
        const s = view.data.scalp;
        fill(`<div class="center">${art('tickets', 'prop')}<h1>Tickets! Extra Tickets!</h1>
            <p class="dim">Round ${s.round} of ${s.rounds}</p>
            <p class="huge gold">Face Value: ${dd(s.face)}</p>
            <p class="big">Lowest Bid gets sold! All ties forfeit sale.</p></div>`, progress(view, 'Priced'));
    },

    scalp_result(view) {
        layout('board');
        const s = view.data.scalp;
        const asks = s.asks.map(a => `<li class="${a.name === s.winner_name ? 'gold' : ''}">${esc(a.name)}: ${dd(a.price)}</li>`).join('');
        fill(`<div class="center"><h1>Ticket Scalping · Round ${s.round} of ${s.rounds}</h1><ol class="choices">${asks}</ol>
            ${s.winner_name ? `<p class="huge gold">${esc(s.winner_name)} sells for ${dd(s.price)}!</p>` : '<p class="big">Every price tied - no sale!</p>'}</div>`,
            progress(view, 'Continue'));
    },

    game_over(view) {
        layout('board');
        renderFinal(view);
    },
};

// Final results are revealed in beats: standings last place first, then the loansharks
// collect, then the winner and awards.
function renderFinal(view) {
    const f = view.data.final, players = byId(view), rules = view.rules;
    const {beat, n, loansharks, winner} = finalReveal(view, apge.phaseStarted);
    const row = (r, i, withDebt) => `<li>${head(players[r.id], rules, 40)} <b>${esc(r.name)}</b> ` +
        (withDebt ? `${dd(r.cash)} <span class="red">- ${dd(r.debt)} owed</span> = <b class="gold">${dd(r.final)}</b>`
                  : `<b class="gold">${dd(r.cash)}</b>`) + '</li>';
    let html = '<div class="center final">';
    if (beat <= n) {
        const shown = f.before.slice(0, Math.max(1, beat + 1));
        html += '<h1>The season is over!</h1><p class="big">Final cash, from last place...</p><ol class="standings" reversed start="' + n + '">' +
            shown.map((r, i) => row(r, i, false)).join('') + '</ol>';
    } else {
        html += (beat === loansharks ? `${art('loansharks', 'prop')}<h1>But wait... Shrimp and Barbie want their money back!</h1>`
            : `<h1>${f.winners.map(esc).join(' & ')} win${f.winners.length > 1 ? '' : 's'} the Derby!</h1>`) +
            '<ol class="standings">' + f.after.map((r, i) => row(r, i, true)).join('') + '</ol>';
        if (beat >= winner) {
            html += '<div class="awards">' + (f.awards.map(a =>
                `<div class="award"><h3>${esc(a.title)}</h3><p>${a.names.map(esc).join(' & ')} · ${esc(a.label)}</p></div>`).join('') ||
                '') + '</div><p class="dim">The house always wins.</p>';
        }
    }
    $('above').innerHTML = html + '</div>';
    $('below').innerHTML = '';
    clearTimeout(revealTimer);
    if (beat <= winner) revealTimer = setTimeout(() => apge.view && apge.view.phase === 'game_over' && renderFinal(apge.view), 500);
}

function renderControls(view) {
    const el = $('controls');
    if (!apge.isHost()) { el.innerHTML = ''; return; }
    const buttons = [];
    if (view.phase === 'lobby') buttons.push(['start', 'Start game', view.players.length < view.min_players]);
    else if (view.phase === view.end_phase) buttons.push(['reset', 'One more game'], ['quit', 'Quit']);
    else buttons.push(['skip', 'Skip']);
    el.innerHTML = buttons.map(([cmd, label, disabled]) =>
        `<button class="apge-button small" data-cmd="${cmd}" ${disabled ? 'disabled' : ''}>${label}</button>`).join('');
}

$('controls').addEventListener('click', e => {
    const cmd = e.target.dataset && e.target.dataset.cmd;
    if (!cmd) return;
    const view = apge.view;
    if (cmd === 'skip' && !confirm('Skip ahead? Anyone still choosing gets no say this time.')) return;
    if (cmd === 'start' && !view.lobby_ready && !confirm('Not everyone has finished their character. Start anyway?')) return;
    if (cmd === 'quit' && !confirm('Quit? Everyone goes back to the join screen.')) return;
    apge[cmd]();
});

function render(view) {
    const stop = view.data.season && view.data.season[view.data.stop];
    $('where').innerHTML = stop && view.phase !== 'lobby' && view.phase !== 'game_over'
        ? `${esc(stop.zone_name)} · ${esc(stop.name)}` : '';
    if (view.phase !== 'map' && view.phase !== 'perform' && view.phase !== 'auction_open') Stage.clear();
    const screen = SCREENS[view.phase];
    if (screen) screen(view);
    renderControls(view);
}

// The auction clock is big and central, so tick it locally between updates. The sound hint
// stays up until someone clicks the host page (browsers won't beep before that).
setInterval(() => {
    const clock = $('auction-clock'), left = apge.timeRemaining() || 0;
    if (clock) {
        clock.textContent = Math.ceil(left) + 's';
        const warnAt = apge.view && apge.view.timer_warning;
        clock.classList.toggle('red', warnAt != null && left <= warnAt);
    }
    $('sound').hidden = APGE.sound.allowed();
}, 250);
