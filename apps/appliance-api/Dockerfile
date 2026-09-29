FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY appliance ./appliance
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "appliance.main:app", "--host", "0.0.0.0", "--port", "8000"]
