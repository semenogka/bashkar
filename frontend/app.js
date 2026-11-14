/**
 * БЕЗТЕЛ — Единый контроллер для всех разделов приложения.
 * Интеграция с бэкендом: /api/v1
 */
const ModelService = {
    sessionExportBuffer: [],
    _history: [],
    _clientId: null,
    _uiLang: localStorage.getItem('beztel_lang') || localStorage.getItem('beztel_ui_lang') || 'ru',
    _chatLang: localStorage.getItem('beztel_lang') || localStorage.getItem('beztel_chat_lang') || 'ru',
    _targetLang: localStorage.getItem('beztel_lang') || localStorage.getItem('beztel_chat_lang') || 'ru',
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
        h['X-Content-Lang'] = this.lang();
        try {
            const token = localStorage.getItem('beztel_token');
            if (token) h['Authorization'] = 'Bearer ' + token;
        } catch (e) {}
        return h;
    },

    _apiOrigin() {
        if (window.BEZTEL_API_ORIGIN) return String(window.BEZTEL_API_ORIGIN).replace(/\/$/, '');
        if (location.protocol === 'file:') return 'http://127.0.0.1:8000';
        const port = location.port;
        if (port && port !== '8000' && port !== '80' && port !== '443') return 'http://127.0.0.1:8000';
        return location.origin;
    },

    get BASE_URL() {
        return this._apiOrigin() + '/api/v1';
    },

    _origin() {
        return this._apiOrigin();
    },

    _wsOrigin() {
        return this._apiOrigin().replace(/^http/, 'ws');
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
        const res = await fetch(this.BASE_URL + '/chat/voice?target_lang=' + encodeURIComponent(this.lang()), {
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

    lang() {
        const code = this._uiLang || this._chatLang || 'ru';
        return code === 'kk' || code === 'zh' ? code : 'ru';
    },
    setLang(lang) {
        const code = lang === 'kk' || lang === 'zh' ? lang : 'ru';
        this._uiLang = this._chatLang = this._targetLang = code;
        try {
            localStorage.setItem('beztel_lang', code);
            localStorage.setItem('beztel_ui_lang', code);
            localStorage.setItem('beztel_chat_lang', code);
        } catch (e) {}
        document.documentElement.lang = code === 'zh' ? 'zh-CN' : code;
        document.querySelectorAll('#uiLangSelect, #chatLangSelect, #chatLangSelectProfile').forEach((el) => {
            el.value = code;
        });
        applyInterface(code);
        this._post('/profile/language', { lang: code }).catch(() => {});
    },
    setUiLang(lang) { this.setLang(lang); },
    setChatLang(lang) { this.setLang(lang); },
};
window.ModelService = ModelService;

// ---------------------------------------------------------------------------
// Утилиты
// ---------------------------------------------------------------------------
function escapeHtml(s) {
    return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const GLOSS = {
    'Пройдите карточки': { kk: 'Карточкаларды өтіңіз', zh: '完成单词卡' },
    'Скоростной забег': { kk: 'Жылдамдық жарысы', zh: '速度挑战' },
    'Выиграйте состязание': { kk: 'Жарыста жеңіңіз', zh: '赢得比赛' },
    'Точность 80%': { kk: 'Дәлдік 80%', zh: '准确率 80%' },
    'привет': { kk: 'сәлем', zh: '你好' },
    'спасибо': { kk: 'рақмет', zh: '谢谢' },
    'да': { kk: 'иә', zh: '是' },
    'нет': { kk: 'жоқ', zh: '不' },
    'до свидания': { kk: 'сау бол', zh: '再见' },
    'я': { kk: 'мен', zh: '我' },
    'ты': { kk: 'сен', zh: '你' },
    'мама': { kk: 'ана', zh: '妈妈' },
    'папа': { kk: 'әке', zh: '爸爸' },
    'семья': { kk: 'отбасы', zh: '家庭' },
    'вода': { kk: 'су', zh: '水' },
    'огонь': { kk: 'от', zh: '火' },
    'земля': { kk: 'жер', zh: '土地' },
    'небо': { kk: 'аспан', zh: '天空' },
    'солнце': { kk: 'күн', zh: '太阳' },
    'собака': { kk: 'ит', zh: '狗' },
    'кошка': { kk: 'мысық', zh: '猫' },
    'лошадь': { kk: 'жылқы', zh: '马' },
    'птица': { kk: 'құс', zh: '鸟' },
    'рыба': { kk: 'балық', zh: '鱼' },
    'хлеб': { kk: 'нан', zh: '面包' },
    'молоко': { kk: 'сүт', zh: '牛奶' },
    'чай': { kk: 'шай', zh: '茶' },
    'мёд': { kk: 'бал', zh: '蜂蜜' },
    'яблоко': { kk: 'алма', zh: '苹果' },
    'знаю': { kk: 'білемін', zh: '我知道' },
    'люблю': { kk: 'жақсы көремін', zh: '我喜欢' },
    'иду': { kk: 'барамын', zh: '我走' },
    'прихожу': { kk: 'келемін', zh: '我来' },
    'читаю': { kk: 'оқимын', zh: '我读' },
    'большой': { kk: 'үлкен', zh: '大' },
    'маленький': { kk: 'кішкентай', zh: '小' },
    'хороший': { kk: 'жақсы', zh: '好' },
    'красивый': { kk: 'әдемі', zh: '漂亮' },
    'новый': { kk: 'жаңа', zh: '新' },
    'друг': { kk: 'дос', zh: '朋友' },
    'страна': { kk: 'ел', zh: '国家' },
    'язык': { kk: 'тіл', zh: '语言' },
    'песня': { kk: 'ән', zh: '歌' },
    'счастье': { kk: 'бақыт', zh: '幸福' },
    'Знакомство': { kk: 'Танысу', zh: '认识' },
    'Семья': { kk: 'Отбасы', zh: '家庭' },
    'Природа': { kk: 'Табиғат', zh: '自然' },
    'Животные': { kk: 'Жануарлар', zh: '动物' },
    'Еда': { kk: 'Тамақ', zh: '食物' },
    'Движение': { kk: 'Қимыл', zh: '动作' },
    'Признаки': { kk: 'Белгілер', zh: '特征' },
    'Культура': { kk: 'Мәдениет', zh: '文化' },
    'Приветствие': { kk: 'Сәлемдесу', zh: '问候' },
    'Дом': { kk: 'Үй', zh: '家' },
    'Чувства': { kk: 'Сезім', zh: '情感' },
    'Я студент': { kk: 'Мен студентпін', zh: '我是学生' },
    'Ты кто?': { kk: 'Сен кімсің?', zh: '你是谁？' },
    'Я читаю': { kk: 'Мен оқимын', zh: '我在读' },
    'До свидания': { kk: 'Сау бол', zh: '再见' },
    'Спасибо тебе': { kk: 'Саған рақмет', zh: '谢谢你' },
    'Это моя мама': { kk: 'Бұл менің анам', zh: '这是我的妈妈' },
    'Моя семья большая': { kk: 'Менің отбасым үлкен', zh: '我的家庭很大' },
    'Я люблю маму': { kk: 'Мен анамды жақсы көремін', zh: '我爱妈妈' },
    'Он мой брат': { kk: 'Ол менің ағам', zh: '他是我的哥哥' },
    'Мы живём вместе': { kk: 'Біз бірге тұрамыз', zh: '我们住在一起' },
    'Солнце светит': { kk: 'Күн жарқырайды', zh: '太阳照耀' },
    'Вода холодная': { kk: 'Су суық', zh: '水是凉的' },
    'Небо синее': { kk: 'Аспан көк', zh: '天空是蓝的' },
    'В лесу поют птицы': { kk: 'Орманда құстар сайрайды', zh: '森林里鸟儿在唱歌' },
    'Земля тёплая': { kk: 'Жер жылы', zh: '土地是暖的' },
    'Я пью чай': { kk: 'Мен шай ішемін', zh: '我喝茶' },
    'Хлеб вкусный': { kk: 'Нан дәмді', zh: '面包很好吃' },
    'Мама варит кашу': { kk: 'Ана ботқа пісіреді', zh: '妈妈在煮粥' },
    'Я люблю яблоки': { kk: 'Мен алма жақсы көремін', zh: '我喜欢苹果' },
    'Молоко очень вкусное': { kk: 'Сүт өте дәмді', zh: '牛奶非常好喝' },
    'Мой дом большой': { kk: 'Менің үйім үлкен', zh: '我的房子很大' },
    'В доме есть кошка': { kk: 'Үйде мысық бар', zh: '家里有一只猫' },
    'Я возвращаюсь домой': { kk: 'Мен үйге ораламын', zh: '我回家' },
    'Окно открыто': { kk: 'Терезе ашық', zh: '窗户开着' },
    'У нас гости': { kk: 'Бізде қонақтар бар', zh: '我们有客人' },
    'Я иду в школу': { kk: 'Мен мектепке барамын', zh: '我去上学' },
    'Ты говоришь по-башкирски': { kk: 'Сен башқұртша сөйлейсің', zh: '你说巴什基尔语' },
    'Он читает книгу': { kk: 'Ол кітап оқиды', zh: '他在读书' },
    'Мы поём песню': { kk: 'Біз ән айтамыз', zh: '我们唱歌' },
    'Они работают': { kk: 'Олар жұмыс істейді', zh: '他们在工作' },
    'Я счастлив': { kk: 'Мен бақыттымын', zh: '我很幸福' },
    'Он очень рад': { kk: 'Ол қатты қуанышты', zh: '他非常高兴' },
    'Мне весело': { kk: 'Маған көңілді', zh: '我很开心' },
    'Ты устал': { kk: 'Сен шаршадың', zh: '你累了' },
    'Мы горды': { kk: 'Біз мақтанамыз', zh: '我们感到自豪' },
    'Башкирский язык красивый': { kk: 'Башқұрт тілі әдемі', zh: '巴什基尔语很美' },
    'Я говорю по-башкирски': { kk: 'Мен башқұртша сөйлеймін', zh: '我说巴什基尔语' },
    'Эта песня очень красивая': { kk: 'Бұл ән өте әдемі', zh: '这首歌非常好听' },
    'Мы изучаем историю': { kk: 'Біз тарихты үйренеміз', zh: '我们在学历史' },
    'Друзья поют вместе': { kk: 'Достар бірге ән айтады', zh: '朋友们一起唱歌' },
};

function meaning(text) {
    const lang = ModelService.lang();
    if (!text || lang === 'ru') return text;
    const row = GLOSS[text];
    return (row && row[lang]) || text;
}

const NAV_LABELS = {
    'hub.html': { ru: 'Мой хаб', kk: 'Менің хабым', zh: '我的主页' },
    'chat.html': { ru: 'Чат с башкиром', kk: 'Башқұртпен сөйлесу', zh: '与巴什基尔语对话' },
    'study.html': { ru: 'Изучение', kk: 'Үйрену', zh: '学习' },
    'daily.html': { ru: 'Дейлик', kk: 'Күнделік', zh: '每日任务' },
    'battles.html': { ru: 'Состязания', kk: 'Жарыс', zh: '竞赛' },
    'dictionary.html': { ru: 'Словарь', kk: 'Сөздік', zh: '词典' },
    'profile.html': { ru: 'Профиль', kk: 'Профиль', zh: '个人资料' },
    'leaderboard.html': { ru: 'Рейтинг', kk: 'Рейтинг', zh: '排行榜' },
    'school.html': { ru: 'Добавить ученика', kk: 'Оқушы қосу', zh: '添加学生' },
    'admin.html': { ru: 'Админ', kk: 'Әкімші', zh: '管理' },
};

function applyInterface(lang) {
    const code = lang === 'kk' || lang === 'zh' ? lang : 'ru';
    document.querySelectorAll('a.nav-item').forEach((link) => {
        const href = (link.getAttribute('href') || '').split('?')[0];
        const label = link.querySelector('.nav-label');
        const pack = NAV_LABELS[href];
        if (label && pack) label.textContent = pack[code];
    });
    const copy = {
        ru: { ph: 'Написать сообщение...', find: 'Найти', exp: 'Скачать весь словарь', listen: 'Послушать', lang: 'Язык', q: 'Башкирское слово или перевод' },
        kk: { ph: 'Хабарлама жазу...', find: 'Іздеу', exp: 'Бүкіл сөздікті жүктеу', listen: 'Тыңдау', lang: 'Тіл', q: 'Башқұртша сөз немесе аударма' },
        zh: { ph: '写一条消息...', find: '查找', exp: '下载整本词典', listen: '听', lang: '语言', q: '巴什基尔语或译文' },
    }[code];
    const input = document.getElementById('chatTextInput');
    if (input) input.placeholder = copy.ph;
    const find = document.querySelector('#dictForm button[type="submit"]');
    if (find) find.textContent = copy.find;
    const dictQuery = document.getElementById('dictQuery');
    if (dictQuery) dictQuery.placeholder = copy.q;
    const exp = document.getElementById('dictExportBtn');
    if (exp) exp.textContent = copy.exp;
    document.querySelectorAll('.study-speak-label').forEach((el) => { el.textContent = copy.listen; });
    document.querySelectorAll('label[for="uiLangSelect"], label[for="chatLangSelect"]').forEach((el) => {
        el.textContent = copy.lang;
    });
}

// ---------------------------------------------------------------------------
// Озвучка башкирского: сначала голос модели, затем браузерный синтез
// ---------------------------------------------------------------------------
let _ttsAudio = null;
let _ttsToken = 0;

function playAudioUrl(url) {
    return new Promise((resolve) => {
        try {
            if (_ttsAudio) {
                try { _ttsAudio.pause(); } catch (e) {}
                _ttsAudio = null;
            }
            const full = url.startsWith('http') ? url : ModelService._origin() + url;
            const audio = new Audio(full);
            _ttsAudio = audio;
            const done = () => {
                if (_ttsAudio === audio) _ttsAudio = null;
                resolve(true);
            };
            audio.addEventListener('ended', done, { once: true });
            audio.addEventListener('error', done, { once: true });
            audio.play().catch(done);
        } catch (e) {
            resolve(false);
        }
    });
}

function speakWithBrowser(text) {
    return new Promise((resolve) => {
        try {
            if (!('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) {
                resolve(false);
                return;
            }
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'ba-RU';
            utterance.rate = 0.86;
            utterance.pitch = 1;
            const voices = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
            const preferred = voices.find((v) => /^ba/i.test(v.lang))
                || voices.find((v) => /^tt/i.test(v.lang))
                || voices.find((v) => /^ru/i.test(v.lang));
            if (preferred) utterance.voice = preferred;
            let settled = false;
            const finish = (ok) => {
                if (settled) return;
                settled = true;
                resolve(ok);
            };
            utterance.onend = () => finish(true);
            utterance.onerror = () => finish(false);
            window.speechSynthesis.speak(utterance);
            setTimeout(() => finish(true), Math.min(9000, 1600 + text.length * 120));
        } catch (e) {
            resolve(false);
        }
    });
}

function stopSpeech() {
    _ttsToken += 1;
    if (_ttsAudio) {
        try { _ttsAudio.pause(); } catch (e) {}
        _ttsAudio = null;
    }
    if ('speechSynthesis' in window) {
        try { window.speechSynthesis.cancel(); } catch (e) {}
    }
}

async function speakBashkir(text, button) {
    const value = String(text || '').trim();
    if (!value) return false;
    const token = ++_ttsToken;
    const label = button ? button.querySelector('.study-speak-label, .sentence-speak-label') : null;
    const originalLabel = label ? label.textContent : '';
    if (button) {
        button.classList.add('is-loading');
        button.disabled = true;
    }
    if (label) label.textContent = 'Готовим голос…';

    let played = false;
    try {
        const res = await fetch(ModelService._origin() + '/api/speech/tts?text=' + encodeURIComponent(value), {
            headers: ModelService._tgHeaders(),
        });
        if (res.ok) {
            const data = await res.json();
            if (data && data.url) {
                played = true;
                if (button) {
                    button.classList.remove('is-loading');
                    button.classList.add('is-playing');
                }
                if (label) label.textContent = 'Звучит…';
                await playAudioUrl(data.url);
            }
        }
    } catch (e) {}

    if (!played && token === _ttsToken) {
        if (button) {
            button.classList.remove('is-loading');
            button.classList.add('is-playing');
        }
        if (label) label.textContent = 'Звучит…';
        played = await speakWithBrowser(value);
    }

    if (token === _ttsToken) {
        if (button) {
            button.classList.remove('is-loading', 'is-playing');
            button.disabled = false;
        }
        if (label) label.textContent = originalLabel || 'Послушать';
    }
    return played;
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
function reshapeNav() {
    const page = (location.pathname.split('/').pop() || '').toLowerCase();
    document.querySelectorAll('.nav-index').forEach((el) => el.remove());
    document.querySelectorAll('.header-section-title').forEach((el) => {
        el.textContent = el.textContent.replace(/^\s*\d+\s*\/\s*/, '');
    });
    document.querySelectorAll('a.nav-item[href="sentences.html"]').forEach((el) => el.remove());
    document.querySelectorAll('a.nav-item[href="export.html"]').forEach((el) => {
        el.setAttribute('href', 'dictionary.html');
        const label = el.querySelector('.nav-label');
        if (label) label.textContent = 'Словарь';
    });
    document.querySelectorAll('nav.nav-menu').forEach((nav) => {
        const dict = [...nav.querySelectorAll('a.nav-item[href="dictionary.html"]')];
        dict.slice(1).forEach((el) => el.remove());
        nav.querySelectorAll('a.nav-item[href="school.html"], a.nav-item[href="admin.html"]').forEach((el) => el.remove());
    });
    document.querySelectorAll('a.nav-item').forEach((el) => {
        const href = (el.getAttribute('href') || '').split('?')[0].toLowerCase();
        const here = page === 'export.html' ? 'dictionary.html' : page;
        el.classList.toggle('active', href === here);
    });
}

function addNavLink(href, label, icon) {
    document.querySelectorAll('nav.nav-menu').forEach((nav) => {
        if (nav.querySelector('a[href="' + href + '"]')) return;
        const page = (location.pathname.split('/').pop() || '').toLowerCase();
        const link = document.createElement('a');
        link.href = href;
        link.className = 'nav-item' + (page === href ? ' active' : '');
        const hasIcons = !!nav.querySelector('.nav-icon');
        link.innerHTML = hasIcons
            ? '<span class="nav-icon"><img src="' + icon + '" alt="" loading="lazy"></span><span class="nav-label">' + label + '</span>'
            : '<span class="nav-label">' + label + '</span>';
        nav.appendChild(link);
    });
}

async function injectRoleNav() {
    try {
        const res = await fetch(ModelService._origin() + '/api/v1/school/me', { headers: ModelService._tgHeaders() });
        if (!res.ok) return;
        const me = await res.json();
        if (me.role === 'teacher') addNavLink('school.html', 'Добавить ученика', 'img/galochka.png');
        if (me.role === 'admin') addNavLink('admin.html', 'Админ', 'img/zadumchivyy.png');
        applyInterface(ModelService.lang());
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', async () => {
    reshapeNav();
    injectRoleNav();
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
    ModelService.setLang(ModelService.lang());

    // Общая статистика в шапке
    await updateHeaderStats();

    // ---------- ХАБ ----------
    if (currentPage === 'hub') {
        function paintHubStreak(streak) {
            const days = Math.max(0, Number(streak) || 0);
            const shown = days === 0 ? 0 : (days % 7 === 0 ? 7 : days % 7);
            const ring = document.getElementById('hubStreakRing');
            const label = document.getElementById('hubStreakValue');
            if (ring) ring.style.setProperty('--p', String(shown / 7 * 100));
            if (label) label.textContent = shown + '/7';
        }
        async function loadDailyTasks() {
            const slot = document.getElementById('dailyTasksSlot');
            const countEl = document.getElementById('hubGoalsCount');
            if (!slot) return;
            try {
                const tasks = await ModelService.fetchDailyTasks();
                const done = tasks.filter((t) => t.completed).length;
                if (countEl) countEl.textContent = done + '/' + tasks.length;
                slot.innerHTML = tasks.map((t) => {
                    const width = t.target ? Math.min(100, Math.round((t.progress || 0) / t.target * 100)) : 0;
                    return `<div class="hub-goal${t.completed ? ' is-done' : ''}">
                        <span class="hub-goal-mark">${t.completed ? '✓' : ''}</span>
                        <span class="hub-goal-title">${escapeHtml(meaning(t.title))}</span>
                        <span class="hub-goal-meta">${t.progress}/${t.target}</span>
                        <span class="hub-goal-bar"><i style="width:${width}%"></i></span>
                    </div>`;
                }).join('') || '<p class="hub-word-note">На сегодня целей нет.</p>';
            } catch (e) {
                slot.innerHTML = '<p class="hub-word-note">Цели появятся после входа.</p>';
            }
        }
        loadDailyTasks();

        const heroUserName = document.getElementById('heroUserName');
        if (heroUserName) heroUserName.textContent = firstName;
        try {
            const profile = await ModelService.fetchProfile();
            paintHubStreak(profile.streak || 0);
            const name = profile.username && profile.username !== 'Гость' ? profile.username : firstName;
            if (heroUserName && name) heroUserName.textContent = name;
        } catch (e) {
            paintHubStreak(0);
        }
        try {
            const insight = await ModelService.fetchHubDailyInsight();
            document.getElementById('hubInsightBashkir').textContent = insight.bashkir_phrase;
            document.getElementById('hubInsightTranslation').textContent = insight.translation_ru;
            document.getElementById('hubInsightContext').textContent = insight.cultural_note;
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
        if (langSelect) {
            langSelect.value = ModelService.lang();
            langSelect.addEventListener('change', () => ModelService.setLang(langSelect.value));
        }

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
        const wordsPane = document.getElementById('studyWordsPane');
        const sentencesPane = document.getElementById('studySentencesPane');
        function applyStudyMode(mode) {
            if (wordsPane) wordsPane.classList.toggle('hidden', mode !== 'words');
            if (sentencesPane) sentencesPane.classList.toggle('hidden', mode !== 'sentences');
            document.querySelectorAll('#studyModes .lb-tab').forEach((btn) => {
                btn.classList.toggle('is-on', btn.dataset.mode === mode);
            });
        }
        const studyModes = document.getElementById('studyModes');
        if (studyModes) {
            studyModes.addEventListener('click', (event) => {
                const btn = event.target.closest('.lb-tab');
                if (btn) applyStudyMode(btn.dataset.mode);
            });
            applyStudyMode(new URLSearchParams(location.search).get('mode') === 'sentences' ? 'sentences' : 'words');
        }
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
        const speakBtn = document.getElementById('studySpeakBtn');

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

        const GROUNDHOG_FOR_STATE = {
            current: 'makhayushchiy',
            open: 'zadumchivyy',
            replay: 'dovolnyy',
        };

        function renderMap() {
            const currentIndex = firstPlayableIndex();
            trail.innerHTML = LEVELS.map((level, index) => {
                const state = stateFor(index);
                const stars = starsOf(level);
                const playable = state === 'current' || state === 'open' || state === 'replay';
                const hog = GROUNDHOG_FOR_STATE[state];
                const groundhogMarkup = playable && hog
                    ? `<span class="groundhog ${state === 'current' ? 'groundhog--hero' : 'groundhog--peek'}" aria-hidden="true"><img src="img/${hog}.png" alt="" loading="lazy"></span>`
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
                    <span class="mound mound--${state}">${closure}${groundhogMarkup}${planks}<span class="mound-lip" aria-hidden="true"></span></span>
                    <span class="level-label"><span class="level-num">${number}</span> ${escapeHtml(meaning(level.title))}</span>
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
                { text: meaning(word.ru), correct: true },
                ...picks.map((text) => ({ text: meaning(text), correct: false })),
            ]);
        }

        function renderQuestion() {
            stopSpeech();
            const word = session.order[session.index];
            const total = session.order.length;
            sessionTitle.textContent = `Слово ${session.index + 1} из ${total}`;
            document.getElementById('studyWord').textContent = word.ba;
            document.getElementById('studyWordPhonetics').textContent = word.tr;
            progressFill.style.width = `${Math.round((session.index / total) * 100)}%`;
            feedbackEl.textContent = '';
            feedbackEl.className = 'study-feedback';
            if (speakBtn) {
                speakBtn.disabled = false;
                speakBtn.classList.remove('is-loading', 'is-playing');
                const speakLabel = speakBtn.querySelector('.study-speak-label');
                if (speakLabel) speakLabel.textContent = 'Послушать';
            }

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
                feedbackEl.textContent = `Правильный перевод: «${meaning(word.ru)}»`;
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

            const resultMascot = document.getElementById('studyResultMascot');
            if (resultMascot) {
                if (stars >= 3) {
                    resultMascot.src = 'img/radostnyy.png';
                    resultMascot.alt = 'Сурок радуется трём звёздам';
                } else if (stars > 0) {
                    resultMascot.src = 'img/dovolnyy.png';
                    resultMascot.alt = 'Сурок доволен прогрессом';
                } else {
                    resultMascot.src = 'img/grustnyy.png';
                    resultMascot.alt = 'Сурок расстроился, но ждёт повторения';
                }
            }

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
            sessionKicker.textContent = `УРОВЕНЬ ${level.id} · ${meaning(level.title).toUpperCase()}`;
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
            stopSpeech();
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

        if (speakBtn) {
            speakBtn.addEventListener('click', () => {
                if (!session) return;
                const word = session.order[session.index];
                if (word) speakBashkir(word.ba, speakBtn);
            });
        }

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

    // ---------- СОСТАВЬ ПРЕДЛОЖЕНИЕ ----------
    if (currentPage === 'sentences' && !document.getElementById('sentenceTrail')) {
        location.replace('study.html?mode=sentences');
    }
    if (document.getElementById('sentenceTrail')) {
        const SENTENCE_KEY = 'beztel_sentence_progress_v1';
        const SENTENCE_LEVELS = [
            {
                id: 1,
                title: 'Приветствие',
                sentences: [
                    { ru: 'Я студент', tokens: ['мин', 'студент'], extras: ['һин', 'уҡытыусы'] },
                    { ru: 'Ты кто?', tokens: ['һин', 'кем'], extras: ['мин', 'ҡайҙа'] },
                    { ru: 'Я читаю', tokens: ['мин', 'уҡыйым'], extras: ['һин', 'яҙаһың'] },
                    { ru: 'До свидания', tokens: ['һау', 'бул'], extras: ['сәләм', 'рәхмәт'] },
                    { ru: 'Спасибо тебе', tokens: ['рәхмәт', 'һиңә'], extras: ['сәләм', 'мин'] },
                ],
            },
            {
                id: 2,
                title: 'Семья',
                sentences: [
                    { ru: 'Это моя мама', tokens: ['был', 'минең', 'әсәй'], extras: ['атай', 'һин'] },
                    { ru: 'Моя семья большая', tokens: ['минең', 'ғаилә', 'ҙур'], extras: ['бәләкәй', 'беҙ'] },
                    { ru: 'Я люблю маму', tokens: ['мин', 'әсәйемде', 'яратам'], extras: ['атайымды', 'беләм'] },
                    { ru: 'Он мой брат', tokens: ['ул', 'минең', 'ағай'], extras: ['һеңле', 'уҡытыусы'] },
                    { ru: 'Мы живём вместе', tokens: ['беҙ', 'бергә', 'йәшәйбеҙ'], extras: ['улар', 'эшләйбеҙ'] },
                ],
            },
            {
                id: 3,
                title: 'Природа',
                sentences: [
                    { ru: 'Солнце светит', tokens: ['ҡояш', 'яҡтыра'], extras: ['ай', 'яңғырай'] },
                    { ru: 'Вода холодная', tokens: ['һыу', 'һалҡын'], extras: ['йылы', 'ер'] },
                    { ru: 'Небо синее', tokens: ['күк', 'зәңгәр'], extras: ['йәшел', 'ер'] },
                    { ru: 'В лесу поют птицы', tokens: ['урманда', 'ҡоштар', 'йырлай'], extras: ['балыҡтар', 'яҡтыра'] },
                    { ru: 'Земля тёплая', tokens: ['ер', 'йылы'], extras: ['һалҡын', 'күк'] },
                ],
            },
            {
                id: 4,
                title: 'Еда',
                sentences: [
                    { ru: 'Я пью чай', tokens: ['мин', 'сәй', 'эсәм'], extras: ['һөт', 'ашайым'] },
                    { ru: 'Хлеб вкусный', tokens: ['икмәк', 'тәмле'], extras: ['бал', 'һалҡын'] },
                    { ru: 'Мама варит кашу', tokens: ['әсәй', 'ботҡа', 'бешерә'], extras: ['атай', 'сәй'] },
                    { ru: 'Я люблю яблоки', tokens: ['мин', 'алма', 'яратам'], extras: ['бал', 'беләм'] },
                    { ru: 'Молоко очень вкусное', tokens: ['һөт', 'бик', 'тәмле'], extras: ['сәй', 'ҙур'] },
                ],
            },
            {
                id: 5,
                title: 'Дом',
                sentences: [
                    { ru: 'Мой дом большой', tokens: ['минең', 'өйөм', 'ҙур'], extras: ['бәләкәй', 'мәктәп'] },
                    { ru: 'В доме есть кошка', tokens: ['өйҙә', 'бер', 'бесәй', 'бар'], extras: ['эт', 'юҡ'] },
                    { ru: 'Я возвращаюсь домой', tokens: ['мин', 'өйгә', 'ҡайтам'], extras: ['мәктәпкә', 'барам'] },
                    { ru: 'Окно открыто', tokens: ['тәҙрә', 'асыҡ'], extras: ['ишек', 'ябыҡ'] },
                    { ru: 'У нас гости', tokens: ['беҙҙә', 'ҡунаҡтар', 'бар'], extras: ['дуҫтар', 'юҡ'] },
                ],
            },
            {
                id: 6,
                title: 'Движение',
                sentences: [
                    { ru: 'Я иду в школу', tokens: ['мин', 'мәктәпкә', 'барам'], extras: ['өйгә', 'ҡайтам'] },
                    { ru: 'Ты говоришь по-башкирски', tokens: ['һин', 'башҡортса', 'һөйләшәһең'], extras: ['уҡыйһың', 'мин'] },
                    { ru: 'Он читает книгу', tokens: ['ул', 'китап', 'уҡый'], extras: ['яҙа', 'гәзит'] },
                    { ru: 'Мы поём песню', tokens: ['беҙ', 'йыр', 'йырлайбыҙ'], extras: ['бейейбеҙ', 'улар'] },
                    { ru: 'Они работают', tokens: ['улар', 'эшләй'], extras: ['уҡый', 'беҙ'] },
                ],
            },
            {
                id: 7,
                title: 'Чувства',
                sentences: [
                    { ru: 'Я счастлив', tokens: ['мин', 'бәхетле'], extras: ['һин', 'арыған'] },
                    { ru: 'Он очень рад', tokens: ['ул', 'бик', 'шат'], extras: ['мин', 'ҡайғылы'] },
                    { ru: 'Мне весело', tokens: ['миңә', 'күңелле'], extras: ['һиңә', 'ҡыйын'] },
                    { ru: 'Ты устал', tokens: ['һин', 'арығанһың'], extras: ['мин', 'шат'] },
                    { ru: 'Мы горды', tokens: ['беҙ', 'ғорур'], extras: ['улар', 'бәхетле'] },
                ],
            },
            {
                id: 8,
                title: 'Культура',
                sentences: [
                    { ru: 'Башкирский язык красивый', tokens: ['башҡорт', 'теле', 'матур'], extras: ['русса', 'ҡыйын'] },
                    { ru: 'Я говорю по-башкирски', tokens: ['мин', 'башҡортса', 'һөйләшәм'], extras: ['уҡыйым', 'һин'] },
                    { ru: 'Эта песня очень красивая', tokens: ['был', 'йыр', 'бик', 'матур'], extras: ['китап', 'ҙур'] },
                    { ru: 'Мы изучаем историю', tokens: ['беҙ', 'тарихты', 'өйрәнәбеҙ'], extras: ['телде', 'беләбеҙ'] },
                    { ru: 'Друзья поют вместе', tokens: ['дуҫтар', 'бергә', 'йырлай'], extras: ['эшләй', 'улар'] },
                ],
            },
        ];

        const trail = document.getElementById('sentenceTrail');
        const modal = document.getElementById('sentenceModal');
        const gameBox = document.getElementById('sentenceGame');
        const resultBox = document.getElementById('sentenceResult');
        const promptRu = document.getElementById('sentencePromptRu');
        const answerBox = document.getElementById('sentenceAnswer');
        const bankBox = document.getElementById('sentenceBank');
        const feedbackEl = document.getElementById('sentenceFeedback');
        const progressFill = document.getElementById('sentenceProgressFill');
        const sessionTitle = document.getElementById('sentenceSessionTitle');
        const sessionKicker = document.getElementById('sentenceSessionKicker');
        const sessionHint = document.getElementById('sentenceSessionHint');
        const checkBtn = document.getElementById('sentenceCheckBtn');
        const clearBtn = document.getElementById('sentenceClearBtn');
        const speakBtn = document.getElementById('sentenceSpeakBtn');
        const retryBtn = document.getElementById('sentenceRetryBtn');
        const nextBtn = document.getElementById('sentenceNextBtn');
        const backBtn = document.getElementById('sentenceBackBtn');
        const closeBtn = document.getElementById('sentenceCloseBtn');
        const resultMascot = document.getElementById('sentenceResultMascot');
        const resultStars = document.getElementById('sentenceResultStars');
        const resultTitle = document.getElementById('sentenceResultTitle');
        const resultText = document.getElementById('sentenceResultText');

        if (!trail || !modal) return;

        let session = null;
        let lastLevelIndex = 0;
        let advanceTimer = null;

        function loadProgress() {
            let data = {};
            try { data = JSON.parse(localStorage.getItem(SENTENCE_KEY) || '{}'); } catch (e) {}
            const stars = {};
            const rawStars = data && data.stars && typeof data.stars === 'object' ? data.stars : {};
            Object.keys(rawStars).forEach((key) => {
                const value = Number(rawStars[key]);
                if (Number.isFinite(value) && value > 0) stars[key] = Math.min(3, Math.floor(value));
            });
            return {
                stars,
                solved: Array.isArray(data.solved) ? data.solved.filter((id) => typeof id === 'string') : [],
            };
        }

        const progress = loadProgress();

        function saveProgress() {
            try { localStorage.setItem(SENTENCE_KEY, JSON.stringify(progress)); } catch (e) {}
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
        const totalStars = () => SENTENCE_LEVELS.reduce((sum, level) => sum + starsOf(level), 0);
        const solvedCount = () => progress.solved.length;
        const completedCount = () => SENTENCE_LEVELS.filter((level) => starsOf(level) > 0).length;
        const unlockedCount = () => Math.max(
            1,
            Math.min(SENTENCE_LEVELS.length, 1 + completedCount() + Math.floor(solvedCount() / 10))
        );

        function firstPlayableIndex() {
            const limit = unlockedCount();
            for (let i = 0; i < limit; i += 1) {
                if (starsOf(SENTENCE_LEVELS[i]) === 0) return i;
            }
            for (let i = 0; i < limit; i += 1) {
                if (starsOf(SENTENCE_LEVELS[i]) < 3) return i;
            }
            return -1;
        }

        function stateFor(index) {
            const stars = starsOf(SENTENCE_LEVELS[index]);
            if (stars >= 3) return 'done';
            if (index >= unlockedCount()) return 'locked';
            if (index === firstPlayableIndex()) return 'current';
            return stars > 0 ? 'replay' : 'open';
        }

        function tierFor(solved) {
            if (solved >= 30) return 'СТУПЕНЬ B1';
            if (solved >= 20) return 'СТУПЕНЬ A2+';
            if (solved >= 10) return 'СТУПЕНЬ A2';
            if (solved >= 5) return 'СТУПЕНЬ A1+';
            return 'СТУПЕНЬ A1';
        }

        function updateStats() {
            const solved = solvedCount();
            const solvedEl = document.getElementById('sentenceSolvedCount');
            const starsEl = document.getElementById('sentenceTotalStars');
            const maxEl = document.getElementById('sentenceStarsMax');
            const tierEl = document.getElementById('sentenceTierLabel');
            const hintEl = document.getElementById('sentenceMapHint');
            if (solvedEl) solvedEl.textContent = String(solved);
            if (starsEl) starsEl.textContent = String(totalStars());
            if (maxEl) maxEl.textContent = String(SENTENCE_LEVELS.length * 3);
            if (tierEl) tierEl.textContent = `${tierFor(solved)} · ${solved} ФРАЗ`;
            if (hintEl) {
                const open = unlockedCount();
                hintEl.textContent = open >= SENTENCE_LEVELS.length
                    ? 'Все уровни открыты. Осталось собрать звёзды!'
                    : `Открыто ${open} из ${SENTENCE_LEVELS.length}. Сурок с флейтой ждёт у доступного уровня.`;
            }
        }

        const SENTENCE_HOG_FOR_STATE = {
            current: 'flayta',
            open: 'zadumchivyy',
            replay: 'dovolnyy',
        };

        function renderMap() {
            const currentIndex = firstPlayableIndex();
            trail.innerHTML = SENTENCE_LEVELS.map((level, index) => {
                const state = stateFor(index);
                const stars = starsOf(level);
                const playable = state === 'current' || state === 'open' || state === 'replay';
                const hog = SENTENCE_HOG_FOR_STATE[state];
                const groundhogMarkup = playable && hog
                    ? `<span class="groundhog ${state === 'current' ? 'groundhog--hero' : 'groundhog--peek'}" aria-hidden="true"><img src="img/${hog}.png" alt="" loading="lazy"></span>`
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
                let meta = '5 фраз';
                if (state === 'current') meta = 'сейчас';
                else if (state === 'replay') meta = 'перепройти';
                else if (state === 'done') meta = 'закрыто';
                else if (state === 'locked') meta = 'впереди';

                let label = `${number} ${level.title}, доступно, 5 фраз`;
                if (state === 'done') label = `${number} ${level.title}, закрыто дощечками, 3 из 3 звёзд`;
                else if (state === 'locked') label = `${number} ${level.title}, впереди, закрыто`;
                else if (stars > 0) label = `${number} ${level.title}, перепройти, ${stars} из 3 звёзд`;
                else if (state === 'current') label = `${number} ${level.title}, сейчас, играть`;

                return `<button type="button" class="level-node level-node--${state}" data-level="${index}"${playable ? '' : ' aria-disabled="true"'} aria-label="${escapeHtml(label)}">
                    <span class="mound mound--${state}">${closure}${groundhogMarkup}${planks}<span class="mound-lip" aria-hidden="true"></span></span>
                    <span class="level-label"><span class="level-num">${number}</span> ${escapeHtml(meaning(level.title))}</span>
                    <span class="level-stars" aria-hidden="true">${starsMarkup}</span>
                    <span class="level-meta">${meta}</span>
                </button>`;
            }).join('');
            if (currentIndex < 0 && SENTENCE_LEVELS.every((level) => starsOf(level) >= 3)) {
                trail.insertAdjacentHTML('beforeend', '<p class="level-trail-done">Все фразы собраны на 3 звезды. Сурок играет на флейте! 🎉</p>');
            }
        }

        function updateControls() {
            const hasAnswer = !!(session && session.answer.length);
            const locked = !session || session.answered;
            checkBtn.disabled = !hasAnswer || locked;
            clearBtn.disabled = !hasAnswer || locked;
        }

        function resetSpeakButton() {
            speakBtn.disabled = true;
            speakBtn.classList.remove('is-loading', 'is-playing');
            const label = speakBtn.querySelector('.sentence-speak-label');
            if (label) label.textContent = 'Прослушать фразу';
        }

        function renderAnswer() {
            answerBox.innerHTML = '';
            if (!session) return;
            session.answer.forEach((token) => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'sentence-token sentence-token--answer';
                button.textContent = token.text;
                button.addEventListener('click', () => removeAnswerToken(token.id));
                answerBox.appendChild(button);
            });
        }

        function renderBank() {
            bankBox.innerHTML = '';
            if (!session) return;
            const used = new Set(session.answer.map((token) => token.id));
            session.tokens.forEach((token) => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'sentence-token';
                button.textContent = token.text;
                if (used.has(token.id)) button.classList.add('is-used');
                button.addEventListener('click', () => addToken(token));
                bankBox.appendChild(button);
            });
        }

        function addToken(token) {
            if (!session || session.answered) return;
            if (session.answer.some((item) => item.id === token.id)) return;
            session.answer.push(token);
            renderAnswer();
            renderBank();
            updateControls();
        }

        function removeAnswerToken(tokenId) {
            if (!session || session.answered) return;
            session.answer = session.answer.filter((token) => token.id !== tokenId);
            renderAnswer();
            renderBank();
            updateControls();
        }

        function clearAnswer() {
            if (!session || session.answered) return;
            session.answer = [];
            feedbackEl.textContent = '';
            feedbackEl.className = 'study-feedback';
            renderAnswer();
            renderBank();
            updateControls();
        }

        function renderQuestion() {
            stopSpeech();
            const sentence = session.order[session.index];
            const total = session.order.length;
            session.answered = false;
            session.answer = [];
            sessionTitle.textContent = `Фраза ${session.index + 1} из ${total}`;
            promptRu.textContent = meaning(sentence.ru);
            progressFill.style.width = `${Math.round((session.index / total) * 100)}%`;
            feedbackEl.textContent = '';
            feedbackEl.className = 'study-feedback';
            answerBox.classList.remove('is-correct', 'is-wrong');
            resetSpeakButton();

            const tokens = [
                ...sentence.tokens.map((text, i) => ({ id: `t${i}`, text })),
                ...sentence.extras.map((text, i) => ({ id: `e${i}`, text })),
            ];
            session.tokens = shuffle(tokens);
            renderAnswer();
            renderBank();
            updateControls();
        }

        function checkSentence() {
            if (!session || session.answered) return;
            const sentence = session.order[session.index];
            const expected = sentence.tokens.join(' ');
            const attempt = session.answer.map((token) => token.text).join(' ');
            session.answered = true;
            updateControls();

            if (attempt === expected) {
                session.correct += 1;
                const solvedId = `${session.level.id}-${session.order[session.index].ru}`;
                if (!progress.solved.includes(solvedId)) {
                    progress.solved.push(solvedId);
                    saveProgress();
                    updateStats();
                }
                answerBox.classList.add('is-correct');
                feedbackEl.textContent = 'Дөрөҫ! Фраза собрана верно.';
                feedbackEl.className = 'study-feedback is-good';
                speakBtn.disabled = false;
                progressFill.style.width = `${Math.round(((session.index + 1) / session.order.length) * 100)}%`;
                speakBashkir(expected, speakBtn);
                clearTimeout(advanceTimer);
                advanceTimer = setTimeout(() => {
                    if (!session) return;
                    session.index += 1;
                    if (session.index >= session.order.length) finishSession();
                    else renderQuestion();
                }, 1300);
            } else {
                session.mistakes += 1;
                answerBox.classList.add('is-wrong');
                feedbackEl.textContent = `Верно так: «${expected}»`;
                feedbackEl.className = 'study-feedback is-bad';
                clearTimeout(advanceTimer);
                advanceTimer = setTimeout(() => {
                    if (!session) return;
                    session.answered = false;
                    session.answer = [];
                    answerBox.classList.remove('is-wrong');
                    feedbackEl.textContent = 'Попробуйте собрать фразу ещё раз.';
                    feedbackEl.className = 'study-feedback';
                    renderAnswer();
                    renderBank();
                    updateControls();
                }, 1700);
            }
        }

        function findNextPlayable(fromIndex) {
            for (let i = fromIndex + 1; i < SENTENCE_LEVELS.length; i += 1) {
                const state = stateFor(i);
                if (state === 'current' || state === 'open' || state === 'replay') return i;
            }
            return -1;
        }

        function finishSession() {
            stopSpeech();
            const level = session.level;
            const levelIndex = session.levelIndex;
            const total = session.order.length;
            const mistakes = session.mistakes;
            const correct = session.correct;
            let stars = 3;
            if (mistakes > 6) stars = 0;
            else if (mistakes > 3) stars = 1;
            else if (mistakes > 0) stars = 2;

            const previous = starsOf(level);
            progress.stars[level.id] = Math.max(previous, stars);
            saveProgress();
            session = null;
            lastLevelIndex = levelIndex;

            renderMap();
            updateStats();

            resultStars.innerHTML = [0, 1, 2]
                .map((n) => `<span class="${n < stars ? 'is-on' : ''}">★</span>`)
                .join('');

            if (stars >= 3) {
                resultMascot.src = 'img/radostnyy.png';
                resultMascot.alt = 'Сурок радуется трём звёздам';
            } else if (stars > 0) {
                resultMascot.src = 'img/dovolnyy.png';
                resultMascot.alt = 'Сурок доволен прогрессом';
            } else {
                resultMascot.src = 'img/grustnyy.png';
                resultMascot.alt = 'Сурок расстроился, но ждёт повторения';
            }

            const titles = ['Стоит повторить', 'Хорошее начало', 'Почти идеально!', 'Ни одной ошибки!'];
            const texts = [
                'Фразы собраны, но ошибок многовато. Перепройдите уровень, чтобы сурок закрыл норку.',
                'Одна звезда. Повторите порядок слов — и результат станет выше.',
                'Две звезды! Ещё немного внимания к порядку слов — и норка закроется дощечками.',
                'Все 5 фраз собраны без единой ошибки. Сурок играет на флейте!',
            ];
            resultTitle.textContent = titles[stars];
            resultText.textContent = texts[stars];
            sessionHint.textContent = `Верно: ${correct} из ${total} · ошибок: ${mistakes}`;
            progressFill.style.width = '100%';
            sessionTitle.textContent = 'Уровень завершён';

            gameBox.classList.add('hidden');
            resultBox.classList.remove('hidden');
            const nextIndex = findNextPlayable(levelIndex);
            retryBtn.classList.toggle('hidden', stars >= 3);
            nextBtn.classList.toggle('hidden', stars < 3 || nextIndex < 0);

            const xp = stars * 10 + correct * 2 + (stars >= 3 ? 5 : 0);
            if (xp > 0) ModelService.awardXp(xp, 'sentence_level').catch(() => {});
        }

        function openSession(levelIndex) {
            const state = stateFor(levelIndex);
            if (state !== 'current' && state !== 'open' && state !== 'replay') return;
            clearTimeout(advanceTimer);
            const level = SENTENCE_LEVELS[levelIndex];
            lastLevelIndex = levelIndex;
            session = {
                level,
                levelIndex,
                order: shuffle(level.sentences),
                index: 0,
                correct: 0,
                mistakes: 0,
                answered: false,
                answer: [],
                tokens: [],
            };
            sessionKicker.textContent = `УРОВЕНЬ ${level.id} · ${meaning(level.title).toUpperCase()}`;
            sessionHint.textContent = 'Соберите башкирскую фразу из слов ниже.';
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
            stopSpeech();
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

        checkBtn.addEventListener('click', checkSentence);
        clearBtn.addEventListener('click', clearAnswer);
        retryBtn.addEventListener('click', () => openSession(lastLevelIndex));
        nextBtn.addEventListener('click', () => {
            const nextIndex = findNextPlayable(lastLevelIndex);
            if (nextIndex >= 0) openSession(nextIndex);
        });
        backBtn.addEventListener('click', closeSession);
        closeBtn.addEventListener('click', closeSession);
        document.getElementById('sentenceModalBackdrop').addEventListener('click', closeSession);

        speakBtn.addEventListener('click', () => {
            if (!session) return;
            const sentence = session.order[session.index];
            if (sentence) speakBashkir(sentence.tokens.join(' '), speakBtn);
        });

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
        let pvpXpGiven = false;

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

        function showPvpResult(yourScore, oppScore, winner, winnerIsYou) {
            let text = `Ничья! Вы: ${yourScore}, соперник: ${oppScore}`;
            if (winner === 'draw' || (winner == null && yourScore === oppScore)) {
                text = `Ничья! Вы: ${yourScore}, соперник: ${oppScore}`;
            } else if (winnerIsYou || (winner == null && yourScore > oppScore)) {
                text = `Вы победили! Вы: ${yourScore}, соперник: ${oppScore}`;
            } else {
                text = `Соперник победил. Вы: ${yourScore}, соперник: ${oppScore}`;
            }
            if (pvpQuestionSlot) pvpQuestionSlot.classList.remove('hidden');
            if (pvpPromptText) pvpPromptText.textContent = text;
            pvpOpts.forEach((b) => { b.disabled = true; });
            findPvpBtn.disabled = false;
            findPvpBtn.textContent = 'Найти соперника';
        }

        async function finishPvp() {
            if (pvpFinished) return;
            pvpFinished = true;
            if (pvpGameTimer) { clearInterval(pvpGameTimer); pvpGameTimer = null; }
            if (pvpPollTimer) { clearInterval(pvpPollTimer); pvpPollTimer = null; }
            try { if (pvpSocket) pvpSocket.send(JSON.stringify({type:'progress', index: pvpCurrentIndex, score: pvpScore, done: true})); } catch (e) {}
            try { sessionStorage.removeItem('beztel_pvp_match_id'); } catch (e) {}
            showPvpResult(pvpScore, pvpOpponentScore);
        }

        let pvpSocket = null;

        findPvpBtn.addEventListener('click', () => {
            if (pvpSocket) return;
            pvpFinished = false;
            pvpXpGiven = false;
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

            const wsUrl = ModelService._wsOrigin() + '/api/v1/pvp/ws?client_id=' + encodeURIComponent(ModelService._clientId) + '&lang=' + encodeURIComponent(ModelService.lang());
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
                    pvpFinished = true;
                    if (pvpGameTimer) { clearInterval(pvpGameTimer); pvpGameTimer = null; }
                    pvpScore = Number(msg.your_score) || 0;
                    pvpOpponentScore = Number(msg.opponent_score) || 0;
                    try { sessionStorage.removeItem('beztel_pvp_match_id'); } catch (e) {}
                    try { sessionStorage.removeItem('beztel_pvp_searching'); } catch (e) {}
                    showPvpResult(pvpScore, pvpOpponentScore, msg.winner, !!msg.winner_is_you);
                    setTimeout(() => { try { if (pvpSocket) pvpSocket.close(); } catch (e) {} pvpSocket = null; }, 400);
                    if (msg.winner_is_you && !pvpXpGiven) {
                        pvpXpGiven = true;
                        ModelService.awardXp(30, 'pvp_win').catch(() => {});
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
        const slot = document.getElementById('leaderboardSlot');
        if (slot && !document.getElementById('lbTabs')) {
            slot.insertAdjacentHTML('beforebegin', `
                <div class="lb-tabs" id="lbTabs">
                    <button type="button" class="lb-tab is-on" data-kind="users">Ученики</button>
                    <button type="button" class="lb-tab" data-kind="classes">Классы</button>
                    <button type="button" class="lb-tab" data-kind="schools">Школы</button>
                </div>
                <div class="lb-tabs" id="lbPeriods">
                    <button type="button" class="lb-tab is-on" data-period="day">День</button>
                    <button type="button" class="lb-tab" data-period="month">Месяц</button>
                    <button type="button" class="lb-tab" data-period="year">Год</button>
                </div>`);
        }
        const titleEl = document.querySelector('.editorial-main .section-title');
        const subEl = document.querySelector('.editorial-main .section-bar-minimal .mono-tiny');
        const titles = {
            users: ['Рейтинг учеников', 'Опыт за выбранный период'],
            classes: ['Рейтинг классов', 'Сумма опыта учеников'],
            schools: ['Рейтинг школ', 'Сумма опыта учеников'],
        };
        let boardPeriod = 'day';
        function boardTable(rows, kind) {
            if (kind === 'users') {
                return `<table class="school-table"><thead><tr><th>#</th><th>Игрок</th><th>Уровень</th><th>XP</th></tr></thead><tbody>
                    ${rows.map((r) => `<tr><td>${r.rank}</td><td>${escapeHtml(r.name)} ${r.avatar || ''}</td><td>${r.level}</td><td>${r.xp}</td></tr>`).join('')}
                </tbody></table>`;
            }
            return `<table class="school-table"><thead><tr><th>#</th><th>${kind === 'schools' ? 'Школа' : 'Класс'}</th><th>Ученики</th><th>XP</th><th>Среднее</th></tr></thead><tbody>
                ${rows.map((r) => `<tr><td>${r.rank}</td><td>${escapeHtml(r.name)}${kind === 'classes' && r.school_name ? ' · ' + escapeHtml(r.school_name) : ''}${r.city ? ' · ' + escapeHtml(r.city) : ''}</td><td>${r.students}</td><td>${r.xp}</td><td>${r.avg_xp}</td></tr>`).join('')}
            </tbody></table>`;
        }
        async function loadLeaderboardPage(kind) {
            if (!slot) return;
            kind = kind || 'users';
            document.querySelectorAll('#lbTabs .lb-tab').forEach((btn) => {
                btn.classList.toggle('is-on', btn.dataset.kind === kind);
            });
            const periods = document.getElementById('lbPeriods');
            if (periods) periods.classList.toggle('hidden', kind !== 'users');
            if (titleEl && titles[kind]) titleEl.textContent = titles[kind][0];
            if (subEl && titles[kind]) subEl.textContent = titles[kind][1];
            slot.classList.add('empty-slot-box');
            slot.textContent = 'Загрузка...';
            try {
                const path = kind === 'users'
                    ? '/api/leaderboard/users?limit=50&period=' + encodeURIComponent(boardPeriod)
                    : '/api/v1/school/rankings/' + kind;
                const res = await fetch(ModelService._origin() + path, { headers: ModelService._tgHeaders() });
                if (!res.ok) throw new Error('API error');
                const rows = await res.json();
                slot.classList.remove('empty-slot-box');
                const empty = kind === 'users'
                    ? '<p>За этот период опыта пока нет. Он появится после занятий.</p>'
                    : '<p>Пока пусто. Школы и классы появятся, когда админ их создаст.</p>';
                slot.innerHTML = rows.length ? boardTable(rows, kind) : empty;
            } catch (e) {
                slot.innerHTML = '<p>Не удалось загрузить рейтинг.</p>';
            }
        }
        const tabs = document.getElementById('lbTabs');
        if (tabs) {
            tabs.addEventListener('click', (event) => {
                const btn = event.target.closest('.lb-tab');
                if (btn) loadLeaderboardPage(btn.dataset.kind);
            });
        }
        const periodTabs = document.getElementById('lbPeriods');
        if (periodTabs) {
            periodTabs.addEventListener('click', (event) => {
                const btn = event.target.closest('.lb-tab');
                if (!btn) return;
                boardPeriod = btn.dataset.period || 'day';
                periodTabs.querySelectorAll('.lb-tab').forEach((item) => {
                    item.classList.toggle('is-on', item === btn);
                });
                loadLeaderboardPage('users');
            });
        }
        loadLeaderboardPage('users');
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
            uiLangSelect.value = ModelService.lang();
            uiLangSelect.addEventListener('change', () => ModelService.setLang(uiLangSelect.value));
        }
        if (chatLangSelectProfile) {
            chatLangSelectProfile.value = ModelService.lang();
            chatLangSelectProfile.addEventListener('change', () => ModelService.setLang(chatLangSelectProfile.value));
        }
    }
});
