FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# LibreOffice converts Word/PowerPoint uploads; Liberation and Noto give it
# Latin and Arabic fonts. The notes PDF uses the fonts bundled in static/.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-impress \
    fonts-liberation \
    fonts-noto-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user: a bug in a file parser must not give root.
RUN useradd --create-home --uid 10001 app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app *.py ./
COPY --chown=app:app note_templates/ note_templates/
COPY --chown=app:app static/ static/
COPY --chown=app:app .streamlit/config.toml .streamlit/config.toml

USER app
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD curl -fsS "http://localhost:${PORT:-10000}/_stcore/health" || exit 1

# The Gemini key comes from the GEMINI_API_KEY environment variable set in the
# hosting dashboard; it is never baked into the image.
CMD ["sh", "-c", "streamlit run app.py --server.address 0.0.0.0 --server.port ${PORT:-10000} --server.headless true"]
