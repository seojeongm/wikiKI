FROM python:3.11-slim

# faiss-cpu requires libgomp for OpenMP threading
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY src/ ./src/
COPY main.py .

RUN useradd --system --no-create-home appuser && chown -R appuser /app
USER appuser

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
