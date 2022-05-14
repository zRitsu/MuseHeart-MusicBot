# disnake-LL-music-bot
### bot de música programado em python com player interativo, comandos barra/slash, etc. Utilizando as libs disnake e lavalink/YT-DLP.


Tutorial para hospedar seu próprio bot de música deste repositório (Não requer coding no processo): [clique aqui](https://github.com/zRitsu/disnake-LL-music-bot/wiki).
<br/>

Caso não queira criar um bot próprio, há um bot meu já feito e hospedado usando esta source, você pode adicioná-la [clicando aqui](https://discord.com/api/oauth2/authorize?client_id=784891594306093101&permissions=397564505200&scope=bot%20applications.commands).

### Requisitos:

* Python 3.8 ou superior:<br/>
[Download pela Microsoft Store](https://apps.microsoft.com/store/detail/9PJPW5LDXLZ5?hl=pt-br&gl=BR) (Recomendável para usuários do windows 10/11).<br/>
[Download direto do site oficial](https://www.python.org/downloads/) (Marque esta opção ao instalar: **Add python to the PATH**)
* [Git](https://git-scm.com/downloads) (Não escolha a versão portable)</br>

**Requisito para o modo Lavalink (Padrão):**
* [JDK 11](https://www.azul.com/downloads) ou superior (Windows e Linux x64 é baixado automaticamente)</br>
`Nota: este modo requer ter no mínimo 512mb de RAM (caso rode o Lavalink na mesma instância do bot).`

**Requisito para o modo YTDL (FFMPEG):**
* [FFMPEG](https://pt.wikihow.com/Instalar-o-FFmpeg-no-Windows)</br>
`Nota: este modo requer no mínimo 200mb de RAM.`

### Iniciar bot (guia rápido)

* Baixe esta source como [zip](https://github.com/zRitsu/disnake-LL-music-bot/archive/refs/heads/main.zip) e extraia em seguida.
* dê clique-duplo no arquivo setup.sh (ou apenas setup caso o seu windows não esteja exibindo extensões de arquivo) e aguarde.</br>
`Caso esteja usando linux use o comando no terminal: bash setup.sh`
* Vai aparecer um arquivo com nome **.env**, edite ele e coloque o token do bot no campo apropriado (você também pode editar outras coisas deste mesmo arquivo caso queira fazer ajustes específicos no bot).</br>
`Nota: Caso não tenha criado uma conta de bot, acesse este` [link](https://docs.disnake.dev/en/latest/discord.html) `com guia (em inglês) pra criar seu bot e obter o token necessário.` 
* Agora basta apenas abrir o arquivo run.sh para iniciar o bot (caso esteja usando linux use o comando: bash run.sh)

### Notas:

* Para atualizar seu bot dê um clique duplo no update.sh (windows), p/ Linux use o comando no shell/terminal:
```shell
bash update.sh
```
`Ao atualizar, qualquer modificação no code pode ser descartada...`<br/>

`Obs: Caso esteja rodando a source diretamente de uma máquina com windows (e que tenha git instalado) apenas dê um duplo-click no arquivo update.sh`

* Esta source foi criada com intuito para uso de bots privados (não está otimizado o suficiente pra lidar com alta demanda de servidores).
* Usar a source da forma que se encontra, caso queira fazer modificações (e principalmente adicionar novas funcionalidades) é altamente recomendável que tenha conhecimento em python e disnake (e caso queira manter com updates em dias preservando suas modificações, é recomendável ter conhecimento em git também).


### Algumas previews:

- Comandos de barra / Slash commands

![](https://media.discordapp.net/attachments/554468640942981147/944942596814426122/unknown.png)

- Player controller (modo normal/mini-player)

![](https://media.discordapp.net/attachments/554468640942981147/944942948406153276/unknown.png)

- Player controller (modo fixo/estendido com song requests, configurável com o comando: /setup)

![](https://media.discordapp.net/attachments/554468640942981147/944945573834936340/unknown.png)