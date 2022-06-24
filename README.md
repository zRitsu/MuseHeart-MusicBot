# disnake-LL-music-bot
### bot de música programado em python com player interativo, comandos barra/slash, etc. Utilizando as libs disnake e lavalink/YT-DLP.


Tutorial para hospedar seu próprio bot de música deste repositório (Não requer coding no processo): [clique aqui](https://github.com/zRitsu/disnake-LL-music-bot/wiki).
<br/>

Caso não queira criar um bot próprio, há alguns bots meu já feito e hospedado usando esta source, você pode adicionar um dos meus bots abaixo: 

| ![](https://cdn.discordapp.com/avatars/784891594306093101/bb5355bb0fd46eaca1b89a983d8f4c15.png?size=128)                           | ![](https://cdn.discordapp.com/avatars/825460549419794462/8259b8ec375691b26e964187130a3edf.png?size=128)                               |
|------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------|
| [Muse Heart](https://dsc.gg/muse-heart-music) | [Muse Heart (2)](https://dsc.gg/muse-heart-music-2) |

### Requisitos:

* Python 3.8 ou superior:<br/>
[Download pela Microsoft Store](https://apps.microsoft.com/store/detail/9PJPW5LDXLZ5?hl=pt-br&gl=BR) (Recomendável para usuários do windows 10/11).<br/>
[Download direto do site oficial](https://www.python.org/downloads/) (Marque esta opção ao instalar: **Add python to the PATH**)
* [Git](https://git-scm.com/downloads) (Não escolha a versão portable)</br>

**Requisito para o modo Lavalink (Padrão):**
* [JDK 11](https://www.azul.com/downloads) ou superior (Windows e Linux x64 é baixado automaticamente)</br>
`Nota: este modo requer no mínimo 512mb de RAM (caso rode o Lavalink na mesma instância do bot).`

**Requisito para o modo YTDL/FFMPEG (Experimental):**
* [FFMPEG](https://pt.wikihow.com/Instalar-o-FFmpeg-no-Windows)</br>
`Nota: este modo requer no mínimo 200mb de RAM.`</br>
`Para usar este modo, edite o arquivo .env e altere o valor do YTDLMODE de false para true.`

### Iniciar bot (guia rápido):

* Baixe esta source como [zip](https://github.com/zRitsu/disnake-LL-music-bot/archive/refs/heads/main.zip) e extraia em seguida (Ou use o comando abaixo no terminal/cmd e abra a pasta em seguida):
```shell
git clone https://github.com/zRitsu/disnake-LL-music-bot.git
```
* dê clique-duplo no arquivo setup.sh (ou apenas setup caso o seu windows não esteja exibindo extensões de arquivo) e aguarde.</br>
`Caso esteja usando linux use o comando no terminal:` 
```shell
bash setup.sh
```
* Vai aparecer um arquivo com nome **.env**, edite ele e coloque o token do bot no campo apropriado (você também pode editar outras coisas deste mesmo arquivo caso queira fazer ajustes específicos no bot).</br>
`Nota: Caso não tenha criado uma conta de bot, acesse este` [link](https://docs.disnake.dev/en/latest/discord.html) `com guia (em inglês) pra criar seu bot e obter o token necessário.` 
* Agora basta apenas abrir o arquivo run.sh para iniciar o bot (caso esteja usando linux use o comando abaixo):
```shell
bash run.sh
```

### Notas:

* Para atualizar seu bot dê um clique duplo no update.sh (windows), p/ Linux use o comando no shell/terminal:
```shell
bash update.sh
```
`Ao atualizar, há chance de qualquer alteração manual feita ser perdida (caso não seja um fork desta source)...`<br/>

`Obs: Caso esteja rodando a source diretamente de uma máquina com windows (e que tenha git instalado) apenas dê um duplo-click no arquivo update.sh`

* Esta source foi criada com intuito para uso de bots privados (não está otimizado o suficiente pra lidar com alta demanda de servidores).</br></br>
* Recomendo usar a source atual sem alterações no code que vá alem de textos. Caso queira fazer modificações (e principalmente adicionar novas funcionalidades) é altamente recomendável que tenha conhecimento em python e disnake. E caso queira manter sua source modificada com updates em dias usando a source base também recomendo ter conhecimento em git (pelo menos o necessário pra fazer um merge sem erros).


### Algumas previews:

- Comandos de barra / Slash commands

![](https://media.discordapp.net/attachments/554468640942981147/944942596814426122/unknown.png)

- Player controller (modo normal/mini-player)

![](https://media.discordapp.net/attachments/554468640942981147/944942948406153276/unknown.png)

- Player controller (modo fixo/estendido com song requests, configurável com o comando: /setup)

![](https://media.discordapp.net/attachments/554468640942981147/944945573834936340/unknown.png)