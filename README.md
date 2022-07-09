# disnake-LL-music-bot
### bot de música programado em python com player interativo, comandos barra/slash, etc. Utilizando as libs disnake e lavalink/YT-DLP.
<br/>

Há alguns bots meus já feito e hospedado usando esta source, você pode adicionar um dos meus bots abaixo: 

| ![](https://cdn.discordapp.com/avatars/784891594306093101/bb5355bb0fd46eaca1b89a983d8f4c15.png) | ![](https://cdn.discordapp.com/avatars/825460549419794462/8259b8ec375691b26e964187130a3edf.png) |
|---------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [Muse Heart](https://dsc.gg/muse-heart-music) | [Muse Heart (2)](https://dsc.gg/muse-heart-music-2)|

### Comece a usar agora mesmo fazendo deploy em um dos serviços abaixo:

| [![Run on Repl.it](https://repl.it/badge/github/zRitsu/disnake-LL-music-bot.git)](https://repl.it/github/zRitsu/disnake-LL-music-bot.git) | `Vá em secrets (cadeado do painel à esquerda) e crie uma secret com nome TOKEN e no value coloque o token do seu bot (caso queira alterar outras configs, consulte o arquivo .env-example)` |
|---------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [![Heroku_Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/zRitsu/disnake-LL-music-bot) | `Após clicar no botão, apenas preencha os dados que vão ser requisitados na próxima página. Nota: após o deploy, caso queira alterar outras configs vá em settings e clique em Reveal Config Vars, crie a key e o valor desejado da config, consulte o arquivo .env-example para ver as configs disponíveis.` |
| [![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/zRitsu/disnake-LL-music-bot)| `Após o deploy, abra o arquivo .env e coloque o token do bot no campo apropriado. Nota: Assim que finalizar o deploy não esqueça de clicar em pin no workspace para evitar o mesmo ser deletado após 14 dias inativo.` |

Nota: há alguns guias um pouco mais completo [na wiki]((https://github.com/zRitsu/disnake-LL-music-bot/wiki)).

### Ou caso queira hospedar no seu próprio pc ou VPS veja os requisitos abaixo:
<br/>

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

* Esta source foi criada com intuito para uso de bots privados (não está otimizado o suficiente pra lidar com alta demanda de servidores).

* Recomendo usar a source atual sem alterações no code que vá alem de textos. Caso queira fazer modificações (e principalmente adicionar novas funcionalidades) é altamente recomendável que tenha conhecimento em python e disnake. E caso queira manter sua source modificada com updates em dias usando a source base também recomendo ter conhecimento em git (pelo menos o necessário pra fazer um merge sem erros).

* Caso queira fazer algum vídeo/tutorial usando esta source, você está totalmente livre para usá-la pra essa finalidade desde que esteja de acordo com a [licença](/LICENSE) (e caso queira me ajudar, mantenha os créditos originais no code, aparece apenas no comando /about)



### Algumas previews:

- Comandos de barra / Slash commands

![](https://media.discordapp.net/attachments/554468640942981147/944942596814426122/unknown.png)

- Player controller: modo normal/mini-player (skin: default_progressbar)

![](https://media.discordapp.net/attachments/554468640942981147/944942948406153276/unknown.png)

- Player controller: modo fixo/estendido com canal e conversa de song requests (skin: default_progressbar), configurável com o comando: /setup

![](https://media.discordapp.net/attachments/554468640942981147/944945573834936340/unknown.png)

* Há outras skins, consulte usando o comando /change_skin (você também pode criar outras, use os modelos padrões que estão na pasta [skins](utils/music/skins/) como referência, crie uma cópia com outro nome e modifique a seu gosto).