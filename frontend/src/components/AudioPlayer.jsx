import { useEffect, useRef, useState } from "react";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

function fmt(t) {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function AudioPlayer({ src, api, compact = false }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [loaded, setLoaded] = useState(false);

  const url = src ? (src.startsWith("http") ? src : `${api}${src}`) : null;

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    a.playbackRate = rate;
    a.volume = volume;
  }, [rate, volume]);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onTime = () => setCurrent(a.currentTime);
    const onMeta = () => {
      setDuration(a.duration || 0);
      setLoaded(true);
    };
    const onEnd = () => setPlaying(false);
    const onRate = () => setRate(a.playbackRate);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("durationchange", onMeta);
    a.addEventListener("ended", onEnd);
    a.addEventListener("ratechange", onRate);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("durationchange", onMeta);
      a.removeEventListener("ended", onEnd);
      a.removeEventListener("ratechange", onRate);
    };
  }, [url]);

  // Сброс позиции при смене трека
  useEffect(() => {
    setCurrent(0);
    setPlaying(false);
    setLoaded(false);
  }, [url]);

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      a.play().catch(() => {});
      setPlaying(true);
    } else {
      a.pause();
      setPlaying(false);
    }
  };

  const seek = (delta) => {
    const a = audioRef.current;
    if (!a) return;
    a.currentTime = Math.max(0, Math.min(a.duration || 0, a.currentTime + delta));
    setCurrent(a.currentTime);
  };

  const seekTo = (e) => {
    const a = audioRef.current;
    if (!a) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    a.currentTime = ratio * (a.duration || 0);
    setCurrent(a.currentTime);
  };

  const changeRate = (v) => {
    setRate(v);
    if (audioRef.current) audioRef.current.playbackRate = v;
  };

  if (!url) return null;

  const btn = {
    border: "none",
    background: "transparent",
    cursor: "pointer",
    fontSize: compact ? 18 : 20,
    padding: "2px 4px",
    lineHeight: 1,
  };
  const small = { fontSize: 11, color: "#666", fontWeight: 700 };

  if (compact) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 6 }}>
        <audio ref={audioRef} src={url} preload="metadata" />
        <button style={btn} onClick={() => seek(-5)} title="Назад 5 сек">⏪</button>
        <button style={btn} onClick={toggle} title={playing ? "Пауза" : "Играть"}>{playing ? "⏸" : "▶"}</button>
        <button style={btn} onClick={() => seek(5)} title="Вперёд 5 сек">⏩</button>
        <select
          value={rate}
          onChange={(e) => changeRate(Number(e.target.value))}
          style={{ fontSize: 11, border: "1px solid #ddd", borderRadius: 6, padding: "1px 2px", background: "white" }}
        >
          {SPEEDS.map((s) => (
            <option key={s} value={s}>{s}×</option>
          ))}
        </select>
        <span style={small}>{fmt(current)} / {fmt(duration)}</span>
      </div>
    );
  }

  return (
    <div style={{ background: "#FAFAFA", border: "1px solid #E5E5E5", borderRadius: 12, padding: 12, marginTop: 8 }}>
      <audio ref={audioRef} src={url} preload="metadata" />

      {/* Прогресс */}
      <div
        onClick={seekTo}
        style={{ height: 10, background: "#E5E5E5", borderRadius: 6, cursor: "pointer", position: "relative", marginBottom: 10 }}
        title="Перемотать"
      >
        <div
          style={{
            height: "100%",
            width: duration ? `${(current / duration) * 100}%` : "0%",
            background: "#FFC800",
            borderRadius: 6,
          }}
        />
      </div>

      {/* Время */}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#777", marginBottom: 8 }}>
        <span>{fmt(current)}</span>
        <span>{fmt(duration)}{!loaded && " (загрузка...)"}</span>
      </div>

      {/* Управление */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <button style={btn} onClick={() => seek(-10)} title="Назад 10 сек">⏮</button>
        <button style={btn} onClick={() => seek(-5)} title="Назад 5 сек">⏪</button>
        <button
          onClick={toggle}
          style={{ border: "none", background: "#FFC800", color: "#2B2B2B", width: 38, height: 38, borderRadius: "50%", fontSize: 18, cursor: "pointer", fontWeight: 800 }}
          title={playing ? "Пауза" : "Играть"}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <button style={btn} onClick={() => seek(5)} title="Вперёд 5 сек">⏩</button>
        <button style={btn} onClick={() => seek(10)} title="Вперёд 10 сек">⏭</button>

        <span style={{ width: 1, height: 22, background: "#E5E5E5", margin: "0 4px" }} />

        <span style={small}>Скорость</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => changeRate(s)}
            style={{
              ...small,
              padding: "3px 7px",
              borderRadius: 8,
              cursor: "pointer",
              border: rate === s ? "2px solid #FFC800" : "1px solid #E5E5E5",
              background: rate === s ? "#FFF8E1" : "white",
              color: rate === s ? "#7A5C00" : "#666",
            }}
          >
            {s}×
          </button>
        ))}

        <span style={{ width: 1, height: 22, background: "#E5E5E5", margin: "0 4px" }} />

        <span style={small}>🔊</span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={volume}
          onChange={(e) => {
            const v = Number(e.target.value);
            setVolume(v);
            if (audioRef.current) audioRef.current.volume = v;
          }}
          style={{ width: 70 }}
        />
      </div>
    </div>
  );
}
