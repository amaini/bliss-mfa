FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
COPY license_agent ./license_agent
RUN mkdir -p /var/lib/bliss-mfa/license
VOLUME ["/var/lib/bliss-mfa/license"]
EXPOSE 8091
CMD ["uvicorn", "license_agent.main:app", "--host", "0.0.0.0", "--port", "8091"]
