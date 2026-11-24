/* Helpers shared by the host and phone pages. Game numbers come from view.rules, never here. */
const Common = (function () {
    'use strict';
    const esc = APGE.escapeHtml;
    const urls = new Map();

    /** <img> of a player's drawn head (pixelated), or an empty frame if they drew nothing. */
    function head(player, rules, px, cls) {
        const art = player && player.head;
        const size = `width="${px}" height="${px}"`;
        if (!art || !art.replace(/\./g, '')) return `<span class="head blank ${cls || ''}" style="width:${px}px;height:${px}px"></span>`;
        let url = urls.get(art);
        if (!url) {
            url = PixelArt.image(art, rules.palette, rules.pixel_chars).toDataURL();
            if (urls.size > 200) urls.clear();
            urls.set(art, url);
        }
        return `<img class="head ${cls || ''}" src="${url}" ${size} alt="">`;
    }

    const dd = n => (n < 0 ? '-$Dd ' : '$Dd ') + Math.abs(n).toLocaleString('en-US');
    const signed = n => (n > 0 ? '+' : '') + dd(n);

    function byId(view) {
        const m = {};
        view.players.forEach(p => { m[p.id] = p; });
        return m;
    }

    /** Preview of a winning bet's return, after the event winner's cut. Display only: the
     * server pays with rules.payout. */
    function winnings(stake, odds, rules) {
        const won = Math.floor(stake * odds.num / odds.den);
        return stake + won - Math.floor(won * rules.winner_cut_percent / 100);
    }

    /** Where the final-results reveal is up to. Beats 0..n show the standings from last place,
     * then the loansharks collect, then the winner. Host and phones each pace it from when
     * they saw game_over begin (phaseStarted), so phones keep their place secret until then. */
    function finalReveal(view, phaseStarted) {
        const n = view.data.final.before.length, ms = view.rules.final_reveal_seconds * 1000;
        const elapsed = Date.now() - phaseStarted;
        return {beat: Math.floor(elapsed / ms), n: n, loansharks: n + 1, winner: n + 2,
                msToWinner: Math.max(0, (n + 2) * ms - elapsed)};
    }

    function ordinal(n) {
        const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
        return n + (s[(v - 20) % 10] || s[v] || s[0]);
    }

    /** Game art for HTML screens (an id from dev.ART), or its placeholder box until it has some. */
    function art(id, cls) {
        const a = APGE.art.info(id);
        if (!a) console.error('Art ' + id + ' is not in dev.ART');
        if (a && a.url) {
            return `<img class="art-img ${cls || ''} ${a.pixelated ? 'pixelated' : ''}" src="${esc(a.url)}" alt="${esc(a.name)}">`;
        }
        return `<div class="art ${cls || ''}">[ART: ${esc(a ? a.name : id)}]</div>`;
    }

    function stopTitle(stop) {
        if (!stop) return '';
        return stop.kind === 'special' ? `★ Special Event: ${esc(stop.name)}` : `${esc(stop.venue)} · ${esc(stop.town)}`;
    }

    return {esc, head, dd, signed, byId, winnings, finalReveal, ordinal, art, stopTitle};
})();
