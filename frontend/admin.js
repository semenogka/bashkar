/**
 * Консоль администратора: школы, классы, назначение учителя и привязка ученика.
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
        if (!res.ok) {
            const detail = data.detail;
            throw new Error(typeof detail === 'string' ? detail : 'Не получилось');
        }
        return data;
    }

    let board = { schools: [], classes: [] };

    function schoolOptions(selected) {
        return board.schools.map((row) =>
            `<option value="${row.id}"${row.id === selected ? ' selected' : ''}>${esc(row.name)}</option>`
        ).join('');
    }

    function classOptions() {
        return board.classes.map((row) => {
            const school = board.schools.find((item) => item.id === row.school_id);
            const teacher = row.teacher_name ? ' · ' + row.teacher_name : '';
            return `<option value="${row.id}">${esc((school ? school.name + ' · ' : '') + row.name + teacher)}</option>`;
        }).join('');
    }

    function render(users) {
        const root = document.getElementById('adminRoot');
        if (!root) return;
        const classRows = board.classes.length
            ? board.classes.map((row) => {
                const school = board.schools.find((item) => item.id === row.school_id);
                return `<tr><td>${esc(school ? school.name : '—')}</td><td>${esc(row.name)}</td><td>${esc(row.teacher_name || 'не назначен')}</td></tr>`;
            }).join('')
            : '<tr><td colspan="3">Классов пока нет</td></tr>';
        const userRows = (users || []).map((row) =>
            `<tr><td>${esc(row.name)}</td><td>${esc(row.username || '')}</td><td>${esc(row.role)}</td></tr>`
        ).join('') || '<tr><td colspan="3">Никого не нашли</td></tr>';
        root.innerHTML = `
            <article class="school-card">
                <h3>Новая школа</h3>
                <form id="schoolForm" class="school-search">
                    <input id="schoolName" placeholder="Название" required>
                    <input id="schoolCity" placeholder="Город">
                    <button class="school-btn" type="submit">Создать</button>
                </form>
                <p id="schoolMsg" class="school-note"></p>
            </article>
            <article class="school-card">
                <h3>Класс и учитель</h3>
                <form id="classForm" class="school-search">
                    <select id="classSchool" required>${schoolOptions() || '<option value="">Сначала создайте школу</option>'}</select>
                    <input id="className" placeholder="Название класса" required>
                    <input id="classTeacher" placeholder="Логин учителя">
                    <button class="school-btn" type="submit">Создать класс</button>
                </form>
                <p id="classMsg" class="school-note"></p>
                <table class="school-table">
                    <thead><tr><th>Школа</th><th>Класс</th><th>Учитель</th></tr></thead>
                    <tbody>${classRows}</tbody>
                </table>
            </article>
            <article class="school-card">
                <h3>Привязать пользователя</h3>
                <p class="school-note">Учитель получает класс и школу. Ученик попадает к учителю этого класса.</p>
                <form id="assignForm" class="school-search">
                    <input id="assignLogin" placeholder="Логин" required>
                    <select id="assignRole">
                        <option value="teacher">Учитель</option>
                        <option value="student">Ученик</option>
                    </select>
                    <select id="assignClass">${classOptions() || '<option value="">Нет классов</option>'}</select>
                    <button class="school-btn" type="submit">Назначить</button>
                </form>
                <p id="assignMsg" class="school-note"></p>
            </article>
            <article class="school-card">
                <h3>Пользователи</h3>
                <form id="userSearch" class="school-search">
                    <input id="userQuery" placeholder="Имя или логин">
                    <button class="school-btn ghost" type="submit">Найти</button>
                </form>
                <table class="school-table">
                    <thead><tr><th>Имя</th><th>Логин</th><th>Роль</th></tr></thead>
                    <tbody>${userRows}</tbody>
                </table>
            </article>`;
        bind();
    }

    function bind() {
        document.getElementById('schoolForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const msg = document.getElementById('schoolMsg');
            try {
                await api('/admin/schools', {
                    method: 'POST',
                    body: JSON.stringify({
                        name: document.getElementById('schoolName').value.trim(),
                        city: document.getElementById('schoolCity').value.trim(),
                    }),
                });
                msg.textContent = 'Школа создана.';
                await boot();
            } catch (error) {
                msg.textContent = error.message;
            }
        });
        document.getElementById('classForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const msg = document.getElementById('classMsg');
            try {
                await api('/admin/classes', {
                    method: 'POST',
                    body: JSON.stringify({
                        school_id: Number(document.getElementById('classSchool').value),
                        name: document.getElementById('className').value.trim(),
                        teacher_username: document.getElementById('classTeacher').value.trim(),
                    }),
                });
                msg.textContent = 'Класс создан.';
                await boot();
            } catch (error) {
                msg.textContent = error.message;
            }
        });
        document.getElementById('assignForm').addEventListener('submit', async (event) => {
            event.preventDefault();
            const msg = document.getElementById('assignMsg');
            const classId = Number(document.getElementById('assignClass').value);
            const klass = board.classes.find((row) => row.id === classId);
            try {
                const saved = await api('/admin/assign', {
                    method: 'POST',
                    body: JSON.stringify({
                        username: document.getElementById('assignLogin').value.trim(),
                        role: document.getElementById('assignRole').value,
                        class_id: classId || null,
                        school_id: klass ? klass.school_id : null,
                    }),
                });
                msg.textContent = saved.name + ' теперь ' + (saved.role === 'teacher' ? 'учитель' : 'ученик') + '.';
                await boot(document.getElementById('userQuery') ? document.getElementById('userQuery').value : '');
            } catch (error) {
                msg.textContent = error.message;
            }
        });
        document.getElementById('userSearch').addEventListener('submit', async (event) => {
            event.preventDefault();
            const users = await api('/admin/users?q=' + encodeURIComponent(document.getElementById('userQuery').value.trim()));
            render(users.users || []);
        });
    }

    async function boot(query) {
        board = await api('/admin/board');
        const users = await api('/admin/users?q=' + encodeURIComponent(query || ''));
        render(users.users || []);
    }

    document.addEventListener('DOMContentLoaded', async () => {
        const root = document.getElementById('adminRoot');
        try {
            const me = await api('/school/me');
            if (me.role !== 'admin') {
                if (root) root.innerHTML = `
                    <article class="school-card">
                        <h3>Вход администратора</h3>
                        <p class="school-note">Консоль видна только администратору.</p>
                        <form id="adminLogin" class="school-search">
                            <input id="adminUser" placeholder="Логин" autocomplete="username" required>
                            <input id="adminPass" type="password" placeholder="Пароль" autocomplete="current-password" required>
                            <button class="school-btn" type="submit">Войти</button>
                        </form>
                        <p id="adminLoginMsg" class="school-note"></p>
                    </article>`;
                document.getElementById('adminLogin').addEventListener('submit', async (event) => {
                    event.preventDefault();
                    const msg = document.getElementById('adminLoginMsg');
                    msg.textContent = 'Вхожу...';
                    try {
                        const origin = (window.ModelService && ModelService._origin) ? ModelService._origin() : location.origin;
                        const res = await fetch(origin + '/api/v1/auth/login', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                username: document.getElementById('adminUser').value.trim(),
                                password: document.getElementById('adminPass').value,
                            }),
                        });
                        const data = await res.json().catch(() => ({}));
                        if (!res.ok) throw new Error(data.detail || 'Неверный логин или пароль');
                        localStorage.setItem('beztel_token', data.access_token);
                        location.reload();
                    } catch (error) {
                        msg.textContent = error.message;
                    }
                });
                return;
            }
            await boot();
        } catch (error) {
            if (root) root.innerHTML = `<article class="school-card"><p>${esc(error.message)}</p></article>`;
        }
    });
})();
