ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

RUN groupadd -g 1001 streamlit 2>/dev/null || true && \
    useradd -u 1001 -g streamlit -m -s /bin/bash streamlit 2>/dev/null || true

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

WORKDIR /app

RUN mkdir -p /streamlit-runtime && chown streamlit:streamlit /streamlit-runtime

EXPOSE 8501

USER streamlit

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.enableCORS", "false", \
     "--browser.gatherUsageStats", "false"]
