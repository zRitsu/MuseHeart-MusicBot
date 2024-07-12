# MuseHeart-MusicBot-TURKISH / b15162b
## Bu repo, Museheart botunun Ekibimiz [Mahirsn](https://github.com/mahirsn), [Tospeek](https://github.com/Tospeek) Ve [Sepultrex](https://github.com/Sepultrex) Tarafından Portekizce'den Türkçe'ye çevrilmiş versiyonudur. (DİKKAT! Botun mevcut sürümü ile birebir aynı olmayabilir ve çeviride tutarsızlıklar bulunabilir.)
## etkileşimli oynatıcı, slash komutları, [last.fm](https://www.last.fm/) ile entegrasyon ve çok daha fazlası ile python'ile programlanmış müzik botu.

## Davetler ve Muse Heart'tan bazı bilgileri/ekran görüntülerini ve bu kaynağın nasıl çalıştığını içeren sayfa: [buraya tıklayın](https://gist.github.com/zRitsu/4875008554a00c3c372b2df6dcdf437f#file-muse_heart_invites-md).

[![](https://discordapp.com/api/guilds/911370624507707483/embed.png?style=banner2)](https://discord.gg/KM3NS7D6Zj)

### Bazı Önizlemeler:

- Oynatıcı kontrolörü: Mod normal/mini-player (dış görünüm: varsayılan) 
- [RPC (Rich Presence)](https://github.com/zRitsu/MuseHeart-MusicBot-RPC-app)

[![](https://i.ibb.co/6tVbfFH/image.png)](https://i.ibb.co/6tVbfFH/image.png)

<details>
<summary>
Daha fazla önizleme:
</summary>
<br>

- Slash Komutları

[![](https://i.ibb.co/nmhYWrK/muse-heart-slashcommands.png)](https://i.ibb.co/nmhYWrK/muse-heart-slashcommands.png)

- [last.fm](https://www.last.fm/) ile entegre çalışmaktadır.

[![](https://i.ibb.co/SXm608z/muse-heart-lastfm.png)](https://i.ibb.co/SXm608z/muse-heart-lastfm.png)

- Oynatıcı kontrolörü: kanal ve şarkı isteği sohbeti ile sabit/genişletilmiş mod (dış görünüm: varsayılan), /setup komutuyla yapılandırılabilir

[![](https://i.ibb.co/5cZ7JGs/image.png)](https://i.ibb.co/5cZ7JGs/image.png)

- Oynatıcı kontrolörü: ses kanalı ve sahnede otomatik durum desteği ile forumda şarkı istek kanalı ile sabit / genişletilmiş mod

[![](https://i.ibb.co/9Hm5cyG/playercontrollerforum.png)](https://i.ibb.co/9Hm5cyG/playercontrollerforum.png)

* Başka birçok görünüm vardır, /change_skin komutunu kullanarak hepsini kontrol edin (yenilerini de oluşturabilirsiniz, [skins](utils/music/skins/) klasöründeki varsayılan şablonları referans olarak kullanın, başka bir ad altında bir kopya oluşturun ve istediğiniz gibi değiştirin).

</details>

## Bu kaynakla kendi botunuzu oluşturarak/yeniden kullanarak ve aşağıdaki hizmetlerden birine dağıtarak şimdi test edin:

---

<details>
<summary>
Repl.it
</summary>

Resimlerle birlikte kılavuza bağlantı: https://gist.github.com/zRitsu/70737984cbe163f890dae05a80a3ddbe
</details>

---

<details>
<summary>
Render.com
</summary>
<br>

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/zRitsu/MuseHeart-MusicBot/tree/main)

* **[ 1 ]** - **TOKEN_BOT_1** kısmına tokeni giriniz **( [Nasıl Bulunacağına Dair](https://www.youtube.com/watch?v=lfdmZQySTXE) )**. `Not: Dilerseniz, TOKEN alanına daha fazla bottan gelen tokenları dahil edebilir, böylece değere daha fazla token ekleyerek (boşluklarla ayırarak) çoklu ses desteğini etkinleştirmek için ekstra botlara sahip olabilirsiniz.`


* **[ 2 ]** - **DEFAULT_PREFIX** alanına bot için bir önek girin.


* **[ 3 ]** - **SPOTIFY_CLIENT_ID** ve **SPOTIFY_CLIENT_SECRET** alanlarına spotif anahtarlarınızı girin **( [Nasıl Bulunacağına Dair](https://www.youtube.com/watch?v=ceKQjWiCyWE) )**.


* **[ 4 ]** - MongoDB veritabanınızın bağlantısını **MONGO** alanına girin **( [Nasıl Bulunacağına Dair](https://www.youtube.com/watch?v=x1Gq5beRx9k) )**.


* **[ 5 ]** - Uygula'ya tıklayın ve bot başlayana kadar derleme işlemini bekleyin (bu uzun sürebilir, dağıtımın tamamlanması + botun başlaması + lavalink sunucusunun başlaması için en az 13 dakika veya daha fazla sürebilir).
</details>

---

<details>
<summary>
Gitpod
</summary>
<br>

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/zRitsu/MuseHeart-MusicBot)

* **[ 1 ]** - .env dosyasını açın ve bot token'ını uygun alana yerleştirin (eğer sahip değilseniz, bu öğretici ile nasıl elde edeceğinize bakın [tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE) nasıl bulunur). Ayrıca mongodb kullanmanızı şiddetle tavsiye ederim, .env dosyasında MONGO='yu arayın ve mongodb db'nizin bağlantısını girin (eğer sahip değilseniz, nasıl edineceğinizi buradan öğrenebilirsiniz). [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)).


* **[ 2 ]** - main.py dosyasına sağ tıklayın ve ardından tıklayın: Python Dosyasını Terminal'de Çalıştır.


* **Nota 1:** Cep telefonu/cep numarası ile hesap doğrulaması gerektirir.
* **Nota 2:** Kontrol etmeyi unutmayın [workspaces](https://gitpod.io/workspaces) ve projenin 3 noktasına tıklayın ve ardından **pin** öğesine tıklayın.. `(isso evitará o worskpace ser deletado após 14 dias inativo)`
* **Nota 3:** Botu çevrimiçi barındırmak/bakımını yapmak için gitpod kullanmayın, çünkü ücretsiz planda birçok sınırlaması vardır (daha fazla bilgi [Gitpod Linki](https://www.gitpod.io/pricing)).
</details>

---

<details>
<summary>
Kendi bilgisayarınızda/VPS'nizde barındırma (windows/linux)
</summary>
<br>

### Requisitos:

* Python 3.9, 3.10 ou 3.11<br/>
[Download pela Microsoft Store](https://apps.microsoft.com/store/detail/9PJPW5LDXLZ5?hl=pt-br&gl=BR) (Windows 10/11 kullanıcıları için önerilir).<br/>
[Download direto do site oficial](https://www.python.org/downloads/release/python-3117/) (Kurulum sırasında bu seçeneği işaretleyin: **Add python to the PATH**)
* [Git](https://git-scm.com/downloads) (Taşınabilir sürümü seçmeyin)</br>

* [JDK 17](https://www.azul.com/downloads) veya üstü (Windows'ta ve Linux'ta yüklenmesi gerekmez, otomatik olarak indirilir)</br>

`Not: Bu kaynağın normal çalışması için en az 512mb RAM VE 1Ghz CPU gerekir (Lavalink'i botla aynı örnekte çalıştırırsanız, botun özel olduğunu varsayarak).`

### Botu başlatın (hızlı kılavuz):

* Repoyu burdan indirin [zip](https://github.com/zRitsu/MuseHeart-MusicBot/archive/refs/heads/main.zip) ve ardından ayıklayın (Veya aşağıdaki komutu terminal/cmd'de kullanın ve ardından klasörü açın):
```shell
git clone https://github.com/zRitsu/MuseHeart-MusicBot.git
```
* source_setup.sh dosyasına çift tıklayın (veya pencereleriniz dosya uzantılarını görüntülemiyorsa sadece setup tıklayın) ve bekleyin.</br>
`Eğer linux kullanıyorsanız, terminaldeki komutu kullanın:` 
```shell
bash source_setup.sh
```
* **.env** adında bir dosya görünecektir, bu dosyayı düzenleyin ve bot belirtecini uygun alana yerleştirin (botta belirli ayarlamalar yapmak istiyorsanız aynı dosyadaki diğer şeyleri de düzenleyebilirsiniz).</br>
`Not: Eğer bir bot hesabı oluşturmadıysanız,` [veja este tutorial](https://www.youtube.com/watch?v=lfdmZQySTXE) `botunuzu oluşturmak ve gerekli jetonu almak için.`</br>` MONGO= .env dosyasını açın ve içine mongodb db'nizin bağlantısını koyun (eğer sahip değilseniz, nasıl edineceğiniz aşağıda açıklanmıştır` [tutorial](https://www.youtube.com/watch?v=x1Gq5beRx9k)`). ` 
* Şimdi, sisteminiz windows ise botu başlatmak için source_start_win.bat dosyasını açın, linux ise start.sh dosyasına çift tıklayın (veya botu aşağıdaki komutu kullanarak çalıştırmayı tercih ederseniz).:
```shell
bash source_start.sh
```

### Notas:

* Botunuzu güncellemek için update.sh (windows) dosyasına çift tıklayın, Linux için kabuk/terminaldeki komutu kullanın:
```shell
bash source_update.sh
```
`Güncelleme sırasında, yapılan tüm manuel değişikliklerin kaybolma ihtimali vardır (eğer bu kaynağın bir çatalı değilse)...`<br/>

`Not: Kaynağı doğrudan bir Windows makinesinden çalıştırıyorsanız (ve git yüklüyse) source_update.sh dosyasına çift tıklamanız yeterlidir.`
</details>

---

Not: Bu bölümde birkaç rehber daha var [wiki](https://github.com/zRitsu/MuseHeart-MusicBot/wiki).

### Önemli gözlemler:

* Bu kaynağı, özel kullanım için kendi müzik botunuzu barındırmak / çalıştırmak için ana botuma (Muse Heart) alternatif olarak veya yönettiğiniz genel sunucularda (sunucuya kendi botunuzu eklemek için izniniz varsa) kullanabilirsiniz. Bununla birlikte, botu bu kaynağı kullanarak herkese açık olarak dağıtmanızı önermiyorum çünkü yüksek sunucu talebiyle başa çıkacak kadar optimize edilmemiştir, ancak yine de bunu yapmaya karar verirseniz, botun orijinal kaynağın [lisans](/LICENSE) altında olması gerekecektir ve botun nerede tanıtıldığına bağlı olarak (örneğin bot listeleri) botunuzun bu kaynağı kullandığına dikkat çekilme olasılığı vardır.


* Kodda hiçbir değişiklik yapmadan mevcut kaynağı kullanmanızı öneririm. Eğer değişiklik yapmak (ve özellikle yeni özellikler eklemek) istiyorsanız, python, disnake, lavalink ve benzeri konularda bilgi sahibi olmanız şiddetle tavsiye edilir. Ve eğer değiştirdiğiniz kaynağı temel kaynağı kullanarak günlük olarak güncel tutmak istiyorsanız, git bilgisine sahip olmanızı da tavsiye ederim (en azından hatasız bir şekilde birleştirmek için ihtiyacınız olan şey).


* Mevcut kaynağı değiştirirseniz (özel görünümler hariç) destek sağlanmayacaktır, çünkü sık sık güncelliyorum ve değiştirilmiş sürümler güncelliğini kaybetme eğiliminde olduğundan, bu nedenle destek sağlamayı zorlaştırıyor (değişikliğe veya uygulamaya bağlı olarak, sorunu çözmeye çalışmayı zorlaştıran bilinmeyen hatalar oluşturabileceği ve genellikle bu değişiklikleri geri alan kodu güncellemek için yöntemler kullanmam gerektiği gerçeğine ek olarak).


* Bu kaynağı kullanarak bir video / öğretici yayınlamak istiyorsanız, yukarıdaki paragraflarda belirtilen şartları kabul ettiğiniz sürece bu amaçla kullanmakta tamamen özgürsünüz.

---

### Eğer bir probleminiz varsa, problemi detaylandıran bir [issue](https://github.com/zRitsu/MuseHeart-MusicBot/issues) gönderin.


## Özel teşekkürler ve krediler:

* [DisnakeDev](https://github.com/DisnakeDev) (disnake) ve Rapptz'e [discord.py](https://github.com/Rapptz/discord.py) original
* [Pythonista Guild](https://github.com/PythonistaGuild) (wavelink)
* [Lavalink-Devs](https://github.com/lavalink-devs) (lavalink e lavaplayer)
* [DarrenOfficial](https://lavalink-list.darrennathanael.com/) Lavalink sunucu listesi (lavalink sunucularını yayınlayan kullanıcılar, web sitesi / bağlantı ile birlikte hakkında komutunda listelenir).
* Ve hata bildirimlerinde bana çok yardımcı olan tüm üyelere ([issues](https://github.com/zRitsu/MuseHeart-MusicBot/issues) ve discord sunucusunda).
* Diğer görevler şu adreste bulunabilir [dependency graph](https://github.com/zRitsu/MuseHeart-MusicBot/network/dependencies)
