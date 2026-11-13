/**
 * БЕЗТЕЛ — Единый контроллер для всех разделов приложения.
 * Интеграция с бэкендом: /api/v1
 */
const ModelService = {
    BASE_URL: '/api/v1',
    sessionExportBuffer: [],
    _history: [],
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
        const heroUserName = document.getElementById('heroUserName');
        if (heroUserName) heroUserName.textContent = firstName;
        try {
            const insight = await ModelService.fetchHubDailyInsight();
            document.getElementById('hubInsightBashkir').textContent = insight.bashkir_phrase;
            document.getElementById('hubInsightTranslation').textContent = insight.translation_ru;
            document.getElementById('hubInsightContext').textContent = insight.cultural_note;
        } catch (e) {}
        try {
            const profile = await ModelService.fetchProfile();
            const lines = document.querySelectorAll('.mini-stat-line strong');
            if (lines.length >= 3) {
                lines[0].textContent = String(profile.words);
                lines[1].textContent = `${profile.accuracy}%`;
                lines[2].textContent = profile.streak > 0 ? 'Пройден' : 'Не пройден';
            }
            const ring = document.querySelector('.goal-progress');
            if (ring) {
                const pct = Math.min(100, profile.words);
                ring.style.strokeDashoffset = String(314 - 314 * pct / 100);
            }
        } catch (e) {}
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

    // ---------- ИЗУЧЕНИЕ ----------
    if (currentPage === 'study') {
        document.querySelectorAll('.seg-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.subtab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(`sub-${btn.getAttribute('data-subtab')}`).classList.add('active');
            });
        });

        const knowBtn = document.getElementById('cardKnowBtn');
        const dontKnowBtn = document.getElementById('cardDontKnowBtn');
        const nextCard = async (know = true) => {
            knowBtn.disabled = true;
            dontKnowBtn.disabled = true;
            try {
                await ModelService.answerCard(know);
                const card = await ModelService.fetchNextCard();
                document.getElementById('cardBashkirWord').textContent = card.word_bashkir;
                document.getElementById('cardTranscription').textContent = card.phonetics || '';
                document.getElementById('cardRussianTranslation').textContent = card.translation_ru;
            } catch (e) {
                document.getElementById('cardBashkirWord').textContent = '№ 301';
                document.getElementById('cardTranscription').textContent = 'сәләм';
                document.getElementById('cardRussianTranslation').textContent = 'привет';
            } finally {
                setTimeout(() => { knowBtn.disabled = false; dontKnowBtn.disabled = false; }, 350);
            }
        };
        knowBtn.addEventListener('click', () => nextCard(true));
        dontKnowBtn.addEventListener('click', () => nextCard(false));

        const themesBtn = document.getElementById('requestThemesBtn');
        if (themesBtn) {
            themesBtn.addEventListener('click', async () => {
                const slot = document.getElementById('modelThemesSlot');
                try {
                    const themes = await ModelService.fetchThemes();
                    slot.classList.remove('empty-slot-box');
                    slot.innerHTML = themes.map(t => `
                        <div class="ach-row">
                            <span>${t.icon}</span>
                            <div><strong>${escapeHtml(t.title)}</strong><p>${escapeHtml(t.description)}</p></div>
                        </div>`).join('');
                } catch (e) {
                    slot.innerHTML = '<p>Не удалось загрузить темы.</p>';
                }
            });
        }

        // Первая карточка
        nextCard(true);
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
                }
            }, 1000);
        });

        // PvP
        const pvpPromptText = document.getElementById('pvpPromptText');
        const pvpOpts = document.querySelectorAll('#pvpOptionsGrid .opt-btn');
        const findPvpBtn = document.getElementById('findPvpMatchBtn');
        const pvpPlayBtn = document.getElementById('pvpPlayAudioBtn');
        let pvpPrompt = null;

        async function loadPvp() {
            try {
                const prompt = await ModelService.fetchBattlePrompt('pvp');
                pvpPrompt = prompt;
                pvpPromptText.textContent = prompt.pvp_bashkir_phrase;
                pvpOpts.forEach((btn, idx) => {
                    btn.textContent = prompt.options[idx] || '';
                    btn.disabled = false;
                    btn.onclick = () => {
                        pvpOpts.forEach(b => b.disabled = true);
                        if (idx === prompt.correct_index) {
                            btn.style.borderColor = 'var(--accent-success)';
                        } else {
                            btn.style.borderColor = 'var(--accent-danger)';
                        }
                        setTimeout(loadPvp, 700);
                    };
                });
            } catch (e) {}
        }

        findPvpBtn.addEventListener('click', loadPvp);
        pvpPlayBtn.addEventListener('click', () => {
            if (pvpPrompt) ModelService.speakText(pvpPrompt.pvp_bashkir_phrase);
        });
        loadPvp();
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
        } catch (e) {}

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
