FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY mock_adapter ./mock_adapter
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
EXPOSE 8090
CMD ["uvicorn", "mock_adapter.main:app", "--host", "0.0.0.0", "--port", "8090"]
