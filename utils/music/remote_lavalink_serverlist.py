# pip install requests ou adicione requests no requirements.txt (caso não tenha, crie esse arquivo com o nome requests nele).
import re
import traceback
from configparser import ConfigParser

import requests

lavalink_urls = {
    "ssl": "https://raw.githubusercontent.com/DarrenOfficial/lavalink-list/master/docs/SSL/lavalink-with-ssl.md",
    "non-ssl": "https://raw.githubusercontent.com/DarrenOfficial/lavalink-list/master/docs/NoSSL/lavalink-without-ssl.md",
}

host_regex = re.compile(r'Host\s*:\s*(\S+)')
port_regex = re.compile(r'Port\s*:\s*(\d+)')
password_regex = re.compile(r'Password\s*:\s*"([^"]+)"')
secure_regex = re.compile(r'Secure\s*:\s*(\S+)')

def extract_data_from_md(md):

    data = {}

    if not (host_match := host_regex.search(md)):
        return

    if not (port_match := port_regex.search(md)):
        return

    if not (password_match := password_regex.search(md)):
        return

    data['host'] = host_match.group(1)
    data['port'] = int(port_match.group(1))
    data['password'] = password_match.group(1)

    if (secure_match := secure_regex.search(md)):
        data['secure'] = True if secure_match.group(1).lower() == 'true' else False

    return data

def get_lavalink_servers():

    config = ConfigParser()

    lavalink_nodes = {}

    print(f"Baixando lista de servidores lavalink da fonte: https://lavalink-list.darrennathanael.com/\n"
          "Nota: Devido a esses servidores lavalink serem públicos, os mesmos podem apresentar instabilidade.")

    for url_type, url in lavalink_urls.items():

        markdown = requests.get(url).content.decode("utf-8")

        for host in markdown.split("### Hosted by @ ")[1:]:

            hostinfo = host.split('\n')[0].split("](")
            host_owner = hostinfo[0][1:]
            host_url = hostinfo[1][:-1]
            blocks = host.split("```bash")[1:]

            for n, block in enumerate(blocks):
                data = extract_data_from_md(block)
                if not data or not data.get("host"):
                    continue
                data["website"] = host_url
                identifier = f"{host_owner} - {url_type}" if n != 0 else f"{host_owner} {n + 2} - {url_type}"
                config[identifier] = data
                data["identifier"] = identifier
                lavalink_nodes[identifier] = data

    try:
        with open("auto_lavalink.ini", "w", encoding="utf-8") as f:
            config.write(f)
    except Exception:
        traceback.print_exc()

    return lavalink_nodes

if __name__ == "__main__":
    get_lavalink_servers()
