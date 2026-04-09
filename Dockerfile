# syntax=docker/dockerfile:1

FROM python:3.12-alpine AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip wheel --wheel-dir /wheels .


FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache ca-certificates tzdata

WORKDIR /workspace

COPY --from=builder /wheels /wheels
RUN python -m pip install /wheels/*.whl && rm -rf /wheels

ENTRYPOINT ["pretalx-starred-export"]
