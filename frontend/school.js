/**
 * Вкладка учителя: добавить ученика в свой класс.
 */
(function () {
    function headers() {
        const base = (window.ModelService && ModelService._tgHeaders) ? ModelService._tgHeaders() : {};
        const token = localStorage.getItem('beztel_token');
        if (token) base.Authorization = 'Bearer ' + token;
        return base;
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    async function api(path, options) {
        const origin = (window.ModelService && ModelService._origin) ? ModelService._origin() : location.origin;
        const res = await fetch(origin + '/api/v1' + path, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...headers(), ...(options && options.headers) },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Не получилось');
        return data;
    }

    function render(data, flash) {
        const root = document.getElementById('schoolRoot');
        if (!root) return;
        const classes = data.classes || [];
        if (!classes.length) {
            root.innerHTML = '<article class="school-card"><p>Админ ещё не привязал вас к классу. Когда класс появится, сюда можно будет добавить учеников.</p></article>';
            return;
        }
        const options = classes.map((row) => `<option value="${row.id}">${esc(row.name)}</option>`).join('');
        const students = data.students || [];
        const rows = students.length
            ? students.map((row) => `<tr><td>${esc(row.name)}</td><td>${esc(row.username || '')}</td><td>${row.xp || 0}</td></tr>`).join('')
            : '<tr><td colspan="3">Учеников пока нет</td></tr>';
        root.innerHTML = `
            <article class="school-card">
                <h3>Новый ученик</h3>
                <p class="school-note">Укажите логин уже зарегистрированного ученика. Он окажется в выбранном классе.</p>
                <form id="addStudentForm" class="school-search">
                    <input id="studentLogin" placeholder="Логин ученика" autocomplete="off" required>
                    <select id="studentClass">${options}</select>
                    <button class="school-btn" type="submit">Добавить</button>
                </form>
                <p id="studentMsg" class="school-note">${esc(flash || '')}</p>
            </article>
            <article class="school-card">
                <h3>Мои ученики</h3>
                <table class="school-table">
                    <thead><tr><th>Имя</th><th>Логин</th><th>XP</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </article>`;
        document.getElementById('addStudentForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const msg = document.getElementById('studentMsg');
            msg.textContent = 'Добавляю...';
            try {
                const saved = await api('/school/students', {
                    method: 'POST',
                    body: JSON.stringify({
                        username: document.getElementById('studentLogin').value.trim(),
                        class_id: Number(document.getElementById('studentClass').value),
                    }),
                });
                render(await api('/school/students'), saved.name + ' теперь в вашем классе.');
            } catch (error) {
                msg.textContent = error.message;
            }
        });
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const root = document.getElementById('schoolRoot');
        try {
            const me = await api('/school/me');
            if (me.role !== 'teacher') {
                if (root) root.innerHTML = '<article class="school-card"><p>Эта вкладка появляется у учителя. Назначить учителя может администратор.</p></article>';
                return;
            }
            render(await api('/school/students'));
        } catch (error) {
            if (root) root.innerHTML = `<article class="school-card"><p>${esc(error.message)}</p></article>`;
        }
    });
})();
