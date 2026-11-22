# Railway Procfile for independent API & Celery Worker services
web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: celery -A app.worker.celery_app worker --loglevel=INFO -P solo
