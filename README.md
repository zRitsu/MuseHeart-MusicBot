# disnake-LL-music-bot
### bot de música programado em python com player interativo, comandos barra/slash, etc. Utilizando as libs disnake e wavelink/lavalink.
<br/>

Há alguns bots meus já feito e hospedado usando esta source, você pode adicionar um dos meus bots abaixo: 

| ![](https://cdn.discordapp.com/avatars/784891594306093101/b8a201bff9f563e4d1d54e7a470a1d53.png) | ![](https://cdn.discordapp.com/avatars/825460549419794462/8259b8ec375691b26e964187130a3edf.png) |
|---------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [Muse Heart](https://dsc.gg/muse-heart-music) | [Muse Heart (2)](https://dsc.gg/muse-heart-music-2)|

## Teste agora mesmo um bot próprio com esta source fazendo deploy em um dos serviços abaixo:
</br>

[![Run on Repl.it](https://replit.com/badge/github/zRitsu/disnake-LL-music-bot)](https://replit.com/new/github/zRitsu/disnake-LL-music-bot)

* 1 - Após clicar no botão acima, clique em "import from github" e aguarde carregar.
* 2 - Vá em secrets (cadeado do painel à esquerda) e crie uma secret com nome TOKEN e no value coloque o token do seu bot. `(caso queira alterar outras configs, consulte o arquivo .env-example)`
* 3 - Clique em run (botão de **play**) e aguarde o bot instalar as dependências e iniciar.

---
[![Heroku_Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/zRitsu/disnake-LL-music-bot/tree/main)

* 1 - Preencha os dados que vão ser requisitados na próxima página
* 2 - Clique em deploy app e aguarde (o processo pode demorar entre 2-5 minutos).
* 3 - Clique em Manage e depois vá em resources.
* 4 - Desative o dyno web e ative o autoupdate (ou o quickfix, não ative os 2 ao mesmo tempo!) e aguarde o bot logar. `(no canto superior clique em more e em view logs para acompanhar os logs)`
* **Nota:** Caso queira alterar as configs usadas no passo 1, vá em settings e clique em Reveal Config Vars, crie/altere a key e o valor desejado da config, consulte o arquivo .env-example para ver todas as configs disponíveis.

---
[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/zRitsu/disnake-LL-music-bot)

* 1 - Abra o arquivo .env e coloque o token do bot no campo apropriado. 
* 2 - Clique com botão direito em cima do arquivo main.py e depois clique em: Run Python File in Terminal.
* **Nota 1:** Não esqueça de ir na lista de [workspaces](https://gitpod.io/workspaces) e clicar nos 3 pontinhos do projeto e depois clicar em **pin**. `(isso evitará o worskpace ser deletado após 14 dias inativo)`
* **Nota 2:** Não use o gitpod para hospedar/manter o bot online, pois o mesmo não funciona pra isso!

---

Nota: há alguns guias um pouco mais completo [na wiki]((https://github.com/zRitsu/disnake-LL-music-bot/wiki)).

---

## Ou caso queira hospedar no seu próprio pc ou VPS veja os requisitos abaixo:
<br/>

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