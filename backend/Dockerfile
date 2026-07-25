# S2PNexus Backend Dockerfile

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
# build-essential (not just gcc) pulls in g++ + libstdc++ headers, needed to
# compile chroma-hnswlib's C++ extension from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code + migration files
COPY ./app ./app
COPY alembic.ini .
COPY ./alembic ./alembic
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Cloud Run injects $PORT (usually 8080); default to 8000 for local docker-compose
ENV PORT=8000
EXPOSE 8000

# Run migrations, then start the server
CMD ["./entrypoint.sh"]