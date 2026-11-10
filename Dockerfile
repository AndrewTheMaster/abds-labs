FROM python:3.12-slim

WORKDIR /app

COPY app/ /app/app/

ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "-m", "app.main"]
