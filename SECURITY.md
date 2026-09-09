# Güvenli çalıştırma

Parolalar rastgele salt içeren scrypt (N=131072, r=8, p=1) özetleri olarak saklanır. Eski bcrypt özeti başarılı girişte yükseltilir. Parola veya kullanıcı adı değiştiğinde mevcut yönetici oturumları reddedilir. APP_SECRET_KEY değişikliği tüm oturumları geçersiz kılar.

Üretimde APP_BASE_URL=https://alan-adiniz şeklinde ayarlanmalı; HTTPS sonlandıran reverse proxy kullanılmalıdır. Bu ayar Secure çerezleri ve HSTS başlığını etkinleştirir. Uvicorn proxy güveni yalnız gerçek proxy adreslerine verilmelidir; herkese güvenen forwarded-allow-ips kullanılmamalıdır.

.env ve SQLite dosyasını web kökünün dışında tutun ve yalnız servis hesabına erişim verin. .env sürüm kontrolüne eklenmemelidir. Daha önce paylaşılmış anahtarlar yenilenmelidir; git geçmişinden silmek tek başına yeterli değildir.

SQLite dosyası uygulama tarafından bütünüyle şifrelenmez. Disk ve yedeklerde şifreleme için işletim sistemi disk şifrelemesi ve şifreli yedekleme kullanılmalıdır. Parola özetleri ile veri şifrelemesi farklı korumalardır. Halka açık indirilebilir içerikler ziyaretçiler tarafından okunabilir.

Giriş kayıtları güvenilir istemci IP adresini içerir; parolalar kaydedilmez. Hatalı giriş ve hız sınırı olayları Kritik olarak işaretlenir. Kayıtlar mevcut 50/100/200/500/800 saklama sınırına tabidir. Bu kayıtlar değiştirilemez bir harici güvenlik arşivi değildir.

Sunucuyu make dev çalıştırılan terminalde Ctrl+C ile durdurun. Yeniden başlatmak için make dev kullanın. .env değişikliğinden sonra sunucuyu yeniden başlatın.
