import subprocess
from typing import Optional
import requests
import re
import os
import time
import zipfile
import platform
import shutil


def download_file(url, filename):
    if os.path.isfile(filename):
        return
    print(f"Baixando o arquivo: {filename}")
    r = requests.get(url, allow_redirects=True)
    with open(filename, 'wb') as f:
        f.write(r.content)
    r.close()


def run_lavalink(
        lavalink_file_url: Optional[str] = None,
        lavalink_initial_ram: int = 30,
        lavalink_ram_limit: int = 100,
        lavalink_additional_sleep: int = 0,
        lavalink_cpu_cores: int = 1,
):
    download_java = False

    java_cmd = None

    if not shutil.which("java"):

        dirs = []

        try:
            dirs.append(os.path.join(os.environ["JAVA_HOME"] + "bin/java"))
        except KeyError:
            pass

        dirs.extend(
            [
                "~/.jabba/jdk/zulu@1.17.0-0/bin/java",
                "./.java/jdk-13/bin/java",
            ]
        )

        for d in dirs:
            if shutil.which(d):
                java_cmd = d
                break

        if not java_cmd:
            java_cmd = "java"

    else:

        java_cmd = "java"

        try:
            java_info = subprocess.check_output(f'java -version', shell=True, stderr=subprocess.STDOUT)
            java_version = re.search(r'"[\d._]*"', java_info.decode().split("\r")[0]).group().replace('"', '')
            if (ver := int(java_version.split('.')[0])) < 11:
                print(f"A versão do java/jdk instalado/configurado é incompatível: {ver} (Versão mínima: 11)")
                download_java = True
        except Exception as e:
            print(f"Erro ao obter versão do java: {repr(e)}")
            download_java = True

    downloads = {
        "Lavalink.jar": lavalink_file_url,
        "application.yml": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/application.yml"
    }

    if download_java:

        if os.name == "nt":

            if platform.architecture()[0] != "64bit":
                jdk_url = "https://cdn.azul.com/zulu/bin/zulu11.58.25-ca-jdk11.0.16.1-win_i686.zip"
            else:
                jdk_url = "https://download.java.net/openjdk/jdk13/ri/openjdk-13+33_windows-x64_bin.zip"

            jdk_filename = "java.zip"

            download_file(jdk_url, jdk_filename)

            with zipfile.ZipFile(jdk_filename, 'r') as zip_ref:
                zip_ref.extractall("./.java")

            os.remove(jdk_filename)

            java_cmd = "./.java/jdk-13/bin/java"

        else:
            download_file("https://github.com/shyiko/jabba/raw/master/install.sh", "install_jabba.sh")
            subprocess.call(["bash", "install_jabba.sh", "&&", "~/.jabba/bin/jabba", "install", "zulu@1.17.0-0"])
            os.remove("install_jabba.sh")
            java_cmd = "~/.jabba/jdk/zulu@1.17.0-0/bin/java"

    for filename, url in downloads.items():
        download_file(url, filename)

    if lavalink_cpu_cores >= 1:
        java_cmd += f" -XX:ActiveProcessorCount={lavalink_cpu_cores}"

    if lavalink_ram_limit > 10:
        java_cmd += f" -Xmx{lavalink_ram_limit}m"

    if 0 < lavalink_initial_ram < lavalink_ram_limit:
        java_cmd += f" -Xms{lavalink_ram_limit}m"

    java_cmd += " -jar Lavalink.jar"

    print(f"Iniciando o servidor Lavalink (dependendo da hospedagem o lavalink pode demorar iniciar, "
          f"o que pode ocorrer falhas em algumas tentativas de conexão até ele iniciar totalmente).\n{'-' * 30}")

    lavalink_process = subprocess.Popen(java_cmd.split(), stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    if lavalink_additional_sleep:
        print(f"Aguarde {lavalink_additional_sleep} segundos...\n{'-' * 30}")
        time.sleep(lavalink_additional_sleep)

    return lavalink_process
