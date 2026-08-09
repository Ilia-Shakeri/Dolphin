ARG PYTHON_BASE_IMAGE
ARG TARGETPLATFORM
FROM ${PYTHON_BASE_IMAGE}

ARG PYTHON_BASE_IMAGE
ARG TARGETPLATFORM

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.production_settings
WORKDIR /app

COPY requirements.txt ./
RUN python -c "import os, re, sys; value = os.environ.get('PYTHON_BASE_IMAGE', ''); valid = re.fullmatch(r'[^\\s@]+@sha256:[0-9a-f]{64}', value) and sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 13); raise SystemExit(0 if valid else 2)" \
    && test "${TARGETPLATFORM}" = "linux/amd64" \
    && pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.txt
COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/staticfiles \
    && chown appuser:appuser /app/staticfiles
USER appuser

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
