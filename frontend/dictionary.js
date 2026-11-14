/**
 * Словарь: перевод слов и фраз из базы.
 */
(function () {
    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function search(query) {
        const origin = (window.ModelService && ModelService._origin) ? ModelService._origin() : location.origin;
        const headers = (window.ModelService && ModelService._tgHeaders) ? ModelService._tgHeaders() : {};
        const lang = (window.ModelService && ModelService.lang) ? ModelService.lang() : 'ru';
        const res = await fetch(origin + '/api/v1/dictionary?limit=30&lang=' + encodeURIComponent(lang) + '&q=' + encodeURIComponent(query || ''), { headers });
        if (!res.ok) throw new Error('Не удалось открыть словарь');
        return res.json();
    }

    function render(data) {
        const box = document.getElementById('dictResults');
        if (!box) return;
        const items = (data && data.items) || [];
        box.classList.remove('empty-slot-box');
        if (!items.length) {
            box.innerHTML = '<p>В базе нет такого слова. Попробуйте другую форму или более короткую фразу.</p>';
            return;
        }
        const caption = data.query
            ? `Нашёл ${items.length} по запросу «${esc(data.query)}»`
            : 'Слова и фразы из базы';
        box.innerHTML = `<p class="school-note">${caption}</p><div class="dict-list">${items.map((item) => `
            <article class="dict-hit">
                <div class="dict-ba-row">
                    <p class="dict-ba">${esc(item.bashkir)}</p>
                    <button type="button" class="dict-speak" data-speak="${esc(item.bashkir)}" aria-label="Озвучить: ${esc(item.bashkir)}">🔊</button>
                </div>
                <p class="dict-ru">${esc(item.translation)}</p>
                <p class="school-note">${esc(item.topic || 'разговорник')} · сложность ${item.difficulty || 1}${item.source ? ' · ' + esc(item.source) : ''}</p>
            </article>`).join('')}</div>`;
    }

    document.addEventListener('DOMContentLoaded', () => {
        const form = document.getElementById('dictForm');
        const input = document.getElementById('dictQuery');
        if (!form || !input) return;
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const box = document.getElementById('dictResults');
            if (box) box.innerHTML = '<p>Ищу в базе...</p>';
            try {
                render(await search(input.value.trim()));
            } catch (e) {
                if (box) box.innerHTML = `<p>${esc(e.message)}</p>`;
            }
        });
        search('').then(render).catch(() => {});
        const results = document.getElementById('dictResults');
        if (results) {
            results.addEventListener('click', (event) => {
                const button = event.target.closest('.dict-speak');
                if (!button || typeof speakBashkir !== 'function') return;
                speakBashkir(button.getAttribute('data-speak') || '', button);
            });
        }
        const exportBtn = document.getElementById('dictExportBtn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                const origin = (window.ModelService && ModelService._origin) ? ModelService._origin() : location.origin;
                window.location.href = origin + '/api/v1/dictionary/export';
            });
        }
    });
})();
