# -*- coding: utf-8 -*-
import io
import os
import platform
import shutil
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
        for data in r.iter_content(chunk_size=2500 * 1024):
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
                    download_speed = (bytes_downloaded / time_elapsed) / 1024
                    if download_speed >= 1024:
                        download_speed /= 1024
                        speed_txt = "MB/s"
                    else:
                        speed_txt = "KB/s"
                    print(
                        f"Download do arquivo {filename} {current_progress}% concluído ({download_speed:.2f} {speed_txt} / {total_txt})")
                except:
                    print(f"Download do arquivo {filename} {current_progress}% concluído")

    r.close()
    os.rename(f"{filename}.tmp", filename)
    return True


def download_nodejs_portable():
    os_name = platform.system().lower()
    arch = platform.machine().lower()

    os_map = {"windows": "win", "linux": "linux", "darwin": "darwin"}
    arch_map = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}

    target_os = os_map.get(os_name)
    target_arch = arch_map.get(arch)

    if not target_os or not target_arch:
        print(f"Sistema ou arquitetura não suportada: {os_name} {arch}")
        return None

    node_version = "v23.7.0"
    node_dir = f"node-{node_version}-{target_os}-{target_arch}"
    node_dir_abs = os.path.abspath(node_dir)

    def get_npm_path():
        if target_os == "win":
            return os.path.join(node_dir_abs, "npm.cmd")
        return os.path.join(node_dir_abs, "bin", "npm")

    if os.path.isdir(node_dir_abs):
        return get_npm_path()

    extension = ".zip" if target_os == "win" else ".tar.xz"
    base_url = f"https://nodejs.org/dist/{node_version}/{node_dir}{extension}"
    filename = f"{node_dir}{extension}"

    print(f"Node.js não encontrado. Baixando versão portátil {node_version}...")
    try:
        download_file(base_url, filename)
        print(f"Extraindo Node.js...")

        if target_os == "win":
            with zipfile.ZipFile(filename, 'r') as zip_ref:
                zip_ref.extractall(".")
        else:
            import tarfile
            with tarfile.open(filename, 'r:xz') as tar_ref:
                tar_ref.extractall(".")

        if target_os != "win":
            node_bin = os.path.join(node_dir_abs, "bin", "node")
            npm_bin = os.path.join(node_dir_abs, "bin", "npm")
            for bin_file in [node_bin, npm_bin]:
                if os.path.exists(bin_file):
                    os.chmod(bin_file, 0o755)

        os.remove(filename)
        print("Node.js portátil instalado com sucesso!")
        return get_npm_path()

    except Exception as e:
        print(f"Erro ao baixar/extrair Node.js: {e}")
        return None


def run_lavalink(lavalink_additional_sleep: int = 0, *args, **kwargs):
    def get_node_version(npm_path):
        try:
            node_path = npm_path.replace("npm.cmd", "node.exe") if platform.system() == "Windows" else npm_path.replace(
                "npm", "node")
            version_out = subprocess.check_output([node_path, "-v"], text=True).strip()
            return version_out.lstrip('v')
        except:
            return "0.0.0"

    system_npm = shutil.which("npm")
    npm_cmd = system_npm

    if system_npm:
        version = get_node_version(system_npm)
        if version < "22.22.2":
            print(f"Versão do Node.js do sistema ({version}) é insuficiente. Buscando versão portátil...")
            npm_cmd = None

    if npm_cmd is None:
        npm_cmd = download_nodejs_portable()

    if not npm_cmd:
        print("Erro crítico: Node.js não disponível.")
        return

    env = os.environ.copy()
    node_bin_dir = os.path.abspath(os.path.dirname(npm_cmd))
    separator = ";" if platform.system() == "Windows" else ":"
    env["PATH"] = f"{node_bin_dir}{separator}{env.get('PATH', '')}"

    UPDATE_INTERVAL = 2 * 60 * 60
    node_dir = os.path.abspath(os.path.join(os.getcwd(), "NodeLink"))
    deployed_flag = os.path.join(node_dir, ".deployed")
    kw = {"shell": True} if platform.system() == "Windows" else {}

    if not os.path.isfile(deployed_flag):
        subprocess.call(["git", "clone", "https://github.com/PerformanC/NodeLink.git"], **kw)
        subprocess.call(["git", "switch", "dev"], cwd=node_dir, **kw)
        subprocess.call([npm_cmd, "install"], cwd=node_dir, env=env, **kw)
        with open(deployed_flag, "w") as f:
            f.write("")
    else:
        last_update_file = os.path.join(node_dir, ".last_update")
        now = time.time()
        last_update = 0
        if os.path.isfile(last_update_file):
            with open(last_update_file, "r") as f: last_update = float(f.read().strip())

        if now - last_update >= UPDATE_INTERVAL:
            print("Verificando atualizações do NodeLink...")
            subprocess.call(["git", "pull", "--rebase", "--autostash"], cwd=node_dir, **kw)
            subprocess.call([npm_cmd, "install"], cwd=node_dir, env=env, **kw)
            with open(last_update_file, "w") as f: f.write(str(now))

    download_file("https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/config.default.js", "config.js")
    if os.path.isfile("./config.js"):
        shutil.copy("./config.js", os.path.join(node_dir, 'config.js'))

    print(f"Iniciando NodeLink com: {npm_cmd} (Node {get_node_version(npm_cmd)})")

    nodelink_process = subprocess.Popen(
        [npm_cmd, "run", "start"],
        cwd=node_dir,
        env=env,
        **kw
    )

    if lavalink_additional_sleep:
        print(f"🕙 - Aguarde {lavalink_additional_sleep} segundos...")
        time.sleep(lavalink_additional_sleep)

    return nodelink_process


if __name__ == "__main__":
    run_lavalink()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Encerrando...")
