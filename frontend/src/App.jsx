import { useState, useRef, useEffect } from "react";

const API = "http://localhost:8000";

const LANGS = [
  { code: "ru", label: "Русский", flag: "🇷🇺" },
  { code: "kk", label: "Казахский", flag: "🇰🇿" },
  { code: "zh", label: "Китайский", flag: "🇨🇳" },
];

// Конвертирует webm/opus из MediaRecorder в WAV 16-bit mono 16 kHz (формат, который понимает ASR)
async function webmToWav(blob) {
  const arrayBuf = await blob.arrayBuffer();
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const decoded = await audioCtx.decodeAudioData(arrayBuf);
  const targetRate = 16000;

  // Ресемплирование в 16 кГц
  const ratio = targetRate / decoded.sampleRate;
  const length = Math.floor(decoded.duration * targetRate);
  const offline = new OfflineAudioContext(1, Math.max(1, length), targetRate);
  const src = offline.createBufferSource();
  src.buffer = decoded;
  src.connect(offline.destination);
  src.start();
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);
  await audioCtx.close();

  // Кодируем в WAV (PCM 16-bit mono)
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, targetRate, true);
  view.setUint32(28, targetRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [targetLang, setTargetLang] = useState("ru");
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const bottomRef = useRef(null);

  const toggleRecording = async () => {
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setLoading(true);
        try {
          const wavBlob = await webmToWav(blob);
          const form = new FormData();
          form.append("file", wavBlob, "audio.wav");
          const r = await fetch(`${API}/asr`, { method: "POST", body: form });
          const data = await r.json();
          if (data.text) {
            setInput(data.text);
          } else if (data.error) {
            alert("Ошибка распознавания: " + data.error);
          }
        } catch (e) {
          console.error(e);
        } finally {
          setLoading(false);
          stream.getTracks().forEach((t) => t.stop());
        }
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch (e) {
      alert("Микрофон недоступен: " + e.message);
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = { role: "user", text: input.trim() };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const r = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg.text, target_lang: targetLang }),
      });
      const data = await r.json();
      setMessages((m) => [...m, { role: "assistant", text_ba: data.text_ba, translation: data.translation, audio_url: data.audio_url }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text_ba: "Ошибка соединения", translation: "", audio_url: null }]);
    } finally {
      setLoading(false);
    }
  };

  const playAudio = (url) => {
    if (url) new Audio(`${API}${url}`).play();
  };

  return (
    <div style={{ fontFamily: "sans-serif", maxWidth: 600, margin: "0 auto", padding: 16, height: "100vh", display: "flex", flexDirection: "column" }}>
      <header style={{ padding: "12px 0", borderBottom: "1px solid #eee", marginBottom: 12 }}>
        <h1 style={{ fontSize: 20, margin: 0 }}>🐝 Чат-репетитор по башкирскому</h1>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          {LANGS.map((l) => (
            <button key={l.code} onClick={() => setTargetLang(l.code)}
              style={{ padding: "6px 12px", borderRadius: 16, border: targetLang === l.code ? "2px solid #FFC800" : "1px solid #ddd", background: targetLang === l.code ? "#FFF8E1" : "white", cursor: "pointer" }}>
              {l.flag} {l.label}
            </button>
          ))}
        </div>
      </header>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 12, display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{ maxWidth: "80%", padding: "10px 14px", borderRadius: 16, background: m.role === "user" ? "#DCF8C6" : "#F1F0F0" }}>
              {m.role === "user" ? (
                <div>{m.text}</div>
              ) : (
                <>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{m.text_ba}</div>
                  {m.translation && <div style={{ fontSize: 13, color: "#555", fontStyle: "italic" }}>→ {m.translation}</div>}
                  {m.audio_url && (
                    <button onClick={() => playAudio(m.audio_url)} style={{ marginTop: 6, background: "none", border: "none", cursor: "pointer", fontSize: 20 }}>🔊</button>
                  )}
                </>
              )}
            </div>
          </div>
        ))}
        {loading && <div style={{ color: "#888", fontStyle: "italic" }}>🐝 Думаю...</div>}
        <div ref={bottomRef} />
      </div>

      <div style={{ display: "flex", gap: 8, padding: "12px 0", borderTop: "1px solid #eee" }}>
        <button onClick={toggleRecording} disabled={loading}
          style={{ padding: "10px 14px", borderRadius: 20, border: "none", background: recording ? "#FF4B4B" : "#FFF8E1", cursor: "pointer", fontSize: 20 }}>
          {recording ? "⏹" : "🎤"}
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Напиши сообщение..."
          style={{ flex: 1, padding: "10px 14px", borderRadius: 20, border: "1px solid #ddd", outline: "none" }}
        />
        <button onClick={send} disabled={loading || !input.trim()}
          style={{ padding: "10px 18px", borderRadius: 20, border: "none", background: "#FFC800", cursor: "pointer", fontWeight: 700 }}>
          Отправить
        </button>
      </div>
    </div>
  );
}