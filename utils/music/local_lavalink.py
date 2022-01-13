import subprocess
import requests
import re
import os
import time
import zipfile

def download_file(url, filename):
    if os.path.isfile(filename):
        return
    print(f"Baixando o arquivo: {filename}")
    r = requests.get(url, allow_redirects=True)
    with open(filename, 'wb') as f:
        f.write(r.content)
    r.close()

def run_lavalink(
    lavalink_file_url = None,
    lavalink_initial_ram = 30,
    lavalink_ram_limit = 100,
    lavalink_additional_sleep = None,
    lavalink_cpu_cores = 1,
):

    download_java = False

    if os.path.isdir("./.java"):
        java_path = "./.java/jdk-13/bin/"
    else:
        java_path = os.environ.get('JAVA_HOME', '')
        if java_path:
            java_path = java_path.replace("\\", "/") + "/bin/"

    try:
        javaInfo = subprocess.check_output(f'"{java_path}java"' + ' -version', shell=True, stderr=subprocess.STDOUT)
        javaVersion = re.search(r'"[0-9._]*"', javaInfo.decode().split("\r")[0]).group().replace('"', '')
        if (ver := int(javaVersion.split('.')[0])) < 11:
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
            jdk_url, jdk_filename = ["https://download.java.net/openjdk/jdk13/ri/openjdk-13+33_windows-x64_bin.zip",
                                     "java.zip"]
            download_file(jdk_url, jdk_filename)
            with zipfile.ZipFile(jdk_filename, 'r') as zip_ref:
                zip_ref.extractall("./.java")

            os.remove(jdk_filename)

        else:
            jdk_url, jdk_filename = ["https://download.java.net/openjdk/jdk13/ri/openjdk-13+33_linux-x64_bin.tar.gz",
                                     "java.tar.gz"]
            #download_file(jdk_url, jdk_filename)
            subprocess.call(["wget", jdk_url, "-O", jdk_filename])
            os.makedirs("./.java")
            p = subprocess.Popen(["tar", "-zxvf", "java.tar.gz", "-C", "./.java"])
            p.wait()
            os.remove(f"./{jdk_filename}")

        java_path = "./.java/jdk-13/bin/"

    for filename, url in downloads.items():
        download_file(url, filename)

    cmd = f'{java_path}java'

    try:
        lavalink_initial_ram = int(lavalink_initial_ram)
    except TypeError:
        lavalink_initial_ram = 0

    try:
        lavalink_ram_limit = int(lavalink_ram_limit)
    except TypeError:
        lavalink_ram_limit = 0

    try:
        lavalink_cpu_cores = int(lavalink_cpu_cores)
    except TypeError:
        lavalink_cpu_cores = 0

    if int(lavalink_cpu_cores) >= 1:
        cmd += f" -XX:ActiveProcessorCount={lavalink_cpu_cores}"

    if int(lavalink_ram_limit) > 10:
        cmd += f" -Xmx{lavalink_ram_limit}m"

    if lavalink_initial_ram > 0 and lavalink_initial_ram < lavalink_ram_limit:
        cmd += f" -Xms{lavalink_ram_limit}m"

    cmd += " -jar Lavalink.jar"

    print(f"Iniciando o servidor Lavalink (dependendo da hospedagem o lavalink pode demorar iniciar, "
          f"o que pode ocorrer falhas em algumas tentativas de conexão até ele iniciar totalmente).\n{'-'*30}")

    subprocess.Popen(cmd.split(), stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

    if lavalink_additional_sleep:
        print(f"Aguarde {lavalink_additional_sleep} segundos...\n{'-'*30}")
        time.sleep(lavalink_additional_sleep)
