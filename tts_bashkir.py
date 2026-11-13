"""
Скрипт озвучки башкирского текста с помощью facebook/mms-tts-bak.

Использование:
  python tts_bashkir.py "Сәләм, донъя!"
  python tts_bashkir.py            # ввод текста с клавиатуры
  python tts_bashkir.py --text "..." --out result.wav --play

Лицензия модели: CC-BY-NC 4.0 (некоммерческое использование).
"""
import argparse
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Кэш на диске D (на C мало места)
os.environ.setdefault("HF_HOME", "D:/hf-cache")
os.environ.setdefault("HF_HUB_CACHE", "D:/hf-cache/hub")
os.environ.setdefault("TRANSFORMERS_CACHE", "D:/hf-cache")

import torch
import scipy.io.wavfile
from transformers import VitsModel, AutoTokenizer


MODEL_ID = "facebook/mms-tts-bak"


def synthesize(text: str, out_path: str = "output.wav") -> str:
    print(f"Загружаю модель {MODEL_ID} ...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = VitsModel.from_pretrained(MODEL_ID)

    print(f"Синтезирую: {text!r}")
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        waveform = model(**inputs).waveform

    # Пишем в int16 PCM — так wav читают ASR-модели (onnx-asr, whisper)
    audio = (waveform.squeeze().cpu().numpy() * 32767).astype("int16")
    scipy.io.wavfile.write(out_path, rate=model.config.sampling_rate, data=audio)
    print(f"Сохранено: {os.path.abspath(out_path)} (частота {model.config.sampling_rate} Гц)")
    return out_path


def play_audio(path: str):
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    except Exception as e:
        print(f"Воспроизведение недоступно: {e}")


def main():
    parser = argparse.ArgumentParser(description="Озвучка башкирского текста (MMS-TTS)")
    parser.add_argument("text", nargs="?", help="Текст на башкирском")
    parser.add_argument("--text", "-t", dest="text_opt", help="Текст на башкирском")
    parser.add_argument("--out", "-o", default="output.wav", help="Имя выходного wav-файла")
    parser.add_argument("--play", "-p", action="store_true", help="Воспроизвести после синтеза")
    args = parser.parse_args()

    text = args.text or args.text_opt
    if not text:
        text = input("Введите текст на башкирском: ").strip()
    if not text:
        print("Пустой текст, выход.")
        sys.exit(1)

    out = synthesize(text, args.out)
    if args.play:
        play_audio(out)


if __name__ == "__main__":
    main()