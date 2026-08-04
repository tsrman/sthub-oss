ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# Run as an unprivileged user — uvicorn/alembic do not need root.
RUN groupadd -g 1001 app 2>/dev/null || true && \
    useradd -u 1001 -g app -m -s /bin/bash app 2>/dev/null || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app/ ./app/
COPY alembic.ini alembic.ini

RUN chown -R app:app /app

EXPOSE 8000

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
