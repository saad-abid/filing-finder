# FilingFinder app image: the Python server plus the built React page.
# The database runs in its own container and Ollama runs on the host machine
# (see docker-compose.yml). Build and start with:
#   docker compose --profile app up -d --build

# ---- Stage 1: build the React page with Node.js -----------------------------
# Only the finished files (web/dist) are kept; Node.js is not in the final image.
FROM node:20-alpine AS web
WORKDIR /web
# Install packages first (cached until package files change), then copy the code.
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- Stage 2: the Python app --------------------------------------------------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/app/.cache/huggingface
# Run as a normal user, not root.
RUN useradd --create-home app
WORKDIR /app

# Exact package versions; CPU-only PyTorch keeps the image ~1 GB smaller.
COPY requirements-lock.txt ./
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-lock.txt

# The app code, the database schema, the example questions and the built page.
COPY src/ src/
COPY db/ db/
COPY eval/answer_cases.json eval/answer_cases.json
COPY --from=web /web/dist web/dist

# Folders the app writes to: the search-model cache and the filings data.
RUN mkdir -p /home/app/.cache/huggingface /app/data \
    && chown -R app:app /home/app /app/data
USER app

EXPOSE 8000
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
