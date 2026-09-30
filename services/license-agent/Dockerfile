FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY license_agent ./license_agent
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
RUN mkdir -p /var/lib/bliss-mfa/license
VOLUME ["/var/lib/bliss-mfa/license"]
EXPOSE 8091
CMD ["uvicorn", "license_agent.main:app", "--host", "0.0.0.0", "--port", "8091"]
