FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[mlflow]"

# Generate the synthetic dataset, train the model and export demo data at build time,
# so `docker compose up` works without any files committed to git. Takes a few minutes.
ENV MLFLOW_TRACKING_URI=sqlite:////app/mlflow.db MLFLOW_DISABLE_AGENT_HINT=1
RUN python -m smart_reconcile_ml.generator --out data/generated/v1 \
    && python -m smart_reconcile_ml.train --data data/generated/v1 --out models/latest \
    && mkdir -p export \
    && python -m smart_reconcile_ml.export_demo --data data/generated/v1 --out export/demo.json

ENV MODEL_DIR=/app/models/latest FEEDBACK_DIR=/app/feedback
EXPOSE 8000
CMD ["uvicorn", "smart_reconcile_ml.service:app", "--host", "0.0.0.0", "--port", "8000"]
