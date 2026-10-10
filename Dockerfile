FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    IN_DOCKER=true \
    ANONYMIZED_TELEMETRY=false

WORKDIR /app

# 1) Python libraries
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2) Chromium + the Linux libraries it needs (needs root)
RUN playwright install-deps chromium \
    && playwright install chromium \
    && chmod -R a+rX /opt/pw-browsers

# 3) Hugging Face Spaces runs the container as user 1000
RUN useradd -m -u 1000 user \
    && mkdir -p /app/results \
    && chown -R user:user /app
USER user

# 4) App code
COPY --chown=user . /app

# Hugging Face Spaces expects the app on port 7860
EXPOSE 7860
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
