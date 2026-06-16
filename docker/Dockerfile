FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

# Copy dependency files first so this layer is cached when only source changes.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev || uv pip install -r requirements.txt

COPY . .

# Build the RAG index at image build time so the container needs no external
# volume or setup step at runtime.
RUN uv run python -m src.rag.build_index

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
