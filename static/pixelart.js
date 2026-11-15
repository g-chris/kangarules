/*
 * Pixel art: the editor players draw their heads with, and the /art tool for game assets.
 * A touch/pen/mouse port of in-a-big-forest's art_tools.py: a grid, a palette, pencil and
 * eraser, plus fill, mirror and undo.
 *
 * Art is a string, one char per cell row by row: '.' = transparent, otherwise an index
 * into the palette written with `chars` (rules.PIXEL_CHARS). The server validates heads.
 *
 *   PixelArt.mountPad(el, {grid, palette, chars, value, onChange})  -> {get, set, clear}
 *   PixelArt.image(art, palette, chars)                             -> cached <canvas>
 *   PixelArt.draw(ctx, art, palette, chars, x, y, size)
 */
(function () {
    'use strict';

    const cache = new Map();

    function gridSize(art) { return Math.round(Math.sqrt(art.length)); }

    /** A canvas with one pixel per cell (scale it up with imageSmoothingEnabled = false). */
    function image(art, palette, chars) {
        const key = art + '|' + chars;
        if (cache.has(key)) return cache.get(key);
        const n = gridSize(art);
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = n;
        const ctx = canvas.getContext('2d');
        for (let i = 0; i < art.length; i++) {
            const idx = chars.indexOf(art[i]);
            if (idx < 0) continue;
            ctx.fillStyle = palette[idx];
            ctx.fillRect(i % n, Math.floor(i / n), 1, 1);
        }
        if (cache.size > 200) cache.clear();
        cache.set(key, canvas);
        return canvas;
    }

    function draw(ctx, art, palette, chars, x, y, size) {
        if (!art) return;
        const smooth = ctx.imageSmoothingEnabled;
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(image(art, palette, chars), x, y, size, size);
        ctx.imageSmoothingEnabled = smooth;
    }

    /** An <img>-like element for HTML lists (a scaled canvas). */
    function element(art, palette, chars, px) {
        const c = document.createElement('canvas');
        const n = gridSize(art || '.');
        c.width = c.height = n;
        c.className = 'pixel-head';
        c.style.width = c.style.height = px + 'px';
        if (art) c.getContext('2d').drawImage(image(art, palette, chars), 0, 0);
        return c;
    }

    function mountPad(container, opts) {
        const n = opts.grid, palette = opts.palette, chars = opts.chars;
        // A fresh element per mount, so remounting (e.g. a new grid size) never stacks listeners
        container.innerHTML = '';
        const root = document.createElement('div');
        container.appendChild(root);
        let cells = (opts.value && opts.value.length === n * n ? opts.value : '.'.repeat(n * n)).split('');
        let color = 0, tool = 'pencil', mirror = false;
        const undo = [];

        root.classList.add('pad');
        root.innerHTML =
            '<div class="pad-tools">' +
            ['pencil', 'eraser', 'fill'].map(t => `<button type="button" data-tool="${t}">${t}</button>`).join('') +
            '<button type="button" data-opt="mirror">mirror</button>' +
            '<button type="button" data-opt="undo">undo</button>' +
            '<button type="button" data-opt="clear">clear</button></div>' +
            '<canvas class="pad-canvas"></canvas>' +
            '<div class="pad-palette">' + palette.map((c, i) =>
                `<button type="button" class="swatch" data-color="${i}" style="background:${c}"></button>`).join('') + '</div>';
        const canvas = root.querySelector('canvas');
        const ctx = canvas.getContext('2d');

        function resize() {
            const width = Math.min(container.clientWidth || 320, opts.maxPx || 420);
            const cell = Math.max(4, Math.floor(width / n));
            canvas.width = canvas.height = cell * n;
            render();
        }

        function render() {
            const cell = canvas.width / n;
            for (let i = 0; i < n * n; i++) {
                const x = (i % n) * cell, y = Math.floor(i / n) * cell;
                const idx = chars.indexOf(cells[i]);
                ctx.fillStyle = idx >= 0 ? palette[idx] : (((i % n) + Math.floor(i / n)) % 2 ? '#5a5a5a' : '#6e6e6e');
                ctx.fillRect(x, y, cell, cell);
            }
            if (opts.gridLines !== false && cell >= 8) {
                ctx.strokeStyle = 'rgba(0,0,0,0.25)';
                ctx.lineWidth = 1;
                for (let k = 1; k < n; k++) {
                    ctx.beginPath(); ctx.moveTo(k * cell + 0.5, 0); ctx.lineTo(k * cell + 0.5, canvas.height); ctx.stroke();
                    ctx.beginPath(); ctx.moveTo(0, k * cell + 0.5); ctx.lineTo(canvas.width, k * cell + 0.5); ctx.stroke();
                }
            }
            if (mirror) {
                ctx.strokeStyle = 'rgba(255,220,0,0.7)';
                ctx.beginPath(); ctx.moveTo(canvas.width / 2, 0); ctx.lineTo(canvas.width / 2, canvas.height); ctx.stroke();
            }
            root.querySelectorAll('[data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === tool));
            root.querySelectorAll('[data-color]').forEach(b => b.classList.toggle('on', Number(b.dataset.color) === color));
            root.querySelector('[data-opt=mirror]').classList.toggle('on', mirror);
        }

        function changed() {
            render();
            if (opts.onChange) opts.onChange(cells.join(''));
        }

        function paint(i, value) {
            cells[i] = value;
            if (mirror) {
                const x = i % n, y = Math.floor(i / n);
                cells[y * n + (n - 1 - x)] = value;
            }
        }

        function fill(start, value) {
            const target = cells[start];
            if (target === value) return;
            const stack = [start];
            while (stack.length) {
                const i = stack.pop();
                if (cells[i] !== target) continue;
                cells[i] = value;
                const x = i % n, y = Math.floor(i / n);
                if (x > 0) stack.push(i - 1);
                if (x < n - 1) stack.push(i + 1);
                if (y > 0) stack.push(i - n);
                if (y < n - 1) stack.push(i + n);
            }
        }

        function cellAt(e) {
            const r = canvas.getBoundingClientRect();
            const x = Math.floor((e.clientX - r.left) / r.width * n);
            const y = Math.floor((e.clientY - r.top) / r.height * n);
            return x >= 0 && y >= 0 && x < n && y < n ? y * n + x : -1;
        }

        let drawing = false;
        canvas.addEventListener('pointerdown', e => {
            const i = cellAt(e);
            if (i < 0) return;
            e.preventDefault();
            undo.push(cells.join(''));
            if (undo.length > 50) undo.shift();
            const value = tool === 'eraser' ? '.' : chars[color];
            if (tool === 'fill') { fill(i, value); changed(); return; }
            drawing = true;
            canvas.setPointerCapture(e.pointerId);
            paint(i, value);
            changed();
        });
        canvas.addEventListener('pointermove', e => {
            if (!drawing) return;
            const i = cellAt(e);
            if (i >= 0) { paint(i, tool === 'eraser' ? '.' : chars[color]); changed(); }
        });
        ['pointerup', 'pointercancel'].forEach(t => canvas.addEventListener(t, () => { drawing = false; }));

        root.addEventListener('click', e => {
            const b = e.target.closest('button');
            if (!b || !root.contains(b)) return;
            if (b.dataset.tool) tool = b.dataset.tool;
            if (b.dataset.color) { color = Number(b.dataset.color); if (tool === 'eraser') tool = 'pencil'; }
            if (b.dataset.opt === 'mirror') mirror = !mirror;
            if (b.dataset.opt === 'undo' && undo.length) cells = undo.pop().split('');
            if (b.dataset.opt === 'clear') { undo.push(cells.join('')); cells = cells.map(() => '.'); }
            changed();
        });
        const onResize = () => { if (root.isConnected) resize(); else window.removeEventListener('resize', onResize); };
        window.addEventListener('resize', onResize);
        resize();

        return {
            get: () => cells.join(''),
            set: art => { cells = art.split(''); changed(); },
            clear: () => { cells = cells.map(() => '.'); changed(); },
            resize: resize,
        };
    }

    window.PixelArt = {image, draw, element, mountPad};
})();
