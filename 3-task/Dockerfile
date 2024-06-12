FROM python:3.12-slim

COPY . /bot

WORKDIR /bot

RUN pip install --no-cache-dir requests

CMD ["python3", "bot.py"]