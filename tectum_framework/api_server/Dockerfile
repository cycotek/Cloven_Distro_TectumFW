FROM python:3.11-slim

WORKDIR /app
COPY ./ /app

# Minimal deps; DB libs can be added later
RUN pip install --no-cache-dir fastapi uvicorn[standard]

EXPOSE 8000
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]