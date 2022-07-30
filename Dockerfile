FROM python:3.10-slim

WORKDIR /usr/src/app

COPY . .

RUN apt-get update \
&& apt-get install -y gcc \
&& apt-get clean

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "/usr/src/app/main.py"]

EXPOSE 8080
