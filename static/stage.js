/*
 * Host-screen canvas: the map and the event animations.
 *
 * Every scene is a pure function of (elapsed seconds, data), so a state update arriving
 * mid-animation never restarts it: Stage.scene(key, fn) only resets the clock when the
 * key changes. Placeholder art is labelled boxes ("[ART: ...]") until real art lands;
 * players are stick figures wearing the head they drew.
 */
(function () {
    'use strict';

    const INK = '#f4ecd8';
    const GOLD = '#ffcd00';
    const GREEN = '#00843d';

    let canvas, ctx, current = null, started = 0, W = 0, H = 0;

    function mount(el) {
        canvas = el;
        ctx = canvas.getContext('2d');
        const fit = () => {
            const r = canvas.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            canvas.width = Math.max(1, r.width * dpr);
            canvas.height = Math.max(1, r.height * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            W = r.width; H = r.height;
        };
        // Refit whenever the canvas box changes (layout switches, the HTML around it growing),
        // otherwise the drawing is stretched to the old size
        new ResizeObserver(fit).observe(canvas);
        fit();
        requestAnimationFrame(loop);
        Stage.fit = fit;
    }

    /** Show a scene. Same key = keep the clock running (a state update mid-animation). */
    function scene(key, fn, offset) {
        if (!current || current.key !== key) {
            started = performance.now() - (offset || 0) * 1000;
            Stage.fit();
        }
        current = {key: key, fn: fn};
    }

    function clear() { current = null; if (ctx) ctx.clearRect(0, 0, W, H); }

    function loop(now) {
        if (current && W) {
            ctx.clearRect(0, 0, W, H);
            try { current.fn(ctx, W, H, (now - started) / 1000); } catch (e) { console.error(e); current = null; }
        }
        requestAnimationFrame(loop);
    }

    // ---- drawing helpers ---------------------------------------------------------------

    function text(c, str, x, y, size, opts) {
        opts = opts || {};
        c.font = (opts.bold ? 'bold ' : '') + size + 'px system-ui, sans-serif';
        c.fillStyle = opts.color || INK;
        c.textAlign = opts.align || 'center';
        c.textBaseline = opts.baseline || 'middle';
        c.fillText(str, x, y);
    }

    /** Placeholder art: a labelled rectangle. corner: put the label top-left (busy maps). */
    function box(c, label, x, y, w, h, color, corner) {
        c.fillStyle = color || 'rgba(255,255,255,0.08)';
        c.fillRect(x, y, w, h);
        c.strokeStyle = INK;
        c.lineWidth = 2;
        c.setLineDash([6, 4]);
        c.strokeRect(x, y, w, h);
        c.setLineDash([]);
        if (corner) text(c, label, x + 4, y - 9, 11, {color: 'rgba(244,236,216,0.7)', align: 'left'});
        else text(c, label, x + w / 2, y + h / 2, Math.max(10, Math.min(18, h / 3)), {color: INK});
    }

    /**
     * A stick figure with its feet at (x, y). opts: head (art string), rules, swing (walk
     * phase, radians), lying (fallen over), color, name.
     */
    function figure(c, x, y, h, opts) {
        opts = opts || {};
        c.save();
        c.translate(x, y);
        if (opts.lying) c.rotate(-Math.PI / 2 * (opts.lyingDir || 1));
        const head = h * 0.36, swing = opts.swing || 0;
        const neck = -h + head, hip = -h * 0.4, shoulder = neck + h * 0.06;
        c.strokeStyle = opts.color || INK;
        c.lineWidth = Math.max(2, h * 0.05);
        c.lineCap = 'round';
        c.beginPath();
        // Limbs: a resting stance (so a still figure isn't a single line) plus the walk swing
        const stance = h * 0.11, reach = h * 0.2, arm = opts.armsUp ? shoulder - h * 0.25 : shoulder + h * 0.22;
        c.moveTo(0, neck); c.lineTo(0, hip);
        c.moveTo(0, shoulder); c.lineTo(-reach + Math.sin(swing) * h * 0.18, arm);
        c.moveTo(0, shoulder); c.lineTo(reach - Math.sin(swing) * h * 0.18, arm);
        c.moveTo(0, hip); c.lineTo(stance + Math.sin(swing) * h * 0.16, 0);
        c.moveTo(0, hip); c.lineTo(-stance - Math.sin(swing) * h * 0.16, 0);
        c.stroke();
        if (opts.head && opts.rules && opts.head.replace(/\./g, '')) {
            PixelArt.draw(c, opts.head, opts.rules.palette, opts.rules.pixel_chars, -head / 2, -h, head);
            c.lineWidth = 1;
            c.strokeStyle = 'rgba(244,236,216,0.35)';
            c.strokeRect(-head / 2, -h, head, head);
        } else {
            c.beginPath();
            c.arc(0, -h + head / 2, head / 2.4, 0, Math.PI * 2);
            c.stroke();
        }
        c.restore();
        if (opts.name && !opts.lying) text(c, opts.name, x, y + 14, 14, {bold: true});
        if (opts.name && opts.lying) text(c, opts.name, x, y + 14, 14, {color: '#bbb'});
    }

    const ease = t => t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t);
    const noise = (seed, t) => Math.sin(t * (2.1 + seed % 1.7) + seed * 7.3) * 0.6 + Math.sin(t * (3.7 + seed % 0.9) + seed) * 0.4;

    function seedOf(id) {
        let s = 0;
        for (let i = 0; i < id.length; i++) s = (s * 31 + id.charCodeAt(i)) % 9973;
        return s / 97;
    }

    // ---- map --------------------------------------------------------------------------------

    // Rough bounding boxes (lon/lat) - placeholder rectangles until there's a drawn map
    const LANDMASSES = [
        {label: 'AUSTRALIA', lon: [113.2, 153.6], lat: [-10.7, -39.1]},
        {label: 'TAS', lon: [144.6, 148.4], lat: [-40.6, -43.6]},
        {label: 'NZ NORTH', lon: [172.6, 178.6], lat: [-34.4, -41.6]},
        {label: 'NZ SOUTH', lon: [166.4, 174.4], lat: [-40.5, -46.7]},
    ];

    function mapScene(view) {
        return function (c, w, h, t) {
            const data = view.data, rules = view.rules;
            const pad = 20, lon0 = 110, lon1 = 181, lat0 = -8, lat1 = -48;
            const sx = (w - pad * 2) / (lon1 - lon0), sy = (h - pad * 2) / (lat0 - lat1);
            const s = Math.min(sx, sy);
            const ox = (w - (lon1 - lon0) * s) / 2, oy = (h - (lat0 - lat1) * s) / 2;
            const px = lon => ox + (lon - lon0) * s, py = lat => oy + (lat0 - lat) * s;

            LANDMASSES.forEach(m => box(c, m.label, px(m.lon[0]), py(m.lat[0]),
                (m.lon[1] - m.lon[0]) * s, (m.lat[0] - m.lat[1]) * s, 'rgba(0,132,61,0.25)', true));

            const stops = data.season || [];
            c.strokeStyle = 'rgba(255,205,0,0.5)';
            c.lineWidth = 3;
            c.setLineDash([8, 6]);
            c.beginPath();
            stops.forEach((st, i) => (i ? c.lineTo : c.moveTo).call(c, px(st.lon), py(st.lat)));
            c.stroke();
            c.setLineDash([]);

            stops.forEach((st, i) => {
                const x = px(st.lon), y = py(st.lat);
                const past = i < data.stop, here = i === data.stop;
                if (st.kind === 'special') {
                    text(c, '★', x, y, here ? 30 : 20, {color: past ? '#777' : GOLD});
                } else {
                    c.fillStyle = past ? '#777' : here ? GOLD : INK;
                    c.beginPath(); c.arc(x, y, here ? 9 : 6, 0, Math.PI * 2); c.fill();
                    text(c, st.town.replace(/, (NZ|AUS)$/, ''), x + 10, y - 12, 12, {align: 'left', color: past ? '#888' : INK});
                }
            });

            const here = stops[data.stop];
            if (!here) return;
            const marker = view.players.find(p => p.id === data.map_marker);
            const bob = Math.sin(t * 4) * 4;
            if (marker) figure(c, px(here.lon), py(here.lat) - 6 + bob, 54, {head: marker.head, rules: rules});
        };
    }

    // ---- gambling events ------------------------------------------------------------------------

    function playersById(view) {
        const m = {};
        view.players.forEach(p => { m[p.id] = p; });
        return m;
    }

    function raceScene(view) {
        const perf = view.data.performance, ev = view.data.event, rules = view.rules;
        const D = perf.duration || 9, order = perf.order, n = order.length;
        const lanes = view.players.map(p => p.id).filter(id => order.includes(id));
        const finishAt = {};
        order.forEach((id, k) => { finishAt[id] = D * (0.62 + 0.22 * k / Math.max(1, n - 1)); });
        const up = ev.direction === 'up';
        const byId = playersById(view);

        return function (c, w, h, t) {
            const margin = 70;
            const span = up ? h - margin * 2 : w - margin * 2.5;
            const laneSize = (up ? w - margin * 2 : h - margin) / lanes.length;
            const figH = Math.min(laneSize * 0.75 * (ev.scale || 1), (up ? 140 : h * 0.6));
            if (up) {
                box(c, '[ART: summit / finish line]', margin, margin - 40, w - margin * 2, 30);
            } else {
                c.fillStyle = INK;
                for (let y = 0; y < h; y += 16) c.fillRect(margin + span + 10, y, 6, 8);
                text(c, 'FINISH', margin + span + 13, 14, 14, {bold: true, color: GOLD});
            }
            lanes.forEach((id, lane) => {
                const T = finishAt[id];
                const base = Math.min(1, t / T);
                const wobble = base < 1 ? noise(seedOf(id), t) * 0.07 * Math.sin(Math.PI * base) : 0;
                const prog = Math.max(0, Math.min(1, base + wobble));
                const running = prog < 1;
                const swing = running ? Math.sin(t * 12 + lane) * 0.9 : 0;
                const place = order.indexOf(id) + 1;
                let x, y;
                if (up) {
                    x = margin + laneSize * (lane + 0.5);
                    y = h - margin + 20 - prog * span;
                } else {
                    x = margin + prog * span;
                    y = laneSize * (lane + 1) + margin / 2 - 6;
                    c.strokeStyle = 'rgba(255,255,255,0.12)';
                    c.beginPath(); c.moveTo(0, y + 2); c.lineTo(w, y + 2); c.stroke();
                }
                figure(c, x, y, figH, {head: byId[id].head, rules: rules, swing: swing, name: byId[id].name});
                if (!running) text(c, Common.ordinal(place), x + (up ? 0 : figH * 0.5 + 18), y - figH - (up ? 14 : -figH / 2), 20, {bold: true, color: GOLD});
            });
        };
    }

    function eliminationScene(view) {
        const perf = view.data.performance, ev = view.data.event, rules = view.rules;
        const D = perf.duration, order = perf.order, n = order.length;
        const variant = ev.variant;
        const byId = playersById(view);
        // Worst first: elimination k happens at outAt[id]
        const outAt = {};
        order.slice(1).reverse().forEach((id, k) => { outAt[id] = 2 + k * (D - 3.5) / Math.max(1, n - 1); });
        const seats = view.players.map(p => p.id).filter(id => order.includes(id));

        return function (c, w, h, t) {
            const cx = w / 2, cy = h * 0.58;
            const R = Math.min(w, h) * (variant === 'sumo' ? 0.34 : 0.28);
            const figH = Math.min(150, h * 0.22) * (ev.scale || 1) * (variant === 'sumo' ? 0.75 : 1);
            if (variant === 'sumo') {
                c.strokeStyle = GOLD; c.lineWidth = 5;
                c.beginPath(); c.ellipse(cx, cy, R, R * 0.45, 0, 0, Math.PI * 2); c.stroke();
                text(c, '[ART: dohyo ring]', cx, cy + R * 0.45 + 18, 14);
            } else if (variant === 'note') {
                box(c, '[ART: Opera House stage]', w * 0.1, h * 0.12, w * 0.8, 36);
            } else {
                box(c, '[ART: dust cloud]', cx - R, cy - R * 0.4 - 60, R * 2, 32);
            }
            seats.forEach((id, i) => {
                const out = outAt[id] !== undefined && t >= outAt[id];
                const since = out ? t - outAt[id] : 0;
                const s = seedOf(id);
                let x, y;
                if (variant === 'note') {
                    x = w * (i + 1) / (seats.length + 1);
                    y = cy + 40;
                    if (!out) {
                        x += Math.sin(t * 40 + s) * 2;
                        const k = (t * 0.8 + s) % 1;
                        text(c, '♪', x + 20 + Math.sin(k * 6) * 8, y - figH - k * 70, 22, {color: GOLD});
                    }
                } else {
                    const a = (i / seats.length) * Math.PI * 2 - Math.PI / 2;
                    const r = variant === 'sumo' ? R * 0.55 : R * 0.6;
                    x = cx + Math.cos(a) * r;
                    y = cy + Math.sin(a) * r * 0.45;
                    if (!out && t < D - 1.2) {
                        // Mashing into each other: lurch toward the middle and back
                        const lurch = Math.max(0, Math.sin(t * (3 + s % 2) + s)) * (variant === 'sumo' ? 0.35 : 0.5);
                        x += (cx - x) * lurch + noise(s, t * 3) * 6;
                        y += (cy - y) * lurch;
                    }
                    if (out && variant === 'sumo') {
                        const push = ease(since / 0.6);
                        x += Math.cos(a) * R * 0.9 * push;
                        y += Math.sin(a) * R * 0.45 * 0.9 * push;
                    }
                }
                figure(c, x, y, figH, {head: byId[id].head, rules: rules, name: byId[id].name,
                    lying: out && (variant !== 'sumo' || since > 0.6), lyingDir: i % 2 ? 1 : -1,
                    swing: out ? 0 : Math.sin(t * 9 + i) * 0.5, armsUp: !out && t >= D - 1.2});
            });
            if (t >= D - 1.2) text(c, byId[order[0]].name + ' WINS!', cx, h * 0.08 + 40, 34, {bold: true, color: GOLD});
        };
    }

    const PROPS = {
        kick: {label: '[ART: sand pitch]', ball: '#d9c79e'},
        golf: {label: '[ART: mini golf hole + sculptures]', ball: '#ffffff'},
        shot: {label: '[ART: half court]', ball: '#ff8c00'},
    };

    function turnsScene(view) {
        const perf = view.data.performance, ev = view.data.event, rules = view.rules;
        const byId = playersById(view);
        const turns = view.players.map(p => p.id).filter(id => perf.order.includes(id));
        const scores = perf.scores;
        const vals = turns.map(id => scores[id]);
        const max = Math.max.apply(null, vals.map(Math.abs).concat([1]));
        const TURN = 3;
        const prop = PROPS[ev.prop] || PROPS.kick;

        return function (c, w, h, t) {
            const k = Math.min(turns.length - 1, Math.floor(t / TURN));
            const u = Math.min(1, (t - k * TURN) / (TURN * 0.7));
            const id = turns[k], p = byId[id];
            const ground = h * 0.78, figH = Math.min(160, h * 0.3);
            box(c, prop.label, 20, ground + 12, w - 40, h - ground - 24);
            let fx = 90;
            if (ev.prop === 'shot') {
                const hoopX = w - 120, hoopY = h * 0.3;
                box(c, '[ART: hoop]', hoopX - 10, hoopY - 50, 70, 50);
                fx = 80 + (w * 0.42 - 80) * ease(Math.min(1, u * 1.6));
                const leap = Math.sin(Math.PI * Math.min(1, Math.max(0, u * 1.6 - 0.6))) * 50;
                figure(c, fx, ground - leap, figH, {head: p.head, rules: rules, name: p.name, swing: Math.sin(t * 12) * (u < 0.6 ? 0.8 : 0), armsUp: u > 0.6});
                if (u > 0.6) {
                    const b = Math.min(1, (u - 0.6) / 0.4);
                    const bx = fx + (hoopX + 25 - fx) * b, by = ground - figH - leap - Math.sin(Math.PI * b) * h * 0.25 + (hoopY - (ground - figH)) * b;
                    c.fillStyle = prop.ball; c.beginPath(); c.arc(bx, by, 10, 0, Math.PI * 2); c.fill();
                }
            } else {
                figure(c, fx, ground, figH, {head: p.head, rules: rules, name: p.name, swing: u < 0.3 ? Math.sin(t * 10) * 0.7 : 0});
                const dist = Math.max(0.05, Math.abs(scores[id]) / max);
                const travel = ev.prop === 'golf' ? 1 - Math.min(0.9, dist * 0.9) : dist;
                const bx = fx + 30 + (w - fx - 120) * travel * ease(u);
                const by = ev.prop === 'kick' ? ground - Math.sin(Math.PI * ease(u)) * h * 0.25 : ground - 6;
                if (ev.prop === 'golf') {
                    c.fillStyle = '#111'; c.beginPath(); c.ellipse(w - 90, ground - 2, 14, 5, 0, 0, Math.PI * 2); c.fill();
                }
                c.fillStyle = prop.ball; c.beginPath(); c.arc(bx, by, 9, 0, Math.PI * 2); c.fill();
            }
            if (u >= 1) text(c, `${p.name}: ${scores[id]} ${ev.unit}`, w / 2, h * 0.12, 32, {bold: true, color: GOLD});
            // Running scoreboard of finished turns
            turns.slice(0, u >= 1 ? k + 1 : k).forEach((pid, i) => {
                text(c, `${byId[pid].name}  ${scores[pid]}`, w - 24, 30 + i * 22, 16, {align: 'right'});
            });
        };
    }

    function eventScene(view) {
        const visual = view.data.event.visual;
        if (visual === 'race') return raceScene(view);
        if (visual === 'elimination') return eliminationScene(view);
        return turnsScene(view);
    }

    // ---- card pack -----------------------------------------------------------------------------

    function cardsScene(view, duration) {
        const cards = view.data.auction.cards;
        return function (c, w, h, t) {
            const per = (duration - 3) / cards.length;
            const shown = Math.min(cards.length, Math.floor(t / per) + 1);
            let total = 0;
            const cw = Math.min(150, (w - 80) / cards.length - 16, h * 0.4 / 1.4), ch = cw * 1.4;
            cards.forEach((card, i) => {
                const x = 40 + i * (cw + 16), y = h * 0.35;
                if (i >= shown) { box(c, '?', x, y, cw, ch, 'rgba(0,0,0,0.3)'); return; }
                total += card.value;
                box(c, card.holo ? '[ART: HOLO]' : '[ART: card]', x, y, cw, ch, card.holo ? 'rgba(255,205,0,0.35)' : 'rgba(255,255,255,0.12)');
                text(c, card.holo ? 'Holographic card reveal!' : card.name, x + cw / 2, y - 18, 13, {bold: card.holo, color: card.holo ? GOLD : INK});
                if (card.holo) text(c, card.name, x + cw / 2, y + ch + 18, 13);
                text(c, `Sell Value: $${card.value}`, x + cw / 2, y + ch + (card.holo ? 38 : 18), 15, {bold: true, color: GOLD});
            });
            text(c, `Running total: $Dd ${total}`, w / 2, h * 0.15, 34, {bold: true, color: GOLD});
        };
    }

    window.Stage = {mount, scene, clear, mapScene, eventScene, cardsScene, figure, box, GREEN, GOLD};
})();
