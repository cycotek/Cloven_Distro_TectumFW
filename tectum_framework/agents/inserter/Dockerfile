FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir sqlalchemy[asyncio] asyncpg
CMD ["python","insert_nodes.py"]