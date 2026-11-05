FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV AEGIS_PORT=8000 AEGIS_DEMO=1
RUN python scripts/bootstrap.py
EXPOSE 8000
CMD ["python", "run.py"]
