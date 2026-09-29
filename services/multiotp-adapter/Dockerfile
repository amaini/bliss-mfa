FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /adapter
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

COPY adapter ./adapter

EXPOSE 8090
CMD ["uvicorn", "adapter.main:app", "--host", "0.0.0.0", "--port", "8090"]
