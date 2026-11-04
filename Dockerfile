FROM python:3.12-slim

WORKDIR /app

COPY app/ /app/app/

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "-u", "app/main.py"]
