# -*- coding: utf-8 -*-
import os
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import zipfile
from contextlib import suppress

import requests
from ruamel.yaml import YAML

YT_CIPHER_REPO_URL = "https://github.com/rive-hq/yt-cipher.git"
YT_CIPHER_EJS_REPO_URL = "https://github.com/rive-hq/ejs.git"
YT_CIPHER_EJS_COMMIT = "cd4e87f52e87ab6d8b318fd3a817adda6fafa8dc"
NODELINK_REPO_URL = "https://github.com/PerformanC/NodeLink.git"
LOCAL_UPDATE_INTERVAL = 2 * 60 * 60
DEFAULT_LOCAL_SERVER_PORT = 8090
DEFAULT_LOCAL_SERVER_PASSWORD = "youshallnotpass"
DEFAULT_NODELINK_CONFIG_URL = "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/config.default.js"
DEFAULT_LAVALINK_APPLICATION_YML_URL = "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/application.yml"


def download_file(url, filename):
    if not url or os.path.isfile(filename):
        return

    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    total_size = int(r.headers.get("content-length", 0))
    bytes_downloaded = 0
    previows_progress = 0
    start_time = time.time()

    if total_size >= 1024 * 1024:
        total_txt = f"{total_size / (1024 * 1024):.2f} MB"
    else:
        total_txt = f"{total_size / 1024:.2f} KB"

    with open(f"{filename}.tmp", "wb") as f:
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
                        f"Download do arquivo {filename} {current_progress}% concluído ({download_speed:.2f} {speed_txt} / {total_txt})"
                    )
                except Exception:
                    print(f"Download do arquivo {filename} {current_progress}% concluído")

    r.close()
    os.rename(f"{filename}.tmp", filename)
    return True


def parse_version(version: str):
    numbers = re.findall(r"\d+", version or "")
    return tuple(int(n) for n in numbers[:3])


def is_version_at_least(version: str, minimum: str):
    current = parse_version(version)
    required = parse_version(minimum)
    current += (0,) * (len(required) - len(current))
    required += (0,) * (len(current) - len(required))
    return current >= required


def get_local_server_port():
    try:
        return int(os.environ.get("SERVER_PORT") or DEFAULT_LOCAL_SERVER_PORT)
    except ValueError:
        return DEFAULT_LOCAL_SERVER_PORT


def get_local_server_password():
    return os.environ.get("SERVER_PASSWORD") or DEFAULT_LOCAL_SERVER_PASSWORD


def update_git_repo(repo_dir: str, repo_url: str, update_interval: int):
    deployed_flag = os.path.join(repo_dir, ".deployed")
    last_update_file = os.path.join(repo_dir, ".last_update")

    if not os.path.isdir(repo_dir):
        subprocess.check_call(["git", "clone", repo_url, repo_dir])
        with open(deployed_flag, "w", encoding="utf-8") as f:
            f.write("")
        with open(last_update_file, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        return "cloned"

    if not os.path.isfile(deployed_flag):
        with open(deployed_flag, "w", encoding="utf-8") as f:
            f.write("")
        return "prepared"

    now = time.time()
    last_update = 0

    if os.path.isfile(last_update_file):
        with open(last_update_file, "r", encoding="utf-8") as f:
            last_update = float(f.read().strip() or 0)

    if now - last_update < update_interval:
        return "noop"

    repo_name = os.path.basename(repo_dir)
    print(f"Verificando atualizações do {repo_name}...")
    subprocess.call(["git", "pull", "--rebase", "--autostash"], cwd=repo_dir)

    with open(last_update_file, "w", encoding="utf-8") as f:
        f.write(str(now))
    return "updated"


def wait_for_port(host: str, port: int, timeout: int = 30):
    deadline = time.time() + timeout

    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.5)

    return False


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
        print("Extraindo Node.js...")

        if target_os == "win":
            with zipfile.ZipFile(filename, "r") as zip_ref:
                zip_ref.extractall(".")
        else:
            with tarfile.open(filename, "r:xz") as tar_ref:
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


def download_deno_portable():
    os_name = platform.system().lower()
    arch = platform.machine().lower()

    asset_map = {
        ("windows", "x86_64"): "deno-x86_64-pc-windows-msvc.zip",
        ("windows", "amd64"): "deno-x86_64-pc-windows-msvc.zip",
        ("windows", "arm64"): "deno-aarch64-pc-windows-msvc.zip",
        ("linux", "x86_64"): "deno-x86_64-unknown-linux-gnu.zip",
        ("linux", "amd64"): "deno-x86_64-unknown-linux-gnu.zip",
        ("linux", "aarch64"): "deno-aarch64-unknown-linux-gnu.zip",
        ("linux", "arm64"): "deno-aarch64-unknown-linux-gnu.zip",
        ("darwin", "x86_64"): "deno-x86_64-apple-darwin.zip",
        ("darwin", "amd64"): "deno-x86_64-apple-darwin.zip",
        ("darwin", "arm64"): "deno-aarch64-apple-darwin.zip",
    }

    asset_name = asset_map.get((os_name, arch))

    if not asset_name:
        print(f"Sistema ou arquitetura não suportada para Deno: {os_name} {arch}")
        return None

    deno_dir = os.path.abspath(f"deno-portable-{os_name}-{arch}")
    deno_bin = os.path.join(deno_dir, "deno.exe" if os_name == "windows" else "deno")

    if os.path.isfile(deno_bin):
        return deno_bin

    os.makedirs(deno_dir, exist_ok=True)
    url = f"https://github.com/denoland/deno/releases/latest/download/{asset_name}"
    archive_name = os.path.join(deno_dir, asset_name)

    print("Deno não encontrado. Baixando versão portátil...")

    try:
        download_file(url, archive_name)
        with zipfile.ZipFile(archive_name, "r") as zip_ref:
            zip_ref.extractall(deno_dir)
        os.remove(archive_name)

        if os.path.isfile(deno_bin) and os_name != "windows":
            os.chmod(deno_bin, 0o755)

        print("Deno portátil instalado com sucesso!")
        return deno_bin
    except Exception as e:
        print(f"Erro ao baixar/extrair Deno: {e}")
        return None


def get_deno_version(deno_path: str):
    try:
        version_out = subprocess.check_output([deno_path, "-V"], text=True).strip()
        return version_out.split()[1]
    except Exception:
        return "0.0.0"


def get_deno_binary():
    deno_cmd = shutil.which("deno")

    if deno_cmd:
        version = get_deno_version(deno_cmd)
        if is_version_at_least(version, "2.0.0"):
            return deno_cmd

        print(f"Versão do Deno do sistema ({version}) é insuficiente. Buscando versão portátil...")

    return download_deno_portable()


def ensure_yt_cipher_ejs(repo_dir: str):
    ejs_dir = os.path.join(repo_dir, "ejs")

    if not os.path.isdir(ejs_dir):
        subprocess.check_call(["git", "clone", YT_CIPHER_EJS_REPO_URL, ejs_dir])

    subprocess.call(["git", "fetch", "--all"], cwd=ejs_dir)
    subprocess.check_call(["git", "checkout", YT_CIPHER_EJS_COMMIT], cwd=ejs_dir)


def start_yt_cipher(update_interval: int):
    deno_cmd = get_deno_binary()

    if not deno_cmd:
        print("Aviso: Deno não disponível. O yt-cipher local não será iniciado.")
        return None, None, None

    cipher_dir = os.path.abspath(os.path.join(os.getcwd(), "yt-cipher"))
    update_git_repo(cipher_dir, YT_CIPHER_REPO_URL, update_interval=update_interval)
    ensure_yt_cipher_ejs(cipher_dir)

    subprocess.check_call(
        [
            deno_cmd,
            "run",
            "--allow-read",
            "--allow-write",
            "./scripts/patch-ejs.ts",
        ],
        cwd=cipher_dir,
    )

    cipher_host = os.environ.get("YT_CIPHER_HOST", "0.0.0.0")
    cipher_port = int(os.environ.get("YT_CIPHER_PORT", "8001"))
    cipher_token = os.environ.get("YT_CIPHER_API_TOKEN")
    env = os.environ.copy()
    env["HOST"] = cipher_host
    env["PORT"] = str(cipher_port)

    cipher_variant = (
        env.get("YT_CIPHER_VARIANT")
        or env.get("OVERRIDE_SCRIPT_VARIANT")
        or env.get("OVERRIDE_PLAYER_VARIANT")
        or "IAS"
    )
    env["OVERRIDE_SCRIPT_VARIANT"] = cipher_variant
    env["OVERRIDE_PLAYER_VARIANT"] = cipher_variant

    if cipher_token:
        env["API_TOKEN"] = cipher_token

    print(f"Iniciando yt-cipher com: {deno_cmd} (Deno {get_deno_version(deno_cmd)})")
    cipher_process = subprocess.Popen(
        [
            deno_cmd,
            "run",
            "--allow-net",
            "--allow-read",
            "--allow-write",
            "--allow-env",
            "server.ts",
        ],
        cwd=cipher_dir,
        env=env,
    )

    wait_for_port("127.0.0.1", cipher_port, timeout=20)
    return cipher_process, f"http://127.0.0.1:{cipher_port}/", cipher_token


def ensure_nodelink_cipher_config(config_path: str, cipher_url: str, cipher_token: str | None):
    if not os.path.isfile(config_path):
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config_content = f.read()

    token_value = "null" if not cipher_token else f"'{cipher_token}'"
    cipher_block = (
        "      cipher: {\n"
        f"        url: '{cipher_url}',\n"
        f"        token: {token_value}\n"
        "      }"
    )

    new_content, replacements = re.subn(
        r"cipher:\s*\{\s*url:\s*'[^']*',\s*token:\s*(?:null|'[^']*')\s*\}",
        cipher_block,
        config_content,
        count=1,
    )

    if replacements:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(new_content)
    else:
        print("Aviso: bloco de configuração do cipher não foi encontrado no config.js do NodeLink.")


def ensure_lavalink_cipher_config(application_yml_path: str, cipher_url: str, cipher_token: str | None):
    if not os.path.isfile(application_yml_path):
        return

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.explicit_start = True

    with open(application_yml_path, "r", encoding="utf-8") as file:
        yml_data = yaml.load(file.read())

    server_cfg = yml_data.setdefault("server", {})
    server_cfg["port"] = get_local_server_port()
    server_cfg["address"] = "127.0.0.1"

    lavalink_cfg = yml_data.setdefault("lavalink", {})
    lavalink_server = lavalink_cfg.setdefault("server", {})
    lavalink_server["password"] = get_local_server_password()
    lavalink_sources = lavalink_server.setdefault("sources", {})
    lavalink_sources["youtube"] = False

    plugins = yml_data.setdefault("plugins", {})
    youtube = plugins.setdefault("youtube", {})
    youtube["enabled"] = True
    youtube["remoteCipher"] = {
        "url": cipher_url.rstrip("/"),
        "password": cipher_token or "",
        "userAgent": "MuseHeart-MusicBot/Lavalink"
    }

    with open(application_yml_path, "w", encoding="utf-8") as file:
        yaml.dump(yml_data, file)


def validate_java(cmd: str, debug: bool = False):
    try:
        java_info = subprocess.check_output([cmd, "-version"], stderr=subprocess.STDOUT, text=True)
        if int(java_info.splitlines()[0].split()[2].strip('"').split(".")[0]) >= 17:
            return cmd
    except Exception as e:
        if debug:
            print(
                f"\nFalha ao obter versão do java...\n"
                f"Path: {cmd} | Erro: {repr(e)}\n"
            )


def get_system_java(use_jabba: bool = False):
    bits, osname = platform.architecture()
    jdk_platform = f"{platform.system()}-{bits}-{osname}"
    tmp_dir = tempfile.gettempdir() if os.name == "nt" else "."
    java_binary = "java.exe" if os.name == "nt" else "java"

    if java_cmd := validate_java("java"):
        return java_cmd

    search_paths = []

    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        search_paths.append(os.path.join(java_home, "bin", java_binary))

    if os.name == "nt":
        search_paths.append(os.path.join(tmp_dir, ".java", jdk_platform, "bin", java_binary))
        with suppress(Exception):
            shutil.rmtree("./.jabba")
    else:
        if use_jabba:
            search_paths.extend(
                [
                    os.path.realpath("./.jabba/jdk/zulu@1.17.0-0/bin/java"),
                    os.path.expanduser("./.jabba/jdk/zulu@1.17.0-0/bin/java"),
                ]
            )
            with suppress(Exception):
                shutil.rmtree(f"{tmp_dir}/.java")
        else:
            search_paths.append(os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java"))
            with suppress(Exception):
                shutil.rmtree("./.jabba")

    for cmd in search_paths:
        if java_cmd := validate_java(cmd):
            return java_cmd

    if os.name == "nt":
        with suppress(Exception):
            shutil.rmtree(f"{tmp_dir}/.java")

        if platform.architecture()[0] == "64bit":
            jdk_url = "https://download.bell-sw.com/java/17.0.13+12/bellsoft-jdk17.0.13+12-windows-amd64.zip"
        else:
            jdk_url = "https://download.bell-sw.com/java/17.0.13+12/bellsoft-jdk17.0.13+12-windows-i586.zip"

        jdk_filename = os.path.join(tmp_dir, "java.zip")
        download_file(jdk_url, jdk_filename)

        os.makedirs(os.path.join(tmp_dir, ".java", jdk_platform), exist_ok=True)

        with zipfile.ZipFile(os.path.normpath(jdk_filename), "r") as zip_ref:
            try:
                zip_ref.extractall(os.path.join(tmp_dir, ".java"))
            except zipfile.BadZipFile:
                with suppress(FileNotFoundError):
                    os.remove(jdk_filename)
                raise

        extracted_folder = None

        for folder in os.listdir(os.path.join(tmp_dir, ".java")):
            if folder == jdk_platform:
                continue
            candidate = os.path.join(tmp_dir, ".java", folder, "bin", "java.exe")
            if os.path.isfile(candidate):
                extracted_folder = os.path.join(tmp_dir, ".java", folder)
                break

        if not extracted_folder:
            raise Exception(f"JDK não encontrado no diretório: {os.path.join(tmp_dir, '.java')}")

        target_dir = os.path.join(tmp_dir, ".java", jdk_platform)
        for item in os.listdir(extracted_folder):
            os.rename(os.path.join(extracted_folder, item), os.path.join(target_dir, item))

        with suppress(FileNotFoundError):
            os.remove(jdk_filename)
        with suppress(Exception):
            shutil.rmtree(extracted_folder)

        return os.path.realpath(os.path.join(target_dir, "bin", "java"))

    if use_jabba:
        with suppress(Exception):
            shutil.rmtree("./.jabba/jdk/zulu@1.17.0-0")

        download_file("https://raw.githubusercontent.com/shyiko/jabba/master/install.sh", "install_jabba.sh")
        subprocess.check_call("bash install_jabba.sh", shell=True)
        subprocess.check_call("./.jabba/bin/jabba install zulu@1.17.0-0", shell=True)
        os.remove("install_jabba.sh")

        return os.path.expanduser("./.jabba/jdk/zulu@1.17.0-0/bin/java")

    if not os.path.isdir(f"{tmp_dir}/.java/{jdk_platform}"):
        with suppress(Exception):
            shutil.rmtree(f"{tmp_dir}/.java")

        if platform.architecture()[0] != "64bit":
            jdk_url = "https://download.bell-sw.com/java/21.0.3+12/bellsoft-jdk21.0.3+12-linux-i586-lite.tar.gz"
        else:
            jdk_url = "https://download.bell-sw.com/java/21.0.3+12/bellsoft-jdk21.0.3+12-linux-amd64-lite.tar.gz"

        java_cmd = os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java")
        jdk_filename = "java.tar.gz"

        download_file(jdk_url, jdk_filename)
        with suppress(Exception):
            shutil.rmtree(f"{tmp_dir}/.java")
        os.makedirs(f"{tmp_dir}/.java/{jdk_platform}", exist_ok=True)

        subprocess.check_call(
            ["tar", "--strip-components=1", "-zxvf", jdk_filename, "-C", f"{tmp_dir}/.java/{jdk_platform}"]
        )
        os.remove(jdk_filename)
        return java_cmd

    return os.path.realpath(f"{tmp_dir}/.java/{jdk_platform}/bin/java")


def get_node_version(npm_path: str):
    try:
        node_path = npm_path.replace("npm.cmd", "node.exe") if platform.system() == "Windows" else npm_path.replace("npm", "node")
        version_out = subprocess.check_output([node_path, "-v"], text=True).strip()
        return version_out.lstrip("v")
    except Exception:
        return "0.0.0"


def get_npm_binary():
    system_npm = shutil.which("npm")

    if system_npm:
        version = get_node_version(system_npm)
        if is_version_at_least(version, "22.22.2"):
            return system_npm

        print(f"Versão do Node.js do sistema ({version}) é insuficiente. Buscando versão portátil...")

    return download_nodejs_portable()


def run_nodelink_backend(cipher_url: str | None, cipher_token: str | None):
    npm_cmd = get_npm_binary()

    if not npm_cmd:
        raise RuntimeError("Erro crítico: Node.js não disponível.")

    env = os.environ.copy()
    node_bin_dir = os.path.abspath(os.path.dirname(npm_cmd))
    separator = ";" if platform.system() == "Windows" else ":"
    env["PATH"] = f"{node_bin_dir}{separator}{env.get('PATH', '')}"

    node_dir = os.path.abspath(os.path.join(os.getcwd(), "NodeLink"))
    repo_status = update_git_repo(node_dir, NODELINK_REPO_URL, update_interval=LOCAL_UPDATE_INTERVAL)

    subprocess.call(["git", "switch", "dev"], cwd=node_dir)
    if repo_status in {"cloned", "updated"} or not os.path.isdir(os.path.join(node_dir, "node_modules")):
        subprocess.call([npm_cmd, "install"], cwd=node_dir, env=env)

    download_file(DEFAULT_NODELINK_CONFIG_URL, "config.js")
    if os.path.isfile("./config.js"):
        shutil.copy("./config.js", os.path.join(node_dir, "config.js"))

    if cipher_url:
        ensure_nodelink_cipher_config(os.path.join(node_dir, "config.js"), cipher_url, cipher_token)

    print(f"Iniciando NodeLink com: {npm_cmd} (Node {get_node_version(npm_cmd)})")
    return subprocess.Popen([npm_cmd, "run", "start"], cwd=node_dir, env=env)


def run_java_lavalink_backend(
    lavalink_file_url: str | None,
    lavalink_initial_ram: int,
    lavalink_ram_limit: int,
    lavalink_cpu_cores: int,
    use_jabba: bool,
    cipher_url: str | None,
    cipher_token: str | None,
):
    java_cmd = get_system_java(use_jabba=use_jabba)
    clear_plugins = False

    for filename, url in (
        ("Lavalink.jar", lavalink_file_url),
        ("application.yml", DEFAULT_LAVALINK_APPLICATION_YML_URL),
    ):
        if download_file(url, filename):
            clear_plugins = True

    if cipher_url:
        ensure_lavalink_cipher_config("application.yml", cipher_url, cipher_token)

    command = [java_cmd]

    if lavalink_cpu_cores >= 1:
        command.append(f"-XX:ActiveProcessorCount={lavalink_cpu_cores}")

    if lavalink_ram_limit > 10:
        command.append(f"-Xmx{lavalink_ram_limit}m")

    if 0 < lavalink_initial_ram <= lavalink_ram_limit:
        command.append(f"-Xms{lavalink_initial_ram}m")

    if os.name != "nt":
        if os.path.isdir("./.tempjar"):
            shutil.rmtree("./.tempjar")

        os.makedirs("./.tempjar/undertow-docbase.80.2258596138812103750", exist_ok=True)
        command.append(f"-Djava.io.tmpdir={os.getcwd()}/.tempjar")

    if clear_plugins:
        with suppress(Exception):
            shutil.rmtree("./plugins")

    command.extend(["-jar", "Lavalink.jar"])

    print(
        "🌋 - Iniciando o servidor Lavalink (dependendo da hospedagem o lavalink pode demorar iniciar, "
        "o que pode ocorrer falhas em algumas tentativas de conexão até ele iniciar totalmente)."
    )

    return subprocess.Popen(command)


class ManagedProcess:
    def __init__(self, main_process, child_processes=None):
        self._main_process = main_process
        self._child_processes = [p for p in (child_processes or []) if p]
        self.pid = main_process.pid

    def kill(self):
        for process in self._child_processes:
            if process.poll() is None:
                if platform.system() == "Windows":
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(process.pid)])
                else:
                    process.kill()

        if self._main_process.poll() is None:
            if platform.system() == "Windows":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(self._main_process.pid)])
            else:
                self._main_process.kill()

    def poll(self):
        return self._main_process.poll()


def run_lavalink(
    lavalink_file_url: str = None,
    lavalink_initial_ram: int = 30,
    lavalink_ram_limit: int = 100,
    lavalink_additional_sleep: int = 0,
    lavalink_cpu_cores: int = 1,
    use_jabba: bool = False,
    local_audio_server: str = "nodelink",
):
    local_audio_server = (local_audio_server or "nodelink").strip().lower()

    cipher_process = None
    backend_process = None

    try:
        cipher_process, cipher_url, cipher_token = start_yt_cipher(update_interval=LOCAL_UPDATE_INTERVAL)

        if local_audio_server == "lavalink":
            backend_process = run_java_lavalink_backend(
                lavalink_file_url=lavalink_file_url,
                lavalink_initial_ram=lavalink_initial_ram,
                lavalink_ram_limit=lavalink_ram_limit,
                lavalink_cpu_cores=lavalink_cpu_cores,
                use_jabba=use_jabba,
                cipher_url=cipher_url,
                cipher_token=cipher_token,
            )
        elif local_audio_server == "nodelink":
            backend_process = run_nodelink_backend(cipher_url=cipher_url, cipher_token=cipher_token)
        else:
            raise ValueError(
                f"Valor inválido para LOCAL_AUDIO_SERVER: {local_audio_server!r}. Use 'nodelink' ou 'lavalink'."
            )
    except Exception:
        if cipher_process and cipher_process.poll() is None:
            if platform.system() == "Windows":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(cipher_process.pid)])
            else:
                cipher_process.kill()
        raise

    if lavalink_additional_sleep:
        print(f"🕙 - Aguarde {lavalink_additional_sleep} segundos...")
        time.sleep(lavalink_additional_sleep)

    return ManagedProcess(backend_process, [cipher_process])


if __name__ == "__main__":
    run_lavalink()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Encerrando...")
