# MuseHeart-MusicBot
## bot de música programado em python com player interativo, comandos de barra + slash, integração com o [last.fm](https://www.last.fm/) e muito mais.

## Página com invites e algumas infos/screenshots da Muse Heart e funcionamento dessa source: [clique aqui](https://gist.github.com/zRitsu/4875008554a00c3c372b2df6dcdf437f#file-muse_heart_invites-md).

[![](https://discordapp.com/api/guilds/911370624507707483/embed.png?style=banner2)](https://discord.gg/KM3NS7D6Zj)

### Algumas Previews:

- Player controller: modo normal/mini-player (skin: default) e suporte a [RPC (Rich Presence)](https://github.com/zRitsu/MuseHeart-MusicBot-RPC-app)

[![](https://i.ibb.co/6tVbfFH/image.png)](https://i.ibb.co/6tVbfFH/image.png)

<details>
<summary>
Mais previews:
</summary>
<br>

- Comandos de barra / Slash commands

[![](https://i.ibb.co/nmhYWrK/muse-heart-slashcommands.png)](https://i.ibb.co/nmhYWrK/muse-heart-slashcommands.png)

- Integração com o [last.fm](https://www.last.fm/) para scrobbles (outras funcionalidades em breve).

[![](https://i.ibb.co/SXm608z/muse-heart-lastfm.png)](https://i.ibb.co/SXm608z/muse-heart-lastfm.png)

- Player controller: modo fixo/estendido com canal e conversa de song requests (skin: default), configurável com o comando: /setup

[![](https://i.ibb.co/5cZ7JGs/image.png)](https://i.ibb.co/5cZ7JGs/image.png)

- Player controller: modo fixo/estendido com canal de song-request em forum com suporte a status automático no canal de voz e palco

[![](https://i.ibb.co/9Hm5cyG/playercontrollerforum.png)](https://i.ibb.co/9Hm5cyG/playercontrollerforum.png)

* Há diversas outras skins, veja todas usando o comando /change_skin (você também pode criar outras, use os modelos padrões que estão na pasta [skins](utils/music/skins/) como referência, crie uma cópia com outro nome e modifique a seu gosto).

</details>

## Teste agora mesmo criando/reusando um bot próprio com essa source fazendo deploy em um dos serviços abaixo:

---

<details>
<summary>
Repl.it
</summary>

Link do guia com imagens: https://gist.github.com/zRitsu/70737984cbe163f890dae05a80a3ddbe
</details>

---

<details>
<summary>
Render.com
</summary>
<br>

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/zRitsu/MuseHeart-MusicBot/tree/main)

* **[ 1 ]** - No campo **TOKEN_BOT_1** coloque o token do bot **( [tutorial de como obter](https://www.youtube.com/watch?v=lfdmZQySTXE) )**. `Nota: Caso queira, no campo TOKEN você pode incluir token de mais bots para ter bots extras pra ativar o suporte a multi-voice incluindo mais tokens no value (separando com espaços).`


* **[ 2 ]** - No campo **DEFAULT_PREFIX** coloque um prefixo para o bot.


* **[ 3 ]** - Nos campos **SPOTIFY_CLIENT_ID** e **SPOTIFY_CLIENT_SECRET** coloque as suas keys do spotify **( [tutorial de como obter](https://www.youtube.com/watch?v=ceKQjWiCyWE) )**.


* **[ 4 ]** - No campo **MONGO** coloque o link da sua database do MongoDB **( [tutorial de como obter](https://www.youtube.com/watch?v=x1Gq5beRx9k) )**.


* **[ 5 ]** - Clique em Apply e aguarde o processo de build até o bot iniciar (isso pode demorar bastante, no mínimo uns 13 minutos ou mais para o deploy ser finalizado + bot iniciar + servidor lavalink iniciar).
</details>

---

<details>
<summary>
Gitpod
</summary>
<br>

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/zRitsu/MuseHeart-MusicBot)

* **[ 1 ]** - Abra o arquivo .env e coloque o token do bot no campo apropriado (caso não tenha, veja como obter com este tutorial [tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE) de como obter). Também altamente recomendo usar mongodb, procure onde tem MONGO= no arquivo .env e nele coloque o link da sua db do mongodb (caso não tenha, veja como obter por este [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)).


* **[ 2 ]** - Clique com botão direito em cima do arquivo main.py e depois clique em: Run Python File in Terminal.


* **Nota 1:** Requer verificação da conta por número de celular/mobile.
* **Nota 2:** Não esqueça de ir na lista de [workspaces](https://gitpod.io/workspaces) e clicar nos 3 pontinhos do projeto e depois clicar em **pin**. `(isso evitará o worskpace ser deletado após 14 dias inativo)`
* **Nota 3:** Não use o gitpod para hospedar / manter o bot online, pois a mesma tem bastante limitações no plano gratuito (mais informações [nesse link](https://www.gitpod.io/pricing)).
</details>

---

<details>
<summary>
Hospedando no seu próprio PC/VPS (windows/linux)
</summary>
<br>

### Requisitos:

* Python 3.9, 3.10 ou 3.11<br/>
[Download pela Microsoft Store](https://apps.microsoft.com/store/detail/9PJPW5LDXLZ5?hl=pt-br&gl=BR) (Recomendável para usuários do windows 10/11).<br/>
[Download direto do site oficial](https://www.python.org/downloads/release/python-3117/) (Marque esta opção ao instalar: **Add python to the PATH**)
* [Git](https://git-scm.com/downloads) (Não escolha a versão portable)</br>

* [JDK 17](https://www.azul.com/downloads) ou superior (Windows e Linux não é necessário instalar, ele é baixado automaticamente)</br>

`Nota: esta source requer no mínimo 512mb de RAM E 1Ghz de CPU para rodar normalmente (caso rode o Lavalink na mesma instância do bot considerando que o bot seja privado).`

### Iniciar bot (guia rápido):

* Baixe esta source como [zip](https://github.com/zRitsu/MuseHeart-MusicBot/archive/refs/heads/main.zip) e extraia em seguida (Ou use o comando abaixo no terminal/cmd e abra a pasta em seguida):
```shell
git clone https://github.com/zRitsu/MuseHeart-MusicBot.git
```
* dê clique-duplo no arquivo source_setup.sh (ou apenas setup caso o seu windows não esteja exibindo extensões de arquivo) e aguarde.</br>
`Caso esteja usando linux use o comando no terminal:` 
```shell
bash source_setup.sh
```
* Vai aparecer um arquivo com nome **.env**, edite ele e coloque o token do bot no campo apropriado (você também pode editar outras coisas deste mesmo arquivo caso queira fazer ajustes específicos no bot).</br>
`Nota: Caso não tenha criado uma conta de bot,` [veja este tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE) `para criar seu bot e obter o token necessário.`</br>`Também altamente recomendo usar mongodb, procure onde tem MONGO= no arquivo .env e nele coloque o link da sua db do mongodb (caso não tenha, veja como obter por este` [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)`). ` 
* Agora basta apenas abrir o arquivo source_start_win.bat para iniciar o bot se o seu sistema for windows, caso seja linux dê clique duplo no start.sh (ou se preferir execute o bot usando o comando abaixo):
```shell
bash source_start.sh
```

### Notas:

* Para atualizar seu bot dê um clique duplo no update.sh (windows), p/ Linux use o comando no shell/terminal:
```shell
bash source_update.sh
```
`Ao atualizar, há chance de qualquer alteração manual feita ser perdida (caso não seja um fork desta source)...`<br/>

`Obs: Caso esteja rodando a source diretamente de uma máquina com windows (e que tenha git instalado) apenas dê um duplo-click no arquivo source_update.sh`
</details>

---

Nota: há mais alguns guias na [wiki](https://github.com/zRitsu/MuseHeart-MusicBot/wiki).

### Observações importantes:

* Você pode usar essa source como alternativa de self-hosting do meu bot principal (Muse Heart) pra hospedar/rodar seu próprio bot de música para uso privado ou em servidores públicos no qual você gerencia (que você tenha permissão de adicionar seu próprio bot no servidor). Entretanto não recomendo distribuir o bot usando essa source publicamente por não estar otimizado o suficiente pra lidar com alta demanda de servidores, mas se mesmo assim decidir fazer isso o bot terá que estar sob a [licença](/LICENSE) da source original e dependendo de onde o bot estiver sendo divulgado (ex: botlists) há possibilidade de seu bot ser apontado pelo uso dessa source.


* Recomendo usar a source atual sem alterações no code. Caso queira fazer modificações (e principalmente adicionar novas funcionalidades) é altamente recomendável que tenha conhecimento em python, disnake, lavalink e etc. E caso queira manter sua source modificada com updates em dias usando a source base também recomendo ter conhecimento em git (pelo menos o necessário pra fazer um merge sem erros).


* Não será fornecido suporte caso modifique a source atual (exceto para custom skins), pois atualizo ela com frequência e versões modificadas tendem a ficarem desatualizadas dificultando dar suporte por esse motivo (além de que dependendo da modificação ou implementação poder gerar erros desconhecidos que dificulta ao tentar resolver o problema e de eu exigir usar métodos pra atualizar o code que geralmente desfaz essas alterações).


* Caso queira postar algum vídeo/tutorial usando essa source, você está totalmente livre para usá-la pra essa finalidade desde que esteja de acordo com os termos citados nos parágrafos acima.

---

### Caso tenha algum problema, poste uma [issue](https://github.com/zRitsu/MuseHeart-MusicBot/issues) detalhando o problema.


## Agradecimentos especiais e créditos:

* [DisnakeDev](https://github.com/DisnakeDev) (disnake) e ao Rapptz pelo [discord.py](https://github.com/Rapptz/discord.py) original
* [Pythonista Guild](https://github.com/PythonistaGuild) (wavelink)
* [Lavalink-Devs](https://github.com/lavalink-devs) (lavalink e lavaplayer)
* [DarrenOfficial](https://lavalink-list.darrennathanael.com/) Lavalink serverlist (Usuários que publicaram seus servidores lavalink estão listados no comando about junto com website/link).
* E a todos os membros que me me ajudaram bastante com reports de erros (sendo nas [issues](https://github.com/zRitsu/MuseHeart-MusicBot/issues) e no servidor do discord)
* Demais atribuições podem ser conferidas no [dependency graph](https://github.com/zRitsu/MuseHeart-MusicBot/network/dependencies)
