# Сайт и API

Запуск всего проекта описан в [корневом README](../README.md).

Коротко, из этой папки, когда база уже работает и в корне заполнен `.env`:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
