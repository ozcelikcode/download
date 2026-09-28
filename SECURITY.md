# Güvenli çalıştırma

Parolalar rastgele salt içeren scrypt (N=131072, r=8, p=1) özetleri olarak saklanır. Eski bcrypt özeti başarılı girişte yükseltilir. Parola veya kullanıcı adı değiştiğinde mevcut yönetici oturumları reddedilir. APP_SECRET_KEY değişikliği tüm oturumları geçersiz kılar.

İlk kurulum SETUP_TOKEN ile sunucu sahipliği doğrulaması gerektirir. Anahtar URL'ye, çereze veya işlem günlüğüne yazılmaz. Yeni anahtar `make setup-key` ile üretilir; sunucu yeniden başlatılmalıdır. Kurulum tamamlanmadan içerik, yönetim ve yükleme adresleri kapalıdır. Mevcut sitelerin migration'ı kurulum durumunu korur.

Bakım işlemleri mevcut parola, oturuma bağlı beş dakikalık onay ve site adının birebir girilmesini gerektirir. Tüm kapsamlar yönetici oturumlarını yenileme kuşağıyla geçersiz kılar; eski oturum public sayfalarda da yönetici sayılmaz. Kurulum, giriş, hesap parolası doğrulama ve sıfırlama için SQLite tabanlı deneme sınırı vardır. Hassas formlar 16 KiB ile sınırlandırılır; uzunluk başlığı olmayan akışlar da sayılır.

Tek uygulama süreci işletim sistemi kilidiyle zorunludur. Sıfırlama süren isteklerin ve arka plan işlerinin bitmesini bekler; kalıcı temizleme işareti, kesinti sonrasında siteyi kapalı tutar. Yeniden başlatma temizliği sürdürür. Silme yalnız doğrulanmış iki veri kökü içindeki dosyaları kapsar; geniş/kod/veritabanı yolları, çakışan kökler ve sembolik bağ kökleri reddedilir. Harici sembolik bağ hedefleri silinmez.

SQLite secure_delete etkinleştirilmiştir; buna rağmen SSD, WAL, işletim sistemi snapshot'ları ve harici yedekler için adli düzeyde yok etme garantisi verilmez. Tam sıfırlama .env sırlarını, hosting hesabını veya harici yedekleri kaldırmaz. Kuruluma dönme de sunucudaki uygulama kodunu kaldırmaz.

Üretimde APP_BASE_URL=https://alan-adiniz şeklinde ayarlanmalı; HTTPS sonlandıran reverse proxy kullanılmalıdır. Bu ayar Secure çerezleri ve HSTS başlığını etkinleştirir. Uvicorn proxy güveni yalnız gerçek proxy adreslerine verilmelidir; herkese güvenen forwarded-allow-ips kullanılmamalıdır.

.env ve SQLite dosyasını web kökünün dışında tutun ve yalnız servis hesabına erişim verin. .env sürüm kontrolüne eklenmemelidir. Daha önce paylaşılmış anahtarlar yenilenmelidir; git geçmişinden silmek tek başına yeterli değildir.

SQLite dosyası uygulama tarafından bütünüyle şifrelenmez. Disk ve yedeklerde şifreleme için işletim sistemi disk şifrelemesi ve şifreli yedekleme kullanılmalıdır. Parola özetleri ile veri şifrelemesi farklı korumalardır. Halka açık indirilebilir içerikler ziyaretçiler tarafından okunabilir.

Giriş kayıtları güvenilir istemci IP adresini içerir; parolalar kaydedilmez. Hatalı giriş ve hız sınırı olayları Kritik olarak işaretlenir. Kayıtlar mevcut 50/100/200/500/800 saklama sınırına tabidir. Bu kayıtlar değiştirilemez bir harici güvenlik arşivi değildir.

Sunucuyu make dev çalıştırılan terminalde Ctrl+C ile durdurun. Yeniden başlatmak için make dev kullanın. .env değişikliğinden sonra sunucuyu yeniden başlatın.
