FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# System deps kept minimal; boto3/yfinance/pandas are pure-wheel installs.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# App Runner sets PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Single worker keeps the in-memory debate/WebSocket state coherent.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
