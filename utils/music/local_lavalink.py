# -*- coding: utf-8 -*-
import io
import os
import platform
import subprocess
import time
import zipfile

import requests


def download_file(url, filename):

    if os.path.isfile(filename):
        return

    r = requests.get(url, stream=True)
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
        lavalink_additional_sleep: int = 0,
        *args, **kwargs
):
    version = "v3.4.0"
    base_url = f"https://github.com/PerformanC/NodeLink/releases/download/{version}"

    os_name = platform.system().lower()  # windows, linux, darwin (macos)
    arch = platform.machine().lower()  # x86_64, amd64, arm64, aarch64

    os_map = {
        "windows": "win",
        "linux": "linux",
        "darwin": "macos"
    }

    arch_map = {
        "x86_64": "x64",
        "amd64": "x64",
        "i386": "x86",
        "arm64": "arm64",
        "aarch64": "arm64"
    }

    target_os = os_map.get(os_name)
    target_arch = arch_map.get(arch)

    if not target_os or not target_arch:
        print(f"Sistema ou arquitetura não suportada: {os_name} {arch}")
        return

    download_file("https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/config.default.js", "config.default.js")

    nodelink = f"nodelink-{target_os}-{target_arch}" + ".exe" if target_os == "win" else ""

    if not os.path.isfile(nodelink):

        extension = ".exe.zip" if target_os == "win" else ".zip"
        filename = f"nodelink-{target_os}-{target_arch}{extension}"
        download_url = f"{base_url}/{filename}"

        print(f"Nodelink - Detectado: {os_name} ({arch})")
        print(f"Nodelink - Baixando de: {download_url}...")

        response = requests.get(download_url)
        response.raise_for_status()  # Verifica se houve erro no download

        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(".")
            print(f"Sucesso! Arquivos extraídos na pasta atual: {os.getcwd()}")

    nodelink_process = subprocess.Popen(nodelink.split(), stdout=subprocess.DEVNULL)

    if lavalink_additional_sleep:
        print(f"🕙 - Aguarde {lavalink_additional_sleep} segundos...")
        time.sleep(lavalink_additional_sleep)

    return nodelink_process

if __name__ == "__main__":
    run_lavalink()
    time.sleep(1200)
