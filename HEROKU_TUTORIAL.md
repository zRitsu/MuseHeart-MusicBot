# Hospedando na Heroku

*OBS: Será necessário criar/logar uma conta na heroku (não será abordado essa parte no tutorial). 

*Nota: No plano gratuito da heroku seu bot terá apenas 550 horas mensais com reboot a cada 24h, após passar esse tempo seu bot será desligado até as horas resetarem no mês seguinte (caso adicione um cartão de crédito na conta você vai ganhar 450 horas adicionais o que possibilita manter online o mês inteiro). 

<br/>

- 1 = Clique no botão abaixo (segurando CTRL ou SHIFT para abrir em nova aba/janela):

[![Heroku_Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/zRitsu/disnake-LL-music-bot) 

- 2 = preencha os dados que estão como **required** na imagem abaixo (default_prefix e token do bot).

Nota: para ter todas as funcionalidades do bot recomendo preencher tudo (clique nos links abaixo para ver o tutorial pra obter os devidos dados para inserir nos demais campos):<br />
| [MongoDB](MONGODB_SETUP.md) | [Spotify client_id e client_secret](SPOTIFY_IDS.md) |

Após preencher todos os campos necessários clique em **Deploy app** e aguarde o processo concluir.

![](https://cdn.discordapp.com/attachments/480195401543188483/906038947191345203/unknown.png)

- 3 = Após finalizar, clique em **Manage App** e em seguida clique na aba **Resources**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903823932417789982/Screenshot_3.png)

![](https://cdn.discordapp.com/attachments/480195401543188483/903823939158044743/Screenshot_4.png)

- 4 = Ative seu app ativando o botão da esquerda (veja como fazer no gif abaixo).

![](https://cdn.discordapp.com/attachments/480195401543188483/903825491277004820/Screenshot_5.gif)

- 5 = Clique no botão **More** que está localizado no canto superior direito e em seguida clica em **View logs**.

![](https://cdn.discordapp.com/attachments/480195401543188483/903832292772954122/unknown.png)

- 6 = Nos logs você pode verificar se o bot está online ou se ocorreu possíveis erros, agora é só verificar se seu bot está online no discord e testar os comandos.

- 7 = Após o bot estar online e rodando normalmente, use o comando `@seubot syncguild` para sincronizar os comandos slash (para comandos globais use {seuprefix}syncglobal mas este demora 1h para fazer efeito e caso tenha usado o syncguild os comandos vão aparecer duplicados).
<br/>
Nota: `@seubot` = menção do seu bot