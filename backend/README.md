# Backend (FastAPI)

Серверная часть проекта на FastAPI.

## Установка

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Запуск

```bash
uvicorn app.main:app --reload
```

API будет доступен на http://localhost:8000, документация — http://localhost:8000/docs.