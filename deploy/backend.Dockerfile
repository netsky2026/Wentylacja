FROM python:3.11-slim
WORKDIR /app
COPY deploy/requirements.prod.txt .
RUN pip install --no-cache-dir -r requirements.prod.txt
COPY backend/ .
RUN rm -f .env
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips", "*"]
