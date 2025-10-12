FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir requests aiohttp beautifulsoup4
CMD ["python","scraper.py"]