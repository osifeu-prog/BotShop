FROM python:3.11-slim

WORKDIR /app
COPY . .

# system deps for web3 (ssl/ca, gcc not required here)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 8080
CMD ["python", "main.py"]
