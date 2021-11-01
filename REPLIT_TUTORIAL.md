# Hospedando na Repl.it

*OBS: Será necessário criar/logar uma conta na repl.it (não será abordado essa parte no tutorial).

- 1 = Clique no botão abaixo (segurando CTRL ou SHIFT para abrir em nova aba/janela) e aguarde:

[![Run on Repl.it](https://repl.it/badge/github/zRitsu/disnake-LL-music-bot.git)](https://repl.it/github/zRitsu/disnake-LL-music-bot.git)

- 2 = Clique no cadeado localizado na barra da esquerda para abrir a página das secrets.

![](https://cdn.discordapp.com/attachments/480195401543188483/903853110546542612/unknown.png)
<br/><br/>

- 3 = Caso apareça esse aviso da imagem, apenas clique em **Got it** (caso não, pule para o próximo passo).

![](https://cdn.discordapp.com/attachments/480195401543188483/903853798995394601/unknown.png)
<br/><br/>

- 4 = No campo Key digite o nome **TOKEN** e em value cole o Token do seu bot e em seguida clique em **Add new secret**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903855391178362941/unknown.png)
<br/><br/>

- 5 = Ainda na mesma tela (com os campos vazios) em key digite **DEFAULT_PREFIX** e em value coloque o prefixo para o seu bot (não precisa ser exatamente o da imagem abaixo) e depois clique em **Add new secret**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903856305792512040/unknown.png)
<br/><br/>


### Suporte ao spotify
os passos 6 e 7 para o spotify não são obrigatórios mas caso queira o suporte você terá que ter em mãos o client_id e client_secrect ([clique aqui](SPOTIFY_IDS.md) para ver o tutorial de como obté-los).

- 6 = Em key digite **SPOTIFY_CLIENT_ID** e em value cole o seu client id do spotify e em seguida clique em **Add new secret**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903858983620706354/unknown.png)
<br/><br/>

- 7 = Em key digite **SPOTIFY_CLIENT_SECRET** e em value cole o seu client secret do spotify e em seguida clique em **Add new secret**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903860032955891733/unknown.png)

### MongoDB para database
o passos 8 não é obrigatório mas caso seja ignorado, alguns comandos que depende de database não vão funcionar (setupguildplayer, add_dj_role, etc), para obter o link de sua database para o passo abaixo [clique aqui](MONGODB_SETUP.md) para ver o tutorial.


- 8 = Em key digite **MONGO** e em value cole o link da sua database do mongoDB e em seguida clique em **Add new secret**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903861623578591263/unknown.png)

#############################################################

- 9 = Com todas as secrets devidamente configuradas, clique em **Run** e aguarde o bot ligar normalmente (verifique no discord se ele fica online).

- 10 = Após o bot estar online e rodando normalmente, use o comando {seuprefix}syncguild para sincronizar os comandos slash (para comandos globais use {seuprefix}syncglobal mas este demora 1h para fazer efeito e caso tenha usado o syncguild os comandos vão aparecer duplicados).