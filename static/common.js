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

    const dd = n => (n < 0 ? '-$Dd ' : '$Dd ') + Math.abs(n);
    const signed = n => (n > 0 ? '+' : '') + dd(n);

    function byId(view) {
        const m = {};
        view.players.forEach(p => { m[p.id] = p; });
        return m;
    }

    /** Preview of a winning bet's return. Display only: the server pays with rules.payout. */
    const winnings = (stake, odds) => stake + Math.floor(stake * odds.num / odds.den);

    function ordinal(n) {
        const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
        return n + (s[(v - 20) % 10] || s[v] || s[0]);
    }

    /** Placeholder art box for HTML screens. */
    const art = (label, cls) => `<div class="art ${cls || ''}">[ART: ${esc(label)}]</div>`;

    function stopTitle(stop) {
        if (!stop) return '';
        return stop.kind === 'special' ? `★ Special Event: ${esc(stop.name)}` : `${esc(stop.venue)} · ${esc(stop.town)}`;
    }

    return {esc, head, dd, signed, byId, winnings, ordinal, art, stopTitle};
})();
