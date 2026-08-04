ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

RUN groupadd -g 1001 streamlit 2>/dev/null || true && \
    useradd -u 1001 -g streamlit -m -s /bin/bash streamlit 2>/dev/null || true

# Core: streamlit + visualization
RUN pip install --no-cache-dir --break-system-packages \
    streamlit==1.39.0 \
    plotly==5.24.0 \
    altair==5.5.0 \
    pillow>=10.0.0 \
    pydeck==0.9.1

# Data engineering
RUN pip install --no-cache-dir --break-system-packages \
    pandas==2.2.3 \
    numpy==1.26.4 \
    scipy==1.14.1 \
    sqlalchemy==2.0.36 \
    pymysql==1.1.1 \
    psycopg2-binary==2.9.10 \
    openpyxl==3.1.5 \
    xlrd==2.0.1 \
    pyarrow==18.1.0 \
    fastparquet==2024.11.0

# ML / AI
RUN pip install --no-cache-dir --break-system-packages \
    scikit-learn==1.6.0 \
    matplotlib==3.10.0

# Utils
RUN pip install --no-cache-dir --break-system-packages \
    requests==2.32.3 \
    httpx==0.27.2 \
    python-dotenv==1.0.1 \
    pyyaml==6.0.2 \
    tabulate==0.9.0 \
    rich==13.9.4 \
    jsonschema==4.23.0

WORKDIR /app

RUN mkdir -p /streamlit-runtime && chown streamlit:streamlit /streamlit-runtime

EXPOSE 8501

USER streamlit

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", \
     "--server.port", "8501", \
     "--server.headless", "true", \
     "--server.enableCORS", "false", \
     "--browser.gatherUsageStats", "false"]
