/**
 * БЕЗТЕЛ — Единый контроллер для всех разделов приложения.
 * Интеграция с бэкендом: /api/v1
 */
const ModelService = {
    BASE_URL: '/api/v1',
    sessionExportBuffer: [],
    _history: [],
    _clientId: null,
    _uiLang: localStorage.getItem('beztel_ui_lang') || 'ru',
    _chatLang: localStorage.getItem('beztel_chat_lang') || 'ru',
    _targetLang: localStorage.getItem('beztel_chat_lang') || 'ru',
    _langPairs: [],

    _tgHeaders() {
        const tg = window.Telegram && window.Telegram.WebApp;
        const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
        const h = {};
        if (user) {
            h['X-Telegram-Id'] = String(user.id);
            h['X-Telegram-Name'] = user.first_name || '';
        }
        if (!this._clientId) {
            try { this._clientId = sessionStorage.getItem('beztel_pvp_client_id'); } catch (e) {}
            if (!this._clientId) {
                this._clientId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : (String(Math.random()).slice(2) + Date.now());
                try { sessionStorage.setItem('beztel_pvp_client_id', this._clientId); } catch (e) {}
            }
        }
        h['X-Client-Id'] = this._clientId;
        return h;
    },

    _origin() {
        return window.location.origin;
    },

    async _get(path) {
        const res = await fetch(this.BASE_URL + path, { headers: this._tgHeaders() });
        if (!res.ok) throw new Error('API error ' + res.status);
        return res.json();
    },

    async _post(path, body) {
        const res = await fetch(this.BASE_URL + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...this._tgHeaders() },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('API error ' + res.status);
        return res.json();
    },

    // ---------- Хаб ----------
    async fetchHubDailyInsight() {
        return this._get('/hub/insight');
    },

    // ---------- Чат ----------
    async sendChatMessage(text, history) {
        const res = await this._post('/chat/message', { text, history: history || [], target_lang: this._targetLang });
        this._history.push({ role: 'user', content: text });
        this._history.push({ role: 'assistant', content: res.bashkir_reply });
        if (res.audio_url) this._playAudio(res.audio_url);
        return res;
    },

    async fetchLangPairs() {
        return this._get('/lang-pairs');
    },

    async sendVoiceAudio(audioBlob) {
        if (!audioBlob) return null;
        const form = new FormData();
        form.append('file', audioBlob, 'voice.wav');
        const res = await fetch(this.BASE_URL + '/chat/voice', {
            method: 'POST',
            headers: this._tgHeaders(),
            body: form,
        });
        if (!res.ok) throw new Error('API error ' + res.status);
        const data = await res.json();
        this._history.push({ role: 'user', content: data.recognized_text || '🎤 голосовое сообщение' });
        this._history.push({ role: 'assistant', content: data.bashkir_reply });
        if (data.audio_url) this._playAudio(data.audio_url);
        return data;
    },

    _playAudio(url) {
        try {
            const full = url.startsWith('http') ? url : this._origin() + url;
            const audio = new Audio(full);
            audio.play().catch(() => {});
            return audio;
        } catch (e) {
            return null;
        }
    },

    // ---------- Изучение ----------
    async fetchNextCard() {
        const card = await this._get('/cards/next');
        this._currentCard = card;
        this.sessionExportBuffer.push({ bashkir: card.word_bashkir, russian: card.translation_ru });
        return card;
    },

    async answerCard(know) {
        if (!this._currentCard) return null;
        try {
            return await this._post('/cards/answer', { fragment_id: this._currentCard.fragment_id, know });
        } catch (e) {
            return null;
        }
    },

    async fetchThemes() {
        return this._get('/themes');
    },

    // ---------- Дейлик ----------
    async fetchDailyTask() {
        return this._get('/daily/task');
    },

    async checkUserCorrection(bashkirText, originalProposed, userCorrectedTranslation) {
        return this._post('/daily/check', {
            bashkir_text: bashkirText,
            original_proposed: originalProposed,
            user_corrected: userCorrectedTranslation,
        });
    },

    async submitDailyVote(isApprovedByUser) {
        return this._post('/daily/vote', { approved: !!isApprovedByUser });
    },

    async fetchDailyTasks() {
        return this._get('/daily/tasks');
    },

    async dailyApprove(bashkirText, proposed) {
        return this._post('/daily/check', {
            bashkir_text: bashkirText,
            original_proposed: proposed,
            approved: true,
        });
    },

    // ---------- Состязания ----------
    async fetchBattlePrompt(mode = 'sprint') {
        return this._get('/battles/prompt?mode=' + mode);
    },

    async speakText(text) {
        try {
            const res = await fetch(this._origin() + '/api/speech/tts?text=' + encodeURIComponent(text));
            if (!res.ok) return;
            const data = await res.json();
            if (data && data.url) this._playAudio(data.url);
        } catch (e) {}
    },

    // ---------- Профиль ----------
    async fetchProfile() {
        return this._get('/profile');
    },

    async fetchExportBatch(count = 20) {
        return this._get('/cards/batch?count=' + count);
    },

    async pvpFind() {
        return this._post('/pvp/find', {});
    },
    async pvpStatus() {
        return this._get('/pvp/status');
    },
    async pvpCancel() {
        return this._post('/pvp/cancel', {});
    },
    async pvpProgress(index, score, done) {
        return this._post('/pvp/progress', { index: index || 0, score: score || 0, done: !!done });
    },
    async awardXp(amount, reason) {
        return this._post('/xp/award', { amount: amount || 0, reason: reason || '' });
    },
    async sprintFinish(score) {
        return this._post('/sprint/finish', { score: score || 0 });
    },
    async fetchLeaderboard() {
        const res = await fetch(this._origin() + '/api/leaderboard/users?limit=50', { headers: this._tgHeaders() });
        if (!res.ok) throw new Error('API error ' + res.status);
        return res.json();
    },

    setUiLang(lang) {
        this._uiLang = lang || 'ru';
        try { localStorage.setItem('beztel_ui_lang', this._uiLang); } catch (e) {}
        document.documentElement.lang = this._uiLang;
    },
    setChatLang(lang) {
        this._chatLang = lang || 'ru';
        this._targetLang = this._chatLang;
        try { localStorage.setItem('beztel_chat_lang', this._chatLang); } catch (e) {}
    },
};

// ---------------------------------------------------------------------------
// Утилиты
// ---------------------------------------------------------------------------
function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function webmToWav(blob) {
    const arrayBuf = await blob.arrayBuffer();
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) throw new Error('AudioContext не поддерживается');
    const audioCtx = new AudioCtx();
    let decoded;
    try {
        decoded = await audioCtx.decodeAudioData(arrayBuf);
    } finally {
        try { await audioCtx.close(); } catch (e) {}
    }
    if (!decoded) throw new Error('Не удалось декодировать аудио');
    const targetRate = 16000;
    const ratio = targetRate / decoded.sampleRate;
    const length = Math.floor(decoded.duration * targetRate);
    const offline = new OfflineAudioContext(1, Math.max(1, length), targetRate);
    const src = offline.createBufferSource();
    src.buffer = decoded;
    src.connect(offline.destination);
    src.start();
    const rendered = await offline.startRendering();
    const samples = rendered.getChannelData(0);

    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeStr = (offset, str) => {
        for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, targetRate, true);
    view.setUint32(28, targetRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        offset += 2;
    }
    return new Blob([buffer], { type: 'audio/wav' });
}

async function updateHeaderStats() {
    try {
        const profile = await ModelService.fetchProfile();
        document.querySelectorAll('#headerStreak').forEach((el) => {
            el.textContent = `${profile.streak} 🔥`;
        });
        return profile;
    } catch (e) {
        return null;
    }
}

// ---------------------------------------------------------------------------
// Инициализация
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
    const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    const currentPage = document.body.getAttribute('data-page');
    let firstName = 'Ученик';

    // Приветственная страница
    if (currentPage === 'welcome') {
        const startBtn = document.getElementById('startLearningBtn');
        if (startBtn) {
            startBtn.addEventListener('click', () => {
                if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
            });
        }
    }

    // Авторизация через Telegram
    if (tg) {
        tg.ready();
        tg.expand();
        if (typeof tg.setHeaderColor === 'function') tg.setHeaderColor('#111714');
        if (typeof tg.setBackgroundColor === 'function') tg.setBackgroundColor('#0B0F0D');

        const user = tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user : null;
        if (user) {
            firstName = user.first_name || 'Ученик';
            const userNameEl = document.getElementById('userName');
            const avatarFallbackEl = document.getElementById('avatarFallback');
            if (userNameEl) userNameEl.textContent = firstName;
            if (avatarFallbackEl) avatarFallbackEl.textContent = firstName[0].toUpperCase();
            if (user.photo_url) {
                const avatarEl = document.getElementById('userAvatar');
                if (avatarEl) {
                    avatarEl.src = user.photo_url;
                    avatarEl.classList.remove('hidden');
                }
                if (avatarFallbackEl) avatarFallbackEl.classList.add('hidden');
            }
        }
    }
    document.querySelectorAll('#userName').forEach((el) => { el.textContent = firstName; });

    // Мобильное меню
    const appSidebar = document.getElementById('appSidebar');
    const drawerBackdrop = document.getElementById('drawerBackdrop');
    const openDrawerBtn = document.getElementById('openDrawerBtn');
    const closeDrawerBtn = document.getElementById('closeDrawerBtn');
    if (openDrawerBtn) openDrawerBtn.addEventListener('click', () => {
        appSidebar.classList.add('open');
        drawerBackdrop.classList.remove('hidden');
    });
    function closeDrawer() {
        if (appSidebar) appSidebar.classList.remove('open');
        if (drawerBackdrop) drawerBackdrop.classList.add('hidden');
    }
    if (closeDrawerBtn) closeDrawerBtn.addEventListener('click', closeDrawer);
    if (drawerBackdrop) drawerBackdrop.addEventListener('click', closeDrawer);

    // Применяем сохранённый язык интерфейса
    ModelService.setUiLang(ModelService._uiLang);

    // Общая статистика в шапке
    await updateHeaderStats();

    // ---------- ХАБ ----------
    if (currentPage === 'hub') {
        async function loadDailyTasks() {
            const slot = document.getElementById('dailyTasksSlot');
            if (!slot) return;
            try {
                const tasks = await ModelService.fetchDailyTasks();
                slot.classList.remove('empty-slot-box');
                slot.innerHTML = tasks.map((t) => `
                    <div class="ach-row">
                        <span>${t.completed ? '✓' : '○'}</span>
                        <div>
                            <strong>${escapeHtml(t.title)}</strong>
                            <p>${t.progress}/${t.target} • ${t.xp_reward} XP</p>
                        </div>
                    </div>`).join('');
            } catch (e) {
                slot.innerHTML = '<p>Не удалось загрузить задания.</p>';
            }
        }
        loadDailyTasks();

        const heroUserName = document.getElementById('heroUserName');
        if (heroUserName) heroUserName.textContent = firstName;
        try {
            const insight = await ModelService.fetchHubDailyInsight();
            document.getElementById('hubInsightBashkir').textContent = insight.bashkir_phrase;
            document.getElementById('hubInsightTranslation').textContent = insight.translation_ru;
            document.getElementById('hubInsightContext').textContent = insight.cultural_note;
        } catch (e) {}
        // только слово дня; профиль/статистика убраны с хаба
    }

    // ---------- ЧАТ ----------
    if (currentPage === 'chat') {
        const chatForm = document.getElementById('chatForm');
        const chatTextInput = document.getElementById('chatTextInput');
        const chatMessagesStream = document.getElementById('chatMessagesStream');
        const micToggleBtn = document.getElementById('micToggleBtn');
        const voiceRecordingBar = document.getElementById('voiceRecordingBar');
        let mediaRecorder = null;
        let chunks = [];
        let thinkingBubble = null;

        // ---------- Язык перевода ----------
        const langSelect = document.getElementById('chatLangSelect');
        async function loadLangPairs() {
            try {
                const pairs = await ModelService.fetchLangPairs();
                // оставим только пары с башкирским источником, отсортируем
                const baPairs = pairs.filter(p => p.source_lang === 'ba');
                const byCode = { ru: '🇷🇺 Русский', kk: '🇰🇿 Қазақша', zh: '🇨🇳 中文' };
                langSelect.innerHTML = baPairs.map(p => {
                    const label = byCode[p.target_lang] || p.native_label || p.code;
                    const selected = p.target_lang === ModelService._targetLang ? 'selected' : '';
                    return `<option value="${p.target_lang}" ${selected}>${label}</option>`;
                }).join('');
                langSelect.value = ModelService._targetLang;
            } catch (e) {
                // оставим дефолтные option из HTML
            }
        }
        loadLangPairs();

        langSelect.addEventListener('change', () => {
            ModelService.setChatLang(langSelect.value);
        });
        // синхронизируем с сохранённым выбором
        try { langSelect.value = ModelService._targetLang; } catch (e) {}

        function showThinking() {
            thinkingBubble = appendBubble('думаю...', 'model');
            thinkingBubble.classList.add('thinking');
            return thinkingBubble;
        }
        function hideThinking() {
            if (thinkingBubble) { thinkingBubble.remove(); thinkingBubble = null; }
        }

        function buildAudioPlayer(url) {
            if (!url) return null;
            const origin = ModelService._origin();
            const full = url.startsWith('http') ? url : origin + url;
            const wrap = document.createElement('div');
            wrap.className = 'audio-player';

            const audio = document.createElement('audio');
            audio.src = full;
            audio.preload = 'metadata';
            wrap.appendChild(audio);

            const progress = document.createElement('div');
            progress.className = 'audio-progress';
            const bar = document.createElement('div');
            bar.className = 'audio-bar';
            progress.appendChild(bar);
            progress.addEventListener('click', (e) => {
                if (!audio.duration) return;
                const rect = progress.getBoundingClientRect();
                const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                audio.currentTime = ratio * audio.duration;
            });
            wrap.appendChild(progress);

            const controls = document.createElement('div');
            controls.className = 'audio-controls';

            const fmt = (t) => {
                if (!isFinite(t) || t < 0) t = 0;
                const m = Math.floor(t / 60);
                const s = Math.floor(t % 60);
                return `${m}:${String(s).padStart(2, '0')}`;
            };

            const playBtn = document.createElement('button');
            playBtn.className = 'audio-btn audio-play';
            playBtn.type = 'button';
            playBtn.textContent = '▶';
            playBtn.addEventListener('click', () => {
                if (audio.paused) { audio.play().catch(() => {}); playBtn.textContent = '⏸'; }
                else { audio.pause(); playBtn.textContent = '▶'; }
            });
            audio.addEventListener('ended', () => { playBtn.textContent = '▶'; });
            controls.appendChild(playBtn);

            const backBtn = document.createElement('button');
            backBtn.className = 'audio-btn';
            backBtn.type = 'button';
            backBtn.textContent = '⏪';
            backBtn.title = 'Назад 5 сек';
            backBtn.addEventListener('click', () => { audio.currentTime = Math.max(0, audio.currentTime - 5); });
            controls.appendChild(backBtn);

            const fwdBtn = document.createElement('button');
            fwdBtn.className = 'audio-btn';
            fwdBtn.type = 'button';
            fwdBtn.textContent = '⏩';
            fwdBtn.title = 'Вперёд 5 сек';
            fwdBtn.addEventListener('click', () => { audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 5); });
            controls.appendChild(fwdBtn);

            const time = document.createElement('span');
            time.className = 'audio-time';
            time.textContent = '0:00 / 0:00';
            controls.appendChild(time);

            const speedLabel = document.createElement('span');
            speedLabel.className = 'audio-speed-label';
            speedLabel.textContent = 'Скорость';
            controls.appendChild(speedLabel);

            const speedSelect = document.createElement('select');
            speedSelect.className = 'audio-speed';
            [0.5, 0.75, 1, 1.25, 1.5, 2].forEach((s) => {
                const opt = document.createElement('option');
                opt.value = String(s);
                opt.textContent = s + '×';
                if (s === 1) opt.selected = true;
                speedSelect.appendChild(opt);
            });
            speedSelect.addEventListener('change', () => { audio.playbackRate = parseFloat(speedSelect.value); });
            controls.appendChild(speedSelect);

            audio.addEventListener('timeupdate', () => {
                const pct = audio.duration ? (audio.currentTime / audio.duration * 100) : 0;
                bar.style.width = pct + '%';
                time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
            });
            audio.addEventListener('loadedmetadata', () => {
                time.textContent = `${fmt(audio.currentTime)} / ${fmt(audio.duration)}`;
            });

            wrap.appendChild(controls);
            return wrap;
        }

        function appendBubble(text, sender = 'user', audioUrl = null) {
            const emptyBox = chatMessagesStream.querySelector('.empty-slot-box');
            if (emptyBox) emptyBox.remove();
            const div = document.createElement('div');
            div.className = `chat-bubble ${sender === 'user' ? 'user-msg' : 'model-msg'}`;
            const textEl = document.createElement('div');
            textEl.className = 'bubble-text';
            textEl.style.whiteSpace = 'pre-line';
            textEl.textContent = text;
            div.appendChild(textEl);
            if (sender !== 'user' && audioUrl) {
                div.appendChild(buildAudioPlayer(audioUrl));
            }
            chatMessagesStream.appendChild(div);
            chatMessagesStream.scrollTop = chatMessagesStream.scrollHeight;
            return div;
        }

        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const text = chatTextInput.value.trim();
            if (!text) return;
            appendBubble(text, 'user');
            chatTextInput.value = '';
            try {
                const thinking = showThinking();
                const res = await ModelService.sendChatMessage(text, ModelService._history.slice(-10));
                hideThinking();
                appendBubble(`${res.bashkir_reply}\n(${res.russian_translation || ''})`, 'model', res.audio_url);
            } catch (err) {
                hideThinking();
                appendBubble('[Ошибка соединения с сервером]', 'model');
            }
        });

        micToggleBtn.addEventListener('click', async () => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                micToggleBtn.classList.remove('recording');
                micToggleBtn.textContent = '🎙️';
                voiceRecordingBar.classList.add('hidden');
                return;
            }
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                chunks = [];
                const mime = (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported('audio/webm;codecs=opus'))
                    ? 'audio/webm;codecs=opus'
                    : ((MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported('audio/webm')) ? 'audio/webm' : '');
                mediaRecorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
                const recordedType = mediaRecorder.mimeType || mime || 'audio/webm';
                mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
                mediaRecorder.onstop = async () => {
                    stream.getTracks().forEach((t) => t.stop());
                    try {
                        if (!chunks.length) {
                            appendBubble('[Нет аудиоданных]', 'model');
                            return;
                        }
                        const blob = new Blob(chunks, { type: recordedType });
                        let wav = blob;
                        if (!/wav/i.test(recordedType)) {
                            wav = await webmToWav(blob);
                        }
                        const thinking = showThinking();
                        const res = await ModelService.sendVoiceAudio(wav);
                        hideThinking();
                        if (res) {
                            if (res.recognized_text) {
                                appendBubble(res.recognized_text, 'user');
                            }
                            appendBubble(`${res.bashkir_reply}\n(${res.russian_translation || ''})`, 'model', res.audio_url);
                        } else {
                            appendBubble('[Голос не распознан]', 'model');
                        }
                    } catch (err) {
                        hideThinking();
                        appendBubble('[Ошибка распознавания голоса]', 'model');
                    }
                };
                mediaRecorder.start();
                micToggleBtn.classList.add('recording');
                micToggleBtn.textContent = '⏹';
                voiceRecordingBar.classList.remove('hidden');
            } catch (err) {
                alert('Микрофон недоступен: ' + err.message);
            }
        });
    }

    // ---------- ИЗУЧЕНИЕ: карта уровней ----------
    if (currentPage === 'study') {
        // План уровней: 5 слов на уровень, сложность растёт от «Знакомства» к культуре.
        const STUDY_KEY = 'beztel_study_progress_v1';
        const LEVELS = [
            {
                id: 1,
                title: 'Знакомство',
                words: [
                    { ba: 'сәләм', ru: 'привет', tr: 'säläm' },
                    { ba: 'рәхмәт', ru: 'спасибо', tr: 'räxmät' },
                    { ba: 'әйе', ru: 'да', tr: 'äye' },
                    { ba: 'юҡ', ru: 'нет', tr: 'yuq' },
                    { ba: 'һау бул', ru: 'до свидания', tr: 'haw bul' },
                ],
            },
            {
                id: 2,
                title: 'Семья',
                words: [
                    { ba: 'мин', ru: 'я', tr: 'min' },
                    { ba: 'һин', ru: 'ты', tr: 'hin' },
                    { ba: 'әсәй', ru: 'мама', tr: 'äsäy' },
                    { ba: 'атай', ru: 'папа', tr: 'atay' },
                    { ba: 'ғаилә', ru: 'семья', tr: 'ğailä' },
                ],
            },
            {
                id: 3,
                title: 'Природа',
                words: [
                    { ba: 'һыу', ru: 'вода', tr: 'hıw' },
                    { ba: 'ут', ru: 'огонь', tr: 'ut' },
                    { ba: 'ер', ru: 'земля', tr: 'yer' },
                    { ba: 'күк', ru: 'небо', tr: 'kük' },
                    { ba: 'ҡояш', ru: 'солнце', tr: 'qoyaş' },
                ],
            },
            {
                id: 4,
                title: 'Животные',
                words: [
                    { ba: 'эт', ru: 'собака', tr: 'et' },
                    { ba: 'бесәй', ru: 'кошка', tr: 'besäy' },
                    { ba: 'ат', ru: 'лошадь', tr: 'at' },
                    { ba: 'ҡош', ru: 'птица', tr: 'qoş' },
                    { ba: 'балыҡ', ru: 'рыба', tr: 'balıq' },
                ],
            },
            {
                id: 5,
                title: 'Еда',
                words: [
                    { ba: 'икмәк', ru: 'хлеб', tr: 'ikmäk' },
                    { ba: 'һөт', ru: 'молоко', tr: 'höt' },
                    { ba: 'сәй', ru: 'чай', tr: 'säy' },
                    { ba: 'бал', ru: 'мёд', tr: 'bal' },
                    { ba: 'алма', ru: 'яблоко', tr: 'alma' },
                ],
            },
            {
                id: 6,
                title: 'Движение',
                words: [
                    { ba: 'беләм', ru: 'знаю', tr: 'beläm' },
                    { ba: 'яратам', ru: 'люблю', tr: 'yaratam' },
                    { ba: 'барам', ru: 'иду', tr: 'baram' },
                    { ba: 'киләм', ru: 'прихожу', tr: 'kiläm' },
                    { ba: 'уҡыйым', ru: 'читаю', tr: 'uqıyım' },
                ],
            },
            {
                id: 7,
                title: 'Признаки',
                words: [
                    { ba: 'ҙур', ru: 'большой', tr: 'źur' },
                    { ba: 'бәләкәй', ru: 'маленький', tr: 'bäläkäy' },
                    { ba: 'яҡшы', ru: 'хороший', tr: 'yaqşı' },
                    { ba: 'матур', ru: 'красивый', tr: 'matur' },
                    { ba: 'яңы', ru: 'новый', tr: 'yañı' },
                ],
            },
            {
                id: 8,
                title: 'Культура',
                words: [
                    { ba: 'дуҫ', ru: 'друг', tr: 'duś' },
                    { ba: 'ил', ru: 'страна', tr: 'il' },
                    { ba: 'тел', ru: 'язык', tr: 'tel' },
                    { ba: 'йыр', ru: 'песня', tr: 'yır' },
                    { ba: 'бәхет', ru: 'счастье', tr: 'bäxet' },
                ],
            },
        ];

        const trail = document.getElementById('levelTrail');
        const modal = document.getElementById('studyModal');
        const gameBox = document.getElementById('studyGame');
        const resultBox = document.getElementById('studyResult');
        const optionsBox = document.getElementById('studyOptions');
        const feedbackEl = document.getElementById('studyFeedback');
        const progressFill = document.getElementById('studyProgressFill');
        const sessionTitle = document.getElementById('studySessionTitle');
        const sessionKicker = document.getElementById('studySessionKicker');
        const sessionHint = document.getElementById('studySessionHint');
        const retryBtn = document.getElementById('studyRetryBtn');
        const nextBtn = document.getElementById('studyNextBtn');
        const backBtn = document.getElementById('studyBackBtn');
        const closeBtn = document.getElementById('studyCloseBtn');
        const groundhogTpl = document.getElementById('groundhogTemplate');

        if (!trail || !modal) return;

        let profileKnown = 0;
        let session = null;
        let lastLevelIndex = 0;
        let advanceTimer = null;

        function loadProgress() {
            let data = {};
            try { data = JSON.parse(localStorage.getItem(STUDY_KEY) || '{}'); } catch (e) {}
            const stars = {};
            const rawStars = data && data.stars && typeof data.stars === 'object' ? data.stars : {};
            Object.keys(rawStars).forEach((key) => {
                const value = Number(rawStars[key]);
                if (Number.isFinite(value) && value > 0) stars[key] = Math.min(3, Math.floor(value));
            });
            return {
                stars,
                known: Array.isArray(data.known) ? data.known.filter((w) => typeof w === 'string') : [],
            };
        }

        const progress = loadProgress();

        function saveProgress() {
            try { localStorage.setItem(STUDY_KEY, JSON.stringify(progress)); } catch (e) {}
        }

        function shuffle(list) {
            const copy = list.slice();
            for (let i = copy.length - 1; i > 0; i -= 1) {
                const j = Math.floor(Math.random() * (i + 1));
                [copy[i], copy[j]] = [copy[j], copy[i]];
            }
            return copy;
        }

        const starsOf = (level) => Math.min(3, Math.max(0, Number(progress.stars[level.id]) || 0));
        const knownCount = () => Math.max(progress.known.length, profileKnown);
        const totalStars = () => LEVELS.reduce((sum, level) => sum + starsOf(level), 0);
        const completedCount = () => LEVELS.filter((level) => starsOf(level) > 0).length;
        const unlockedCount = () => Math.max(
            1,
            Math.min(LEVELS.length, 1 + completedCount() + Math.floor(knownCount() / 10))
        );

        function firstPlayableIndex() {
            const limit = unlockedCount();
            for (let i = 0; i < limit; i += 1) {
                if (starsOf(LEVELS[i]) === 0) return i;
            }
            for (let i = 0; i < limit; i += 1) {
                if (starsOf(LEVELS[i]) < 3) return i;
            }
            return -1;
        }

        function stateFor(index) {
            const stars = starsOf(LEVELS[index]);
            if (stars >= 3) return 'done';
            if (index >= unlockedCount()) return 'locked';
            if (index === firstPlayableIndex()) return 'current';
            return stars > 0 ? 'replay' : 'open';
        }

        function pluralWords(n) {
            const abs = Math.abs(n) % 100;
            const last = abs % 10;
            if (abs > 10 && abs < 20) return 'слов';
            if (last === 1) return 'слово';
            if (last >= 2 && last <= 4) return 'слова';
            return 'слов';
        }

        function tierFor(known) {
            if (known >= 30) return 'СТУПЕНЬ B1';
            if (known >= 20) return 'СТУПЕНЬ A2+';
            if (known >= 10) return 'СТУПЕНЬ A2';
            if (known >= 5) return 'СТУПЕНЬ A1+';
            return 'СТУПЕНЬ A1';
        }

        function updateStats() {
            const known = knownCount();
            const knownEl = document.getElementById('studyKnownWords');
            const starsEl = document.getElementById('studyTotalStars');
            const maxEl = document.getElementById('studyStarsMax');
            const tierEl = document.getElementById('studyTierLabel');
            const hintEl = document.getElementById('levelMapHint');
            if (knownEl) knownEl.textContent = String(known);
            if (starsEl) starsEl.textContent = String(totalStars());
            if (maxEl) maxEl.textContent = String(LEVELS.length * 3);
            if (tierEl) tierEl.textContent = `${tierFor(known)} · ${known} ${pluralWords(known)}`;
            if (hintEl) {
                const open = unlockedCount();
                hintEl.textContent = open >= LEVELS.length
                    ? 'Все уровни открыты. Осталось собрать звёзды!'
                    : `Открыто ${open} из ${LEVELS.length}. Сурок выглядывает из доступного уровня.`;
            }
        }

        function renderMap() {
            const groundhog = groundhogTpl ? groundhogTpl.innerHTML : '';
            const currentIndex = firstPlayableIndex();
            trail.innerHTML = LEVELS.map((level, index) => {
                const state = stateFor(index);
                const stars = starsOf(level);
                const playable = state === 'current' || state === 'open' || state === 'replay';
                const groundhogMarkup = playable
                    ? `<span class="groundhog ${state === 'current' ? 'groundhog--hero' : 'groundhog--peek'}" aria-hidden="true">${groundhog}</span>`
                    : '';
                const planks = state === 'done'
                    ? '<span class="mound-planks" aria-hidden="true"><i></i><i></i></span>'
                    : '';
                const closure = state === 'locked'
                    ? '<span class="mound-lock" aria-hidden="true"></span>'
                    : '<span class="mound-hole" aria-hidden="true"></span>';
                const starsMarkup = [0, 1, 2]
                    .map((n) => `<span class="level-star ${n < stars ? 'is-on' : ''}"></span>`)
                    .join('');
                const number = String(level.id).padStart(2, '0');
                let meta = '5 слов';
                if (state === 'current') meta = 'сейчас';
                else if (state === 'replay') meta = 'перепройти';
                else if (state === 'done') meta = 'закрыто';
                else if (state === 'locked') meta = 'впереди';

                let label = `${number} ${level.title}, доступно, 5 слов`;
                if (state === 'done') label = `${number} ${level.title}, закрыто дощечками, 3 из 3 звёзд`;
                else if (state === 'locked') label = `${number} ${level.title}, впереди, закрыто`;
                else if (stars > 0) label = `${number} ${level.title}, перепройти, ${stars} из 3 звёзд`;
                else if (state === 'current') label = `${number} ${level.title}, сейчас, играть`;

                return `<button type="button" class="level-node level-node--${state}" data-level="${index}"${playable ? '' : ' aria-disabled="true"'} aria-label="${escapeHtml(label)}">
                    <span class="mound mound--${state}">${closure}${groundhogMarkup}${planks}</span>
                    <span class="level-label"><span class="level-num">${number}</span> ${escapeHtml(level.title)}</span>
                    <span class="level-stars" aria-hidden="true">${starsMarkup}</span>
                    <span class="level-meta">${meta}</span>
                </button>`;
            }).join('');
            if (currentIndex < 0 && LEVELS.every((level) => starsOf(level) >= 3)) {
                trail.insertAdjacentHTML('beforeend', '<p class="level-trail-done">Все уровни закрыты на 3 звезды. Һау бул, сурок! 🎉</p>');
            }
        }

        function buildOptions(word) {
            const seen = new Set([word.ru]);
            const picks = [];
            const pool = shuffle(LEVELS.reduce((acc, level) => acc.concat(level.words), []));
            for (const candidate of pool) {
                if (picks.length >= 2) break;
                if (seen.has(candidate.ru)) continue;
                seen.add(candidate.ru);
                picks.push(candidate.ru);
            }
            return shuffle([
                { text: word.ru, correct: true },
                ...picks.map((text) => ({ text, correct: false })),
            ]);
        }

        function renderQuestion() {
            const word = session.order[session.index];
            const total = session.order.length;
            sessionTitle.textContent = `Слово ${session.index + 1} из ${total}`;
            document.getElementById('studyWord').textContent = word.ba;
            document.getElementById('studyWordPhonetics').textContent = word.tr;
            progressFill.style.width = `${Math.round((session.index / total) * 100)}%`;
            feedbackEl.textContent = '';
            feedbackEl.className = 'study-feedback';

            optionsBox.innerHTML = '';
            buildOptions(word).forEach((option) => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'study-option';
                button.textContent = option.text;
                button.dataset.correct = option.correct ? '1' : '0';
                button.addEventListener('click', () => chooseOption(button, word));
                optionsBox.appendChild(button);
            });
        }

        function addKnown(word) {
            if (!progress.known.includes(word)) {
                progress.known.push(word);
                saveProgress();
                updateStats();
            }
        }

        function chooseOption(button, word) {
            if (!session || session.answered) return;
            session.answered = true;
            const isCorrect = button.dataset.correct === '1';
            const buttons = Array.from(optionsBox.querySelectorAll('.study-option'));
            buttons.forEach((option) => {
                option.disabled = true;
                if (option.dataset.correct === '1') option.classList.add('is-correct');
            });
            if (isCorrect) {
                session.correct += 1;
                addKnown(word.ba);
                feedbackEl.textContent = 'Дөрөҫ! Верно.';
                feedbackEl.className = 'study-feedback is-good';
            } else {
                button.classList.add('is-wrong');
                feedbackEl.textContent = `Правильный перевод: «${word.ru}»`;
                feedbackEl.className = 'study-feedback is-bad';
            }
            progressFill.style.width = `${Math.round(((session.index + 1) / session.order.length) * 100)}%`;
            clearTimeout(advanceTimer);
            advanceTimer = setTimeout(() => {
                if (!session) return;
                session.index += 1;
                session.answered = false;
                if (session.index >= session.order.length) finishSession();
                else renderQuestion();
            }, 850);
        }

        function finishSession() {
            const correct = session.correct;
            const total = session.order.length;
            const stars = correct >= total ? 3 : correct === total - 1 ? 2 : correct === total - 2 ? 1 : 0;
            const level = session.level;
            const levelIndex = session.levelIndex;
            const previous = starsOf(level);
            progress.stars[level.id] = Math.max(previous, stars);
            saveProgress();
            session = null;
            lastLevelIndex = levelIndex;

            renderMap();
            updateStats();

            const starsBox = document.getElementById('studyResultStars');
            starsBox.innerHTML = [0, 1, 2]
                .map((n) => `<span class="${n < stars ? 'is-on' : ''}">★</span>`)
                .join('');

            const titles = ['Стоит повторить', 'Хорошее начало', 'Ещё чуть-чуть!', 'Норка закрыта!'];
            const texts = [
                'Пока ни одной звезды. Загляните в слова ещё раз — уровень ждёт.',
                'Одна звезда. Перепройдите уровень, чтобы добрать остальные.',
                'Две звезды! Ещё одно повторение — и сурок закроет норку дощечками.',
                'Все 5 слов в кармане. Сурок закрыл норку дощечками — уровень завершён.',
            ];
            document.getElementById('studyResultTitle').textContent = titles[stars];
            document.getElementById('studyResultText').textContent = texts[stars];
            sessionHint.textContent = `Верно: ${correct} из ${total}`;
            progressFill.style.width = '100%';
            sessionTitle.textContent = 'Уровень завершён';

            gameBox.classList.add('hidden');
            resultBox.classList.remove('hidden');
            const nextIndex = findNextPlayable(levelIndex);
            retryBtn.classList.toggle('hidden', stars >= 3);
            nextBtn.classList.toggle('hidden', stars < 3 || nextIndex < 0);

            const xp = stars * 10 + correct * 2;
            if (xp > 0) {
                ModelService.awardXp(xp, 'study_level').catch(() => {});
            }
        }

        function findNextPlayable(fromIndex) {
            for (let i = fromIndex + 1; i < LEVELS.length; i += 1) {
                const state = stateFor(i);
                if (state === 'current' || state === 'open' || state === 'replay') return i;
            }
            return -1;
        }

        function openSession(levelIndex) {
            const state = stateFor(levelIndex);
            if (state !== 'current' && state !== 'open' && state !== 'replay') return;
            clearTimeout(advanceTimer);
            const level = LEVELS[levelIndex];
            lastLevelIndex = levelIndex;
            session = {
                level,
                levelIndex,
                order: shuffle(level.words),
                index: 0,
                correct: 0,
                answered: false,
            };
            sessionKicker.textContent = `УРОВЕНЬ ${level.id} · ${level.title.toUpperCase()}`;
            sessionHint.textContent = 'Выберите правильный перевод.';
            progressFill.style.width = '0%';
            gameBox.classList.remove('hidden');
            resultBox.classList.add('hidden');
            renderQuestion();
            modal.classList.remove('hidden');
            closeBtn.focus();
        }

        function closeSession() {
            clearTimeout(advanceTimer);
            session = null;
            modal.classList.add('hidden');
            const node = trail.querySelector(`.level-node[data-level="${lastLevelIndex}"]`);
            if (node) node.focus();
        }

        trail.addEventListener('click', (event) => {
            const node = event.target.closest('.level-node');
            if (!node) return;
            const index = Number(node.dataset.level);
            const state = stateFor(index);
            if (state === 'done' || state === 'locked') return;
            openSession(index);
        });

        retryBtn.addEventListener('click', () => openSession(lastLevelIndex));
        nextBtn.addEventListener('click', () => {
            const nextIndex = findNextPlayable(lastLevelIndex);
            if (nextIndex >= 0) openSession(nextIndex);
        });
        backBtn.addEventListener('click', closeSession);
        closeBtn.addEventListener('click', closeSession);
        document.getElementById('studyModalBackdrop').addEventListener('click', closeSession);

        document.addEventListener('keydown', (event) => {
            if (modal.classList.contains('hidden')) return;
            if (event.key === 'Escape') {
                event.preventDefault();
                closeSession();
                return;
            }
            if (event.key !== 'Tab') return;
            const focusable = Array.from(modal.querySelectorAll('button:not(:disabled):not(.hidden)'))
                .filter((el) => el.offsetParent !== null);
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });

        renderMap();
        updateStats();

        // Подтягиваем слова из профиля (если бэкенд доступен) — сложность растёт.
        ModelService.fetchProfile().then((profile) => {
            const words = profile && Number(profile.words);
            if (Number.isFinite(words) && words > profileKnown) {
                profileKnown = words;
                renderMap();
                updateStats();
            }
        }).catch(() => {});
    }

    // ---------- ДЕЙЛИК ----------
    if (currentPage === 'daily') {
        const approveBtn = document.getElementById('dailyApproveBtn');
        const rejectBtn = document.getElementById('dailyRejectBtn');
        const correctionBox = document.getElementById('dailyCorrectionBox');
        const correctionInput = document.getElementById('dailyCorrectionInput');
        const submitCorrectionBtn = document.getElementById('submitCorrectionBtn');
        const verdictBox = document.getElementById('correctionVerdictBox');
        let locked = false;


        try {
            const task = await ModelService.fetchDailyTask();
            document.getElementById('dailyBashkirText').textContent = task.bashkir_text;
            document.getElementById('dailyProposedTranslation').textContent = task.proposed_translation;

            const approveBtn = document.getElementById('dailyApproveBtn');
            const rejectBtn = document.getElementById('dailyRejectBtn');
            const correctionBox = document.getElementById('dailyCorrectionBox');
            const verdictBox = document.getElementById('correctionVerdictBox');

            // Если пользователь уже отвечал на дейлик сегодня — показываем результат, а не новый текст
            if (task.answered) {
                approveBtn?.classList.add('hidden');
                rejectBtn?.classList.add('hidden');
                correctionBox?.classList.add('hidden');
                verdictBox?.classList.remove('hidden');
                verdictBox.innerHTML = task.is_correct
                    ? `✓ <strong>Верно!</strong> Ваш ответ: «${escapeHtml(task.user_answer || '')}».`
                    : `✕ <strong>Неточно.</strong> Вы писали: «${escapeHtml(task.user_answer || '')}».`;
                document.getElementById('dailyVotingLocked')?.classList.add('hidden');
                document.getElementById('dailyVotingResults')?.classList.remove('hidden');
                const vs = task.vote_stats || {};
                const truePct = (vs.approvePercent != null) ? vs.approvePercent : 0;
                const falsePct = (vs.rejectPercent != null) ? vs.rejectPercent : 0;
                const trueEl = document.getElementById('voteTruePercent');
                const falseEl = document.getElementById('voteFalsePercent');
                const trueBar = document.getElementById('voteTrueBar');
                const falseBar = document.getElementById('voteFalseBar');
                if (trueEl) trueEl.textContent = `${truePct}%`;
                if (falseEl) falseEl.textContent = `${falsePct}%`;
                if (trueBar) trueBar.style.width = `${truePct}%`;
                if (falseBar) falseBar.style.width = `${falsePct}%`;
            }
        } catch (e) {}

        async function showVotes(vote) {
            const stats = await ModelService.submitDailyVote(vote);
            document.getElementById('dailyVotingLocked').classList.add('hidden');
            document.getElementById('dailyVotingResults').classList.remove('hidden');
            document.getElementById('voteTruePercent').textContent = `${stats.approvePercent}%`;
            document.getElementById('voteFalsePercent').textContent = `${stats.rejectPercent}%`;
            document.getElementById('voteTrueBar').style.width = `${stats.approvePercent}%`;
            document.getElementById('voteFalseBar').style.width = `${stats.rejectPercent}%`;
        }

        approveBtn.addEventListener('click', async () => {
            if (locked) return;
            locked = true;
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            try {
                await ModelService.dailyApprove(
                    document.getElementById('dailyBashkirText').textContent,
                    document.getElementById('dailyProposedTranslation').textContent
                );
            } catch (e) {}
            await showVotes(true);
        });

        rejectBtn.addEventListener('click', () => {
            if (locked) return;
            locked = true;
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            correctionBox.classList.remove('hidden');
            correctionInput.focus();
        });

        submitCorrectionBtn.addEventListener('click', async () => {
            const val = correctionInput.value.trim();
            if (!val) return;
            correctionInput.disabled = true;
            submitCorrectionBtn.disabled = true;
            try {
                const res = await ModelService.checkUserCorrection(
                    document.getElementById('dailyBashkirText').textContent,
                    document.getElementById('dailyProposedTranslation').textContent,
                    val
                );
                verdictBox.classList.remove('hidden');
                verdictBox.innerHTML = res.is_correct
                    ? `✓ <strong>Верно!</strong> ${escapeHtml(res.model_feedback)}`
                    : `✕ <strong>Неточно.</strong> ${escapeHtml(res.model_feedback)}`;
            } catch (e) {
                verdictBox.classList.remove('hidden');
                verdictBox.innerHTML = '⚠ Не удалось проверить вариант.';
            }
            await showVotes(false);
        });
    }

    // ---------- СОСТЯЗАНИЯ ----------
    if (currentPage === 'battles') {
        document.querySelectorAll('.battle-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.battle-tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.battletab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(`battle-${btn.getAttribute('data-battletab')}`).classList.add('active');
            });
        });

        // Спринт 60с
        const startBtn = document.getElementById('startSprintBtn');
        const timerEl = document.getElementById('sprintTimer');
        const scoreEl = document.getElementById('sprintScore');
        const missesEl = document.getElementById('sprintMisses');
        const opts = document.querySelectorAll('#sprintOptionsGrid .opt-btn');
        let interval = null;
        let currentPrompt = null;

        async function loadSprintPrompt() {
            try {
                const prompt = await ModelService.fetchBattlePrompt('sprint');
                currentPrompt = prompt;
                document.getElementById('sprintPromptText').textContent = prompt.bashkir_prompt;
                opts.forEach((btn, idx) => {
                    btn.textContent = prompt.options[idx] || '';
                    btn.disabled = false;
                });
            } catch (e) {}
        }

        startBtn.addEventListener('click', () => {
            if (interval) clearInterval(interval);
            startBtn.disabled = true;
            let t = 60, score = 0, misses = 0;
            scoreEl.textContent = score;
            missesEl.textContent = misses;
            timerEl.textContent = `${t}s`;

            opts.forEach((btn, idx) => {
                btn.onclick = async () => {
                    if (!currentPrompt) return;
                    opts.forEach(b => b.disabled = true);
                    if (idx === currentPrompt.correct_index) scoreEl.textContent = ++score;
                    else missesEl.textContent = ++misses;
                    await loadSprintPrompt();
                };
            });

            loadSprintPrompt();

            interval = setInterval(() => {
                t--;
                timerEl.textContent = `${t}s`;
                if (t <= 0) {
                    clearInterval(interval);
                    opts.forEach(b => b.disabled = true);
                    startBtn.disabled = false;
                    ModelService.sprintFinish(score).catch(() => {});
                }
            }, 1000);
        });

        // PvP
        const pvpPromptText = document.getElementById('pvpPromptText');
        const pvpOpts = document.querySelectorAll('#pvpOptionsGrid .opt-btn');
        const findPvpBtn = document.getElementById('findPvpMatchBtn');
        const pvpPlayBtn = document.getElementById('pvpPlayAudioBtn');
        const pvpSearchOverlay = document.getElementById('pvpSearchOverlay');
        const pvpSearchTimerText = document.getElementById('pvpSearchTimerText');
        const pvpTimerEl = document.getElementById('pvpTimer');
        const pvpOpponentProgressEl = document.getElementById('pvpOpponentProgress');
        const pvpQuestionCounterEl = document.getElementById('pvpQuestionCounter');
        const pvpQuestionSlot = document.getElementById('pvpQuestionSlot');

        let pvpPrompt = null;
        let pvpQuestions = [];
        let pvpMatchStartedAt = null;
        let pvpDuration = 60;
        let pvpCurrentIndex = 0;
        let pvpScore = 0;
        let pvpOpponentScore = 0;
        let pvpFinished = false;

        let pvpSearchTimer = null;
        let pvpSearchLeft = 0;
        let pvpGameTimer = null;
        let pvpPollTimer = null;

        function stopPvpSearch(message) {
            if (pvpSearchTimer) {
                clearInterval(pvpSearchTimer);
                pvpSearchTimer = null;
            }
            if (pvpSearchOverlay) pvpSearchOverlay.classList.add('hidden');
            findPvpBtn.disabled = false;
            findPvpBtn.textContent = 'Найти соперника';
            if (message) {
                pvpPromptText.textContent = message;
            }
            ModelService.pvpCancel().catch(() => {});
        }

        function renderPvpQuestion() {
            try {
                if (pvpCurrentIndex >= pvpQuestions.length) {
                    finishPvp();
                    return;
                }
                pvpPrompt = pvpQuestions[pvpCurrentIndex];
                if (pvpPromptText) pvpPromptText.textContent = pvpPrompt.pvp_bashkir_phrase;
                if (pvpQuestionCounterEl) {
                    pvpQuestionCounterEl.textContent = `Вопрос ${pvpCurrentIndex + 1} / ${pvpQuestions.length}`;
                }
                if (pvpQuestionSlot) pvpQuestionSlot.classList.remove('hidden');
                pvpOpts.forEach((btn, idx) => {
                    btn.textContent = pvpPrompt.options[idx] || '';
                    btn.disabled = false;
                    btn.style.borderColor = '';
                    btn.onclick = () => {
                        pvpOpts.forEach((b) => { b.disabled = true; });
                        const correct = idx === pvpPrompt.correct_index;
                        if (correct) {
                            btn.style.borderColor = 'var(--accent-success)';
                            pvpScore += 1;
                        } else {
                            btn.style.borderColor = 'var(--accent-danger)';
                        }
                        try { if (pvpSocket) pvpSocket.send(JSON.stringify({type:'progress', index: pvpCurrentIndex + 1, score: pvpScore, done: false})); } catch (e) {}
                        pvpCurrentIndex += 1;
                        setTimeout(() => {
                            if (pvpCurrentIndex >= pvpQuestions.length) {
                                finishPvp();
                            } else {
                                renderPvpQuestion();
                            }
                        }, 700);
                    };
                });
            } catch (e) {
                console.error('renderPvpQuestion error:', e);
            }
        }

        async function finishPvp(state) {
            if (pvpFinished) return;
            pvpFinished = true;
            if (pvpGameTimer) { clearInterval(pvpGameTimer); pvpGameTimer = null; }
            if (pvpPollTimer) { clearInterval(pvpPollTimer); pvpPollTimer = null; }
            try { if (pvpSocket) pvpSocket.send(JSON.stringify({type:'progress', index: pvpCurrentIndex, score: pvpScore, done: true})); } catch (e) {}
            let oppScore = pvpOpponentScore;
            let text = '';
            if (state && state.winner === 'draw') {
                text = `Ничья! Вы: ${pvpScore}, соперник: ${oppScore}`;
            } else if (state && state.winner_is_you) {
                text = `Вы победили! Вы: ${pvpScore}, соперник: ${oppScore}`;
            } else if (state && state.winner) {
                text = `Соперник победил. Вы: ${pvpScore}, соперник: ${oppScore}`;
            } else {
                if (pvpScore > oppScore) text = `Вы победили! Вы: ${pvpScore}, соперник: ${oppScore}`;
                else if (pvpScore < oppScore) text = `Соперник победил. Вы: ${pvpScore}, соперник: ${oppScore}`;
                else text = `Ничья! Вы: ${pvpScore}, соперник: ${oppScore}`;
            }
            if (pvpQuestionSlot) pvpQuestionSlot.classList.add('hidden');
            try { sessionStorage.removeItem('beztel_pvp_match_id'); } catch (e) {}
            pvpPromptText.textContent = text;
            pvpOpts.forEach((b) => { b.disabled = true; });
            findPvpBtn.disabled = false;
            findPvpBtn.textContent = 'Найти соперника';
        }

        let pvpSocket = null;

        findPvpBtn.addEventListener('click', () => {
            if (pvpSocket) return;
            pvpFinished = false;
            pvpCurrentIndex = 0;
            pvpScore = 0;
            pvpQuestions = [];
            pvpMatchStartedAt = null;
            const pvpQuestionSlot = document.getElementById('pvpQuestionSlot');
            if (pvpQuestionSlot) pvpQuestionSlot.classList.add('hidden');
            pvpPromptText.textContent = 'Ожидание соперника...';
            pvpOpts.forEach((b) => {
                b.disabled = true;
                b.textContent = '...';
                b.style.borderColor = '';
            });
            if (pvpOpponentProgressEl) pvpOpponentProgressEl.textContent = 'Соперник: -';
            if (pvpQuestionCounterEl) pvpQuestionCounterEl.textContent = '-';
            if (pvpTimerEl) pvpTimerEl.textContent = '60s';
            if (pvpSearchOverlay) pvpSearchOverlay.classList.remove('hidden');
            findPvpBtn.disabled = true;
            try { sessionStorage.setItem('beztel_pvp_searching', '1'); } catch (e) {}
            pvpSearchLeft = 60;
            if (pvpSearchTimerText) pvpSearchTimerText.textContent = String(pvpSearchLeft);
            findPvpBtn.textContent = `Поиск... ${pvpSearchLeft}s`;

            const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/api/v1/pvp/ws?client_id=' + encodeURIComponent(ModelService._clientId);
            pvpSocket = new WebSocket(wsUrl);

            const searchTimer = setInterval(() => {
                pvpSearchLeft -= 1;
                if (pvpSearchTimerText) pvpSearchTimerText.textContent = String(Math.max(0, pvpSearchLeft));
                if (pvpSearchLeft > 0) {
                    findPvpBtn.textContent = `Поиск... ${pvpSearchLeft}s`;
                } else {
                    clearInterval(searchTimer);
                    try { pvpSocket.send(JSON.stringify({type:'cancel'})); } catch (e) {}
                    pvpSocket.close();
                    pvpSocket = null;
                    if (pvpSearchOverlay) pvpSearchOverlay.classList.add('hidden');
                    findPvpBtn.disabled = false;
                    findPvpBtn.textContent = 'Найти соперника';
                    try { sessionStorage.removeItem('beztel_pvp_match_id'); } catch (e) {}
                    try { sessionStorage.removeItem('beztel_pvp_searching'); } catch (e) {}
                    pvpPromptText.textContent = 'Соперник не найден за 60 секунд. Поиск прерван.';
                }
            }, 1000);

            pvpSocket.onopen = () => {
                try { pvpSocket.send(JSON.stringify({type:'find'})); } catch (e) {}
            };

            pvpSocket.onmessage = (ev) => {
                let msg = {};
                try { msg = JSON.parse(ev.data); } catch (e) { return; }

                if (msg.type === 'searching') {
                    // ждём
                } else if (msg.type === 'matched') {
                    clearInterval(searchTimer);
                    try { sessionStorage.removeItem('beztel_pvp_searching'); } catch (e) {}
                    if (pvpSearchOverlay) pvpSearchOverlay.classList.add('hidden');
                    findPvpBtn.disabled = false;
                    findPvpBtn.textContent = 'Найти соперника';

                    pvpQuestions = msg.questions || [];
                    try { sessionStorage.setItem('beztel_pvp_match_id', msg.match_id || ''); } catch (e) {}
                    pvpMatchStartedAt = msg.started_at;
                    pvpDuration = msg.duration || 60;
                    pvpPromptText.textContent = 'Соперник найден! Переведите фразу:';

                    let pvpRem = pvpDuration;
                    if (pvpTimerEl) pvpTimerEl.textContent = pvpRem + 's';
                    pvpGameTimer = setInterval(() => {
                        pvpRem -= 1;
                        if (pvpTimerEl) pvpTimerEl.textContent = Math.max(0, pvpRem) + 's';
                        if (pvpRem <= 0 && !pvpFinished) {
                            try { pvpSocket.send(JSON.stringify({type:'time_up'})); } catch (e) {}
                            finishPvp();
                        }
                    }, 1000);

                    renderPvpQuestion();
                } else if (msg.type === 'opponent_progress') {
                    pvpOpponentScore = msg.score || 0;
                    if (pvpOpponentProgressEl) {
                        pvpOpponentProgressEl.textContent = `Соперник: вопрос ${msg.index + 1}/${pvpQuestions.length || 10}, очки ${msg.score}`;
                    }
                } else if (msg.type === 'finished') {
                    if (!pvpFinished) {
                        pvpFinished = true;
                        if (pvpGameTimer) { clearInterval(pvpGameTimer); pvpGameTimer = null; }
                        if (pvpQuestionSlot) pvpQuestionSlot.classList.remove('hidden');
                        const oppScore = (msg.opponent_score != null) ? msg.opponent_score : 0;
                        let text = '';
                        if (msg.winner === 'draw') text = `Ничья! Вы: ${msg.your_score}, соперник: ${oppScore}`;
                        else if (msg.winner_is_you) text = `Вы победили! Вы: ${msg.your_score}, соперник: ${oppScore}`;
                        else text = `Соперник победил. Вы: ${msg.your_score}, соперник: ${oppScore}`;
                        pvpPromptText.textContent = text;
                        pvpOpts.forEach((b) => { b.disabled = true; });
                        try { sessionStorage.removeItem('beztel_pvp_match_id'); } catch (e) {}
                        try { sessionStorage.removeItem('beztel_pvp_searching'); } catch (e) {}
                        setTimeout(() => { try { if (pvpSocket) pvpSocket.close(); } catch (e) {} pvpSocket = null; }, 300);
                        if (msg.winner_is_you) {
                            ModelService.awardXp(30, 'pvp_win').catch(() => {});
                        }
                    }
                } else if (msg.type === 'opponent_left') {
                    if (!pvpFinished) {
                        pvpFinished = true;
                        if (pvpGameTimer) { clearInterval(pvpGameTimer); pvpGameTimer = null; }
                        try { sessionStorage.removeItem('beztel_pvp_match_id'); } catch (e) {}
                        try { sessionStorage.removeItem('beztel_pvp_searching'); } catch (e) {}
                        pvpPromptText.textContent = 'Соперник покинул матч.';
                        pvpOpts.forEach((b) => { b.disabled = true; });
                    }
                }
            };

            pvpSocket.onclose = () => {
                pvpSocket = null;
            };
        });

        pvpPlayBtn.addEventListener('click', () => {
            if (pvpPrompt) ModelService.speakText(pvpPrompt.pvp_bashkir_phrase);
        });

        // автовосстановление матча после обновления страницы
        try {
            if (sessionStorage.getItem('beztel_pvp_match_id') || sessionStorage.getItem('beztel_pvp_searching')) {
                setTimeout(() => { findPvpBtn.click(); }, 300);
            }
        } catch (e) {}

    }

    // ---------- РЕЙТИНГ ----------
    if (currentPage === 'leaderboard') {
        async function loadLeaderboardPage() {
            const slot = document.getElementById('leaderboardSlot');
            if (!slot) return;
            try {
                const rows = await ModelService.fetchLeaderboard();
                slot.classList.remove('empty-slot-box');
                slot.innerHTML = `
                    <table style="width:100%; font-size:12px; border-collapse:collapse;">
                        <thead><tr>
                            <th style="text-align:left; padding:4px 8px; color:var(--text-muted);">#</th>
                            <th style="text-align:left; padding:4px 8px; color:var(--text-muted);">Игрок</th>
                            <th style="text-align:left; padding:4px 8px; color:var(--text-muted);">Уровень</th>
                            <th style="text-align:left; padding:4px 8px; color:var(--text-muted);">XP</th>
                        </tr></thead>
                        <tbody>${rows.map(r => `
                            <tr>
                                <td style="padding:4px 8px; border-top:1px solid var(--border-hairline);">${r.rank}</td>
                                <td style="padding:4px 8px; border-top:1px solid var(--border-hairline);">${escapeHtml(r.name)} ${r.avatar || ''}</td>
                                <td style="padding:4px 8px; border-top:1px solid var(--border-hairline);">${r.level}</td>
                                <td style="padding:4px 8px; border-top:1px solid var(--border-hairline);">${r.xp}</td>
                            </tr>`).join('')}
                        </tbody>
                    </table>`;
            } catch (e) {
                slot.innerHTML = '<p>Не удалось загрузить рейтинг.</p>';
            }
        }
        loadLeaderboardPage();
    }

    // ---------- ЭКСПОРТ ----------
    if (currentPage === 'export') {
        const refreshExport = async () => {
            try {
                if (ModelService.sessionExportBuffer.length === 0) {
                    const batch = await ModelService.fetchExportBatch(20);
                    batch.forEach((i) => ModelService.sessionExportBuffer.push(i));
                }
                document.getElementById('exportCountVal').textContent = String(ModelService.sessionExportBuffer.length);
                const slot = document.getElementById('exportPreviewSlot');
                slot.classList.remove('empty-slot-box');
                slot.innerHTML = `
                    <table style="width:100%; font-size:12px; border-collapse:collapse;">
                        <thead><tr><th style="text-align:left; padding:4px 8px; color:var(--text-muted);">Башкирский</th><th style="text-align:left; padding:4px 8px; color:var(--text-muted);">Русский</th></tr></thead>
                        <tbody>${ModelService.sessionExportBuffer.map(i => `
                            <tr><td style="padding:4px 8px; border-top:1px solid var(--border-hairline);">${escapeHtml(i.bashkir)}</td>
                            <td style="padding:4px 8px; border-top:1px solid var(--border-hairline);">${escapeHtml(i.russian)}</td></tr>`).join('')}
                        </tbody>
                    </table>`;
            } catch (e) {}
        };
        await refreshExport();

        document.getElementById('downloadCsvBtn').addEventListener('click', () => {
            const rows = [['bashkir', 'russian'], ...ModelService.sessionExportBuffer.map(i => [i.bashkir, i.russian])];
            const link = document.createElement('a');
            link.href = encodeURI('data:text/csv;charset=utf-8,' + rows.map(e => e.join(',')).join('\n'));
            link.download = 'beztel_translations.csv';
            link.click();
        });
        document.getElementById('downloadJsonBtn').addEventListener('click', () => {
            const link = document.createElement('a');
            link.href = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(ModelService.sessionExportBuffer, null, 2));
            link.download = 'beztel_model_dump.json';
            link.click();
        });
    }

    // ---------- ПРОФИЛЬ ----------
    if (currentPage === 'profile') {
        try {
            const profile = await ModelService.fetchProfile();
            document.getElementById('profileStreak').textContent = `${profile.streak} 🔥`;
            document.getElementById('profileAccuracy').textContent = `${profile.accuracy}%`;
            document.getElementById('profileRank').textContent = `#${profile.rank}`;
            document.getElementById('profileWords').textContent = String(profile.words);
            const lvlEl = document.getElementById('profileLevel');
            const xpEl = document.getElementById('profileXp');
            if (lvlEl) lvlEl.textContent = String(profile.level || 1);
            if (xpEl) xpEl.textContent = String(profile.xp || 0);
            const bar = document.getElementById('profileXpBar');
            const txt = document.getElementById('profileXpText');
            const cur = profile.xp_current_level || 0;
            const need = profile.xp_for_next_level || 1;
            if (bar) bar.style.width = Math.min(100, Math.round(cur / need * 100)) + '%';
            if (txt) txt.textContent = `${cur} / ${need} XP`;
        } catch (e) {
            // Офлайн-режим: показываем слова, выученные на карте уровней.
            try {
                const saved = JSON.parse(localStorage.getItem('beztel_study_progress_v1') || '{}');
                const known = Array.isArray(saved.known) ? saved.known : [];
                const wordsEl = document.getElementById('profileWords');
                if (wordsEl) wordsEl.textContent = String(known.length);
            } catch (e2) {}
        }

        const uiLangSelect = document.getElementById('uiLangSelect');
        const chatLangSelectProfile = document.getElementById('chatLangSelectProfile');
        if (uiLangSelect) {
            uiLangSelect.value = ModelService._uiLang;
            uiLangSelect.addEventListener('change', () => ModelService.setUiLang(uiLangSelect.value));
        }
        if (chatLangSelectProfile) {
            chatLangSelectProfile.value = ModelService._chatLang;
            chatLangSelectProfile.addEventListener('change', () => ModelService.setChatLang(chatLangSelectProfile.value));
        }
    }
});
