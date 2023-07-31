FROM python:3.7.4-slim-buster

WORKDIR /app
COPY ./app /app

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

CMD ["python", "main.py"]
