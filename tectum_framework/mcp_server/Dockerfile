FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# MCP streamable-HTTP transport (served at /mcp)
EXPOSE 8802

CMD ["python", "main.py"]
