# -*- coding: utf-8 -*-
import asyncio
import os
import platform
import re
import shutil
import subprocess
import time
import zipfile

import aiofiles
import aiohttp
import requests


async def download_file(url, filename):
    if os.path.isfile(filename):
        return
    print(f"Baixando o arquivo: {filename}")
    async with aiohttp.ClientSession() as session:
        resp = await session.get(url, allow_redirects=True)
        async with aiofiles.open(filename, 'wb') as f:
            await f.write(await resp.read())
    return True

def validate_java(cmd: str, debug: bool = False):
    try:
        java_info = subprocess.check_output(f'{cmd} -version', shell=True, stderr=subprocess.STDOUT)
        java_version = re.search(r'\d+', java_info.decode().split("\r")[0]).group().replace('"', '')
        if int(java_version.split('.')[0]) >= 17:
            return cmd
    except Exception as e:
        if debug:
            print(f"\nFalha ao obter versão do java...\n"
                  f"Path: {cmd} | Erro: {repr(e)}\n")

async def run_process(cmd: str, wait=True, stdout=None, shell=False):

    if shell:
        p = await asyncio.create_subprocess_shell(cmd, stdout=stdout)
    else:
        p = await asyncio.create_subprocess_exec(*cmd.split(" "), stdout=stdout)

    if wait:
        await p.wait()

    return p

async def run_lavalink(
        lavalink_file_url: str = None,
        lavalink_initial_ram: int = 30,
        lavalink_ram_limit: int = 100,
        lavalink_additional_sleep: int = 0,
        lavalink_cpu_cores: int = 1,
        use_jabba: bool = True
):

    if not (java_cmd := validate_java("java")):

        dirs = []

        try:
            dirs.append(os.path.join(os.environ["JAVA_HOME"] + "bin/java"))
        except KeyError:
            pass

        if os.name == "nt":
            dirs.append(os.path.realpath("./.java/zulu17.44.15-ca-jdk17.0.8-win_x64/bin/java"))
        else:
            dirs.extend(
                [
                    os.path.realpath("./.java/jdk-13/bin/java"),
                    os.path.realpath("./.jabba/jdk/zulu@1.17.0-0/bin/java"),
                    os.path.expanduser("~/.jabba/jdk/zulu@1.17.0-0/bin/java"),
                ]
            )

        for cmd in dirs:
            if validate_java(cmd):
                java_cmd = cmd
                break

        if not java_cmd:

            if os.name == "nt":

                try:
                    shutil.rmtree("./.java")
                except:
                    pass

                if platform.architecture()[0] != "64bit":
                    jdk_url = "https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jdk17.0.8-win_i686.zip"
                else:
                    jdk_url = "https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jdk17.0.8-win_x64.zip"

                jdk_filename = "java.zip"

                await download_file(jdk_url, jdk_filename)

                with zipfile.ZipFile(jdk_filename, 'r') as zip_ref:
                    zip_ref.extractall("./.java")

                os.remove(jdk_filename)

                java_cmd = os.path.realpath("./.java/zulu17.44.15-ca-jdk17.0.8-win_x64/bin/java")

            elif use_jabba:

                try:
                    shutil.rmtree("~/.jabba/jdk/zulu@1.17.0-0")
                except:
                    pass

                await download_file("https://github.com/shyiko/jabba/raw/master/install.sh", "install_jabba.sh")
                await run_process("bash install_jabba.sh")
                await run_process("~/.jabba/bin/jabba install zulu@>=1.17.0-0", shell=True)
                os.remove("install_jabba.sh")

                java_cmd = os.path.expanduser("~/.jabba/jdk/zulu@1.17.0-0/bin/java")

            else:
                if not os.path.isdir("./.java"):

                    if platform.architecture()[0] != "64bit":
                        jdk_url = "https://cdn.azul.com/zulu/bin/zulu17.44.15-ca-jdk17.0.8-linux_i686.tar.gz"
                        java_cmd = os.path.realpath("./.java/zulu17.44.15-ca-jdk17.0.8-linux_i686/bin/java")
                    else:
                        jdk_url = "https://cdn.azul.com/zulu/bin/zulu17.44.17-ca-crac-jdk17.0.8-linux_x64.tar.gz"
                        java_cmd = os.path.realpath("./.java/zulu17.44.17-ca-crac-jdk17.0.8-linux_x64/bin/java")

                    jdk_filename = "java.tar.gz"

                    await download_file(jdk_url, jdk_filename)

                    try:
                        shutil.rmtree("./.java")
                    except:
                        pass

                    os.makedirs("./.java")

                    await run_process("tar -zxvf java.tar.gz -C ./.java")
                    os.remove(f"./{jdk_filename}")

                else:
                    java_cmd = os.path.realpath("./.java/zulu17.44.15-ca-jdk17.0.8-linux_i686/bin/java" \
                        if platform.architecture()[0] != "64bit" else \
                        "./.java/zulu17.44.17-ca-crac-jdk17.0.8-linux_x64/bin/java")

    clear_plugins = False

    for filename, url in (
        ("Lavalink.jar", lavalink_file_url),
        ("application.yml", "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/application.yml")
    ):
        if (await download_file(url, filename)):
            clear_plugins = True

    if lavalink_cpu_cores >= 1:
        java_cmd += f" -XX:ActiveProcessorCount={lavalink_cpu_cores}"

    if lavalink_ram_limit > 10:
        java_cmd += f" -Xmx{lavalink_ram_limit}m"

    if 0 < lavalink_initial_ram < lavalink_ram_limit:
        java_cmd += f" -Xms{lavalink_ram_limit}m"

    java_cmd += " -jar Lavalink.jar"

    if clear_plugins:
        try:
            shutil.rmtree("./plugins")
        except:
            pass

    print(f"Iniciando o servidor Lavalink (dependendo da hospedagem o lavalink pode demorar iniciar, "
          f"o que pode ocorrer falhas em algumas tentativas de conexão até ele iniciar totalmente).\n{'-' * 30}")

    lavalink_process = await run_process(java_cmd, stdout=subprocess.DEVNULL, wait=False)

    if lavalink_additional_sleep:
        print(f"Aguarde {lavalink_additional_sleep} segundos...\n{'-' * 30}")
        time.sleep(lavalink_additional_sleep)

    return lavalink_process
