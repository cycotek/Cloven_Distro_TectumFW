FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn psycopg2-binary sqlalchemy
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
