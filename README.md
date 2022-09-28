# disnake-LL-music-bot
## bot de música programado em python com player interativo, comandos barra/slash, etc. Utilizando as libs disnake e wavelink/lavalink.

### Bots de exemplo usando esta source:
| ![](https://cdn.discordapp.com/avatars/784891594306093101/b8a201bff9f563e4d1d54e7a470a1d53.png?size=128) | ![](https://cdn.discordapp.com/avatars/825460549419794462/383711d4d254ed3e0988ebc5d1393a83.png?size=128) | ![](https://cdn.discordapp.com/avatars/611914625683816478/237f52ef59d848bed74bc890026d6cfc.png?size=128) | ![](https://cdn.discordapp.com/avatars/908029891583299604/a6a4dd5a1079cdcaf2b308357940aa68.png?size=128) | ![](https://cdn.discordapp.com/avatars/919730161786712164/f33f153b13ba7f602ca577f8f3cea889.png?size=128) |
|---|---|---|---|---|
| **Muse Heart 1**<br>[Adicionar](https://discord.com/oauth2/authorize?client_id=784891594306093101&scope=bot+applications.commands&permissions=397287680080) | **Muse Heart 2**<br>[Adicionar](https://discord.com/oauth2/authorize?client_id=825460549419794462&scope=bot+applications.commands&permissions=397287680080) | **Muse Heart 3**<br>[Adicionar](https://discord.com/oauth2/authorize?client_id=611914625683816478&scope=bot+applications.commands&permissions=397287680080) | **Muse Heart 4**<br>[Adicionar](https://discord.com/oauth2/authorize?client_id=908029891583299604&scope=bot+applications.commands&permissions=397287680080) | **Muse Heart 5**<br>[Adicionar](https://discord.com/oauth2/authorize?client_id=919730161786712164&scope=bot+applications.commands&permissions=397287680080) |

### Algumas previews:

- Comandos de barra / Slash commands

![](https://media.discordapp.net/attachments/554468640942981147/944942596814426122/unknown.png)

- Player controller: modo normal/mini-player (skin: default_progressbar)

![](https://media.discordapp.net/attachments/554468640942981147/944942948406153276/unknown.png)

- Player controller: modo fixo/estendido com canal e conversa de song requests (skin: default_progressbar), configurável com o comando: /setup

![](https://media.discordapp.net/attachments/554468640942981147/944945573834936340/unknown.png)

- Player controller: song-request em canal de forum (múltiplos bots) e skin embed_link.

![](https://media.discordapp.net/attachments/554468640942981147/1019806568134475786/forum_song_request.png)

* Há diversas outras skins, veja todas usando o comando /change_skin (você também pode criar outras, use os modelos padrões que estão na pasta [skins](utils/music/skins/) como referência, crie uma cópia com outro nome e modifique a seu gosto).

## Teste agora mesmo um bot próprio com esta source fazendo deploy em um dos serviços abaixo:

---

<details>
<summary>
Repl.it
</summary>
<br>

[![Run on Repl.it](https://replit.com/badge/github/zRitsu/disnake-LL-music-bot)](https://replit.com/new/github/zRitsu/disnake-LL-music-bot)

* 1 - Após clicar no botão acima, aguarde até o deploy ser concluído.
* 2 - Vá em secrets (cadeado do painel à esquerda) e crie uma secret com nome TOKEN_BOT_MAIN e no value coloque o token do bot + espaço + prefixo (que não seja / )
ficando assim: `token prefixo`<br>
ex:<br>
`MZ1yGvKTjE0rY0cV8i47CjAa.uRHQPq.Xb1Mk2nEhe-4iUcrGOuegj57zMC ==
` <br>
caso não tenha o token do bot, veja como obter com este [tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE).<BR>
Obs: Você pode adicionar mais bots pra rodar junto repetindo esse passo, mas apenas alterando o nome MAIN que está no TOKEN_BOT_**MAIN** (pode ser qualquer nome mas com apenas letras e números sem acentos)
e adicionar o token de outro bot no value.
* 3 - Também altamente recomendo usar mongodb para database ao invés de json, pra isso crie uma key com nome MONGO e no value coloque o link de sua url do mongodb (caso não tenha, veja como obter por este [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)). </br>
`se desejar, você pode alterar outras configs, consulte o arquivo .env-example`
* 4 - Clique em run (botão de **play**) e aguarde o bot instalar as dependências e iniciar.
</details>

---

<details>
<summary>
Render.com
</summary>
<br>

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/zRitsu/disnake-LL-music-bot/tree/main)

* 1 - No campo **TOKEN** coloque o token do bot **( [tutorial de como obter](https://www.youtube.com/watch?v=lfdmZQySTXE) )**.
* 2 - No campo **DEFAULT_PREFIX** coloque um prefixo para o bot.
* 3 - Nos campos **SPOTIFY_CLIENT_ID** e **SPOTIFY_CLIENT_SECRET** coloque as suas keys do spotify **( [tutorial de como obter](https://www.youtube.com/watch?v=ceKQjWiCyWE) )**.
* 4 - No campo **MONGO** coloque o link da sua database do MongoDB **( [tutorial de como obter](https://www.youtube.com/watch?v=x1Gq5beRx9k) )**.
* 5 - Clique em Apply e aguarde o processo de build até o bot iniciar (isso pode demorar bastante, no mínimo uns 13 minutos ou mais para o deploy ser finalizado + bot iniciar + servidor lavalink iniciar).
</details>

---

<details>
<summary>
Railway
</summary>
<br>

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template/WbAx7d?referralCode=JDUKpu)
* 1 - Preencha os dados que vão ser requisitados na próxima página (os que tem asteríscos vermelhos são obrigatórios).
* 2 - Clique no botão deploy e aguarde até o deploy ser concluído (Ficando com cor verde. Pode demorar alguns segundos antes de aparecer um deploy na lista).
* **Nota 1:** Requer uma conta do github com um bom tempo de criado ou um cartão de crédito para ter uma conta verificada.
* **Nota 2:** Caso queira alterar as configs usadas no passo 1, clique em variables e crie/altere a key e o valor desejado da config, consulte o arquivo .env-example para ver todas as configs disponíveis.
</details>

---

<details>
<summary>
Gitpod
</summary>
<br>

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/zRitsu/disnake-LL-music-bot)

* 1 - Abra o arquivo .env e coloque o token do bot no campo apropriado (caso não tenha, veja como obter com este tutorial [tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE) de como obter). Também altamente recomendo usar mongodb, procure onde tem MONGO= no arquivo .env e nele coloque o link da sua db do mongodb (caso não tenha, veja como obter por este [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)). 
* 2 - Clique com botão direito em cima do arquivo main.py e depois clique em: Run Python File in Terminal.
* **Nota 1:** Requer verificação da conta por número de celular/mobile.
* **Nota 2:** Não esqueça de ir na lista de [workspaces](https://gitpod.io/workspaces) e clicar nos 3 pontinhos do projeto e depois clicar em **pin**. `(isso evitará o worskpace ser deletado após 14 dias inativo)`
* **Nota 3:** Não use o gitpod para hospedar / manter o bot online, pois a mesma tem bastante limitações no plano gratuito (mais informações [nesse link](https://www.gitpod.io/pricing)).
</details>

---

<details>
<summary>
Heroku
</summary>
<br>

[![Heroku_Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/zRitsu/disnake-LL-music-bot/tree/main)

**Nota: A partir do dia 28/11/2022 a heroku não vai mais fornecer planos gratuitos ([clique aqui](https://blog.heroku.com/next-chapter) para saber mais).** 
* 1 - Preencha os dados que vão ser requisitados na próxima página
* 2 - Clique em deploy app e aguarde (o processo pode demorar entre 2-5 minutos).
* 3 - Clique em Manage e depois vá em resources.
* 4 - Desative o dyno web e ative o autoupdate (ou o quickfix, não ative os 2 ao mesmo tempo!) e aguarde o bot logar. `(no canto superior clique em more e em view logs para acompanhar os logs)`
* **Nota:** Caso queira alterar as configs usadas no passo 1, vá em settings e clique em Reveal Config Vars, crie/altere a key e o valor desejado da config, consulte o arquivo .env-example para ver todas as configs disponíveis.
</details>

---

<details>
<summary>
Hospedando no seu próprio PC/VPS (windows/linux)
</summary>
<br>

### Requisitos:

* Python 3.8 ou superior:<br/>
[Download pela Microsoft Store](https://apps.microsoft.com/store/detail/9PJPW5LDXLZ5?hl=pt-br&gl=BR) (Recomendável para usuários do windows 10/11).<br/>
[Download direto do site oficial](https://www.python.org/downloads/) (Marque esta opção ao instalar: **Add python to the PATH**)
* [Git](https://git-scm.com/downloads) (Não escolha a versão portable)</br>

* [JDK 11](https://www.azul.com/downloads) ou superior (Windows e Linux x64 é baixado automaticamente)</br>

`Nota: esta source requer no mínimo 512mb de RAM E 1Ghz de CPU para rodar normalmente (caso rode o Lavalink na mesma instância do bot considerando que o bot seja privado).`

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
`Nota: Caso não tenha criado uma conta de bot,` [veja este tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE) `para criar seu bot e obter o token necessário.`</br>`Também altamente recomendo usar mongodb, procure onde tem MONGO= no arquivo .env e nele coloque o link da sua db do mongodb (caso não tenha, veja como obter por este` [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)`). ` 
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
</details>

---

Nota: há mais alguns guias na [wiki]((https://github.com/zRitsu/disnake-LL-music-bot/wiki)).

### Observaçoes importantes:

* Esta source foi criada com intuito para uso de bots privados (não está otimizado o suficiente pra lidar com alta demanda de servidores).

* Recomendo usar a source atual sem alterações no code que vá alem de textos. Caso queira fazer modificações (e principalmente adicionar novas funcionalidades) é altamente recomendável que tenha conhecimento em python e disnake. E caso queira manter sua source modificada com updates em dias usando a source base também recomendo ter conhecimento em git (pelo menos o necessário pra fazer um merge sem erros).

* Caso queira fazer algum vídeo/tutorial usando esta source, você está totalmente livre para usá-la pra essa finalidade desde que esteja de acordo com a [licença](/LICENSE) (e caso queira me ajudar, mantenha os créditos originais no code, aparece apenas no comando /about)

### Caso tenha mais alguma dúvida, entre no servidor de suporte: https://discord.gg/R7BPG8fZTr