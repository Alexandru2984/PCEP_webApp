ARG PYTHON_IMAGE=python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
FROM ${PYTHON_IMAGE} AS dependencies
ENV PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --only-binary=:all: --wheel-dir /wheels -r requirements.txt

FROM ${PYTHON_IMAGE}
ARG PCEP_RELEASE=development
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PCEP_RELEASE=${PCEP_RELEASE}
LABEL org.opencontainers.image.revision=${PCEP_RELEASE}
# The versioned upstream image can lag Debian security updates between rebuilds.
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=dependencies /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels \
    && adduser --disabled-password --gecos "" appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown appuser:appuser /app /app/staticfiles /app/media
COPY --chown=appuser:appuser . .
RUN chmod +x /app/entrypoint.sh
USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
