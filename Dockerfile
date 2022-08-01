FROM python:3.10-slim
COPY --from=openjdk:11-jdk-slim /usr/local/openjdk-11 /usr/local/openjdk-11

ENV JAVA_HOME /usr/local/openjdk-11

RUN update-alternatives --install /usr/bin/java java /usr/local/openjdk-11/bin/java 1

WORKDIR /usr/src/app

COPY . .

RUN apt-get update \
&& apt-get install -y gcc \
&& apt-get install -y git \
&& apt-get clean

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "/usr/src/app/main.py"]

EXPOSE 8080
