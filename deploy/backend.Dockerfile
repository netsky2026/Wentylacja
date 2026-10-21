FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN grep -v "^emergentintegrations" requirements.txt > req.txt && pip install --no-cache-dir -r req.txt
COPY backend/ .
RUN rm -f .env
EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--proxy-headers", "--forwarded-allow-ips", "*"]
