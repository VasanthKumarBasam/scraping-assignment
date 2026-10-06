# Optional: run the whole pipeline in a container.
#   docker build -t scraping-assignment .
#   docker run --rm -v "$(pwd)/output:/app/output" -v "$(pwd)/logs:/app/logs" scraping-assignment
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
