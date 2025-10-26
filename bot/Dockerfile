FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# שכבת מערכת קלה (tzdata כדי שהלוגים יהיו לפי אזור זמן אם תרצה)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# התקנת תלויות
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# קוד האפליקציה
COPY . /app

# ברירת המחדל: מריץ את הבוט
CMD ["python","main.py"]