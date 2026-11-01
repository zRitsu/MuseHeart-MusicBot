# -*- coding: utf-8 -*-
import os
import platform
import shutil
import subprocess
import tempfile
import time
import zipfile
from contextlib import suppress

import requests


def download_file(url, filename):

    if os.path.isfile(filename):
        return

    r = requests.get(url, stream=True, timeout=(15, 120))
    r.raise_for_status()
    total_size = int(r.headers.get('content-length', 0))
    bytes_downloaded = 0
    previows_progress = 0
    start_time = time.time()

    if total_size >= 1024 * 1024:
        total_txt = f"{total_size / (1024 * 1024):.2f} MB"
    else:
        total_txt = f"{total_size / 1024:.2f} KB"

    with open(f"{filename}.tmp", 'wb') as f:

        for data in r.iter_content(chunk_size=2500*1024):
            f.write(data)
            bytes_downloaded += len(data)
            try:
                current_progress = int((bytes_downloaded / total_size) * 100)
            except ZeroDivisionError:
                current_progress = 0

            if current_progress != previows_progress:
                previows_progress = current_progress
                time_elapsed = time.time() - start_time
                try:
                    download_speed = bytes_downloaded / time_elapsed / 1024
                    if download_speed >= 1:
                        download_speed = (download_speed or 1) / 1024
                        speed_txt = "MB/s"
                    else:
                        speed_txt = "KB/s"
                    print(f"Download do arquivo {filename} {current_progress}% concluído ({download_speed:.2f} {speed_txt} / {total_txt})")
                except:
                    print(f"Download do arquivo {filename} {current_progress}% concluído")

    r.close()

    os.rename(f"{filename}.tmp", filename)

    return True

def validate_java(cmd: str, debug: bool = False):
    try:
        java_info = subprocess.check_output(f"{cmd} -version", stderr=subprocess.STDOUT, text=True, shell=True)
        if int(java_info.splitlines()[0].split()[2].strip('"').split('.')[0]) >= 17:
            return cmd
    except Exception as e:
        if debug:
            print(f"\nFalha ao obter versão do java...\n"
                  f"Path: {cmd} | Erro: {repr(e)}\n")

def run_lavalink(
        lavalink_file_url: str = None,
        lavalink_initial_ram: int = 30,
        lavalink_ram_limit: int = 100,
        lavalink_additional_sleep: int = 0,
        lavalink_cpu_cores: int = 1,
        use_jabba: bool = False
):
    # platform.architecture() reports the Python process bitness, not the CPU
    # architecture. Use platform.machine() to distinguish x86_64 from ARM64.
    arch, osname = platform.architecture()
    machine = platform.machine().lower()

    if machine in ("aarch64", "arm64"):
        jdk_arch = "aarch64"
    elif machine in ("x86_64", "amd64"):
        jdk_arch = "amd64"
    elif machine in ("i386", "i486", "i586", "i686", "x86"):
        jdk_arch = "i586"
    else:
        raise RuntimeError(
            f"Arquitetura não suportada para download automático do Java: {machine!r}"
        )

    # Include the machine architecture in the cache path so a previously
    # downloaded x86_64 JDK is never reused on an ARM64 host.
    jdk_platform = f"{platform.system()}-{arch}-{osname}-{machine}"

    tmp_dir = tempfile.gettempdir() if os.name == "nt" else "."

    if not (java_cmd := validate_java("java")):

        dirs = []

        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            dirs.append(os.path.join(java_home, "bin", "java"))

        if os.name == "nt":
            dirs.append(f"{tmp_dir}/.java/{jdk_platform}/bin/java")
            try:
                shutil.rmtree("./.jabba")
            except:
                pass

        else:
            if use_jabba:
                dirs.extend(
                    [
                        os.path.realpath("./.jabba/jdk/zulu@1.17.0-0/bin/java"),
                        os.path.expanduser("./.jabba/jdk/zulu@1.17.0-0/bin/java")
                    ]
                )
                try:
                    shutil.rmtree(f"{tmp_dir}/.java")
                except:
                    pass

            else:
                dirs.append(os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java"))
                try:
                    shutil.rmtree("./.jabba")
                except:
                    pass

        for cmd in dirs:
            if validate_java(cmd):
                java_cmd = cmd
                break

        if not java_cmd:

            if os.name == "nt":

                try:
                    shutil.rmtree(f"{tmp_dir}/.java")
                except:
                    pass

                if platform.architecture()[0] == "64bit":
                    jdk_url = "https://download.bell-sw.com/java/17.0.13+12/bellsoft-jdk17.0.13+12-windows-amd64.zip"
                else:
                    jdk_url = "https://download.bell-sw.com/java/17.0.13+12/bellsoft-jdk17.0.13+12-windows-i586.zip"

                jdk_filename = "java.zip"

                download_file(jdk_url, f"{tmp_dir}/{jdk_filename}")

                os.makedirs(f"{tmp_dir}/.java/{jdk_platform}", exist_ok=True)

                with zipfile.ZipFile(os.path.normpath(f"{tmp_dir}/{jdk_filename}"), 'r') as zip_ref:
                    try:
                        zip_ref.extractall(f"{tmp_dir}/.java")
                    except Exception as e:
                        if isinstance(e, zipfile.BadZipFile):
                            os.remove(f"{tmp_dir}/{jdk_filename}")
                        raise e

                extracted_folder = None

                java_dirs = os.listdir(f"{tmp_dir}/.java")

                for d in os.listdir(f"{tmp_dir}/.java"):
                    if d == jdk_platform:
                        continue
                    if os.path.isfile(f"{tmp_dir}/.java/{d}/bin/java.exe"):
                        extracted_folder = f"{tmp_dir}/.java/{d}"

                if not extracted_folder:
                    raise Exception(
                        f"JDK não encontrando no diretório: {tmp_dir}/.java\n" + "\n".join(java_dirs)
                    )

                for item in os.listdir(extracted_folder):
                    item_path = os.path.join(extracted_folder, item)
                    dest_path = os.path.join(f"{tmp_dir}/.java/{jdk_platform}", item)
                    os.rename(item_path, dest_path)

                with suppress(FileNotFoundError):
                    os.remove(f"{tmp_dir}/{jdk_filename}")
                with suppress(AttributeError):
                    shutil.rmtree(extracted_folder)

                java_cmd = os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java")

            elif use_jabba:

                try:
                    shutil.rmtree("./.jabba/jdk/zulu@1.17.0-0")
                except:
                    pass

                download_file("https://raw.githubusercontent.com/shyiko/jabba/master/install.sh", "install_jabba.sh")
                subprocess.call("bash install_jabba.sh", shell=True)
                subprocess.call("./.jabba/bin/jabba install zulu@1.17.0-0", shell=True)
                os.remove("install_jabba.sh")

                java_cmd = os.path.expanduser("./.jabba/jdk/zulu@1.17.0-0/bin/java")

            else:
                if not os.path.isdir(f"{tmp_dir}/.java/{jdk_platform}"):

                    try:
                        shutil.rmtree(f"{tmp_dir}/.java")
                    except:
                        pass

                    jdk_url = (
                        "https://download.bell-sw.com/java/21.0.3+12/"
                        f"bellsoft-jdk21.0.3+12-linux-{jdk_arch}-lite.tar.gz"
                    )

                    java_cmd = os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java")

                    jdk_filename = "java.tar.gz"

                    download_file(jdk_url, jdk_filename)

                    try:
                        shutil.rmtree(f"{tmp_dir}/.java")
                    except:
                        pass

                    os.makedirs(f"{tmp_dir}/.java/{jdk_platform}")

                    p = subprocess.run(
                        ["tar", "--strip-components=1", "-zxf", jdk_filename,
                         "-C", f"{tmp_dir}/.java/{jdk_platform}"],
                        check=False,
                    )
                    with suppress(FileNotFoundError):
                        os.remove(f"./{jdk_filename}")
                    if p.returncode != 0:
                        shutil.rmtree(f"{tmp_dir}/.java/{jdk_platform}", ignore_errors=True)
                        raise RuntimeError(
                            f"Falha ao extrair o JDK para {jdk_platform} (código {p.returncode})."
                        )

                else:
                    java_cmd = os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java")

    clear_plugins = False

    for filename, url in (
        ("Lavalink.jar", lavalink_file_url),
        ("application.yml", "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/application.yml")
    ):
        if download_file(url, filename):
            clear_plugins = True

    if lavalink_cpu_cores >= 1:
        java_cmd += f" -XX:ActiveProcessorCount={lavalink_cpu_cores}"

    if lavalink_ram_limit > 10:
        java_cmd += f" -Xmx{lavalink_ram_limit}m"

    if 0 < lavalink_initial_ram < lavalink_ram_limit:
        java_cmd += f" -Xms{lavalink_ram_limit}m"

    if os.name != "nt":

        if os.path.isdir("./.tempjar"):
            shutil.rmtree("./.tempjar")

        os.makedirs("./.tempjar/undertow-docbase.80.2258596138812103750")

        java_cmd += f" -Djava.io.tmpdir={os.getcwd()}/.tempjar"

    if clear_plugins:
        try:
            shutil.rmtree("./plugins")
        except:
            pass

    java_cmd += " -jar Lavalink.jar"

    print("🌋 - Iniciando o servidor Lavalink (dependendo da hospedagem o lavalink pode demorar iniciar, "
          "o que pode ocorrer falhas em algumas tentativas de conexão até ele iniciar totalmente).")

    lavalink_process = subprocess.Popen(java_cmd.split(), stdout=subprocess.DEVNULL)

    if lavalink_additional_sleep:
        print(f"🕙 - Aguarde {lavalink_additional_sleep} segundos...")
        time.sleep(lavalink_additional_sleep)

    return lavalink_process

if __name__ == "__main__":
    run_lavalink()
    time.sleep(1200)
