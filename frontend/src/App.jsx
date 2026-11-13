import { useEffect, useState } from "react";

export default function App() {
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/health`)
      .then((r) => r.json())
      .then((d) => setStatus(d.status))
      .catch(() => setStatus("error"));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>bashkar</h1>
      <p>Backend status: {status}</p>
    </main>
  );
}