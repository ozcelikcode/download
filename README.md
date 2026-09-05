# Download Sitesi

Minimal, "tıkla ve indir" mantığıyla çalışan FastAPI indirme sitesi.

---

## Hızlı Başlangıç

### 1. Kurulum

```bash
# Sanal ortam ve bağımlılıklar
make install

# Veritabanını oluştur
make migrate
```

### 2. `.env` Yapılandırması

`.env` dosyası zaten hazır. Üretime geçmeden önce şu değerleri değiştirin:

| Değişken | Açıklama |
|---|---|
| `APP_SECRET_KEY` | Session şifreleme anahtarı — `openssl rand -hex 32` ile yenileyin |
| `APP_BASE_URL` | Sitenizin tam adresi (örn. `https://download.example.com`) |
| `ADMIN_USERNAME` | Admin paneli kullanıcı adı |
| `ADMIN_PASSWORD_HASH` | bcrypt hash — aşağıdaki komutla üretin |

**Yeni admin şifresi üretmek:**
```bash
make hash pw=yenisifreniz
# Çıktıyı .env dosyasındaki ADMIN_PASSWORD_HASH değerine yapıştırın
```

### 3. Geliştirme Sunucusu

```bash
make dev
# → http://127.0.0.1:8000
```

### 4. Prodüksiyon Sunucusu

```bash
make prod   # 2 worker, 0.0.0.0:8000
```

### Veritabanı ve geçici dosyalar

Ana veritabanı `download.db` dosyasıdır. `download.db-wal` ve
`download.db-shm`, SQLite'ın WAL modunda kullandığı çalışma dosyalarıdır;
yedek değildir. Sunucu çalışırken elle silmeyin. Sunucu kapatıldıktan ve
veritabanını kullanan diğer uygulamalar kapandıktan sonra bekleyen yazıları
ana dosyaya aktarmak için:

```bash
.venv/bin/python -c 'import sqlite3; c=sqlite3.connect("download.db"); print(c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()); c.close()'
```

Çalışma dosyaları sunucu açıldığında yeniden oluşabilir ve Git tarafından
yok sayılır. `app/static/uploads` medya arşividir; bir sayfada kullanılmayan
dosyalar da arşivde saklanıyor olabilir.

Yüklemelerin sınırı `.env` içindeki `MAX_UPLOAD_SIZE_MB` ile belirlenir
(varsayılan 500 MB). Yeni yüklemeler benzersiz ad alır; medya arşivindeki
yerinde değiştirme işlemi mevcut bağlantıyı korur.

Ters proxy kullanıldığında yalnızca güvenilir proxy adreslerini Uvicorn'un
`FORWARDED_ALLOW_IPS` ayarıyla tanımlayın. İndirme kotası, sunucunun bu
kontrolden geçirdiği istemci adresini kullanır.

---

## Admin Paneli

| URL | Açıklama |
|---|---|
| `/admin/login` | Giriş sayfası |
| `/admin` | Dashboard — tüm indirmeler, istatistikler |
| `/admin/downloads/new` | Yeni dosya ekle (dış link veya dosya yükle) |
| `/admin/categories` | Kategori yönetimi |
| `/admin/tags` | Etiket yönetimi |

**Varsayılan kimlik bilgileri:**
- Kullanıcı adı: `admin`
- Şifre: `admin123`

> ⚠️ Üretime geçmeden önce mutlaka `.env`'deki `ADMIN_PASSWORD_HASH` değerini güncelleyin.

---

## Proje Yapısı

```
download/
├── app/
│   ├── main.py           # FastAPI uygulama fabrikası
│   ├── models.py         # SQLAlchemy ORM modelleri
│   ├── schemas.py        # Pydantic v2 şemalar
│   ├── crud.py           # Asenkron veritabanı işlemleri
│   ├── dependencies.py   # Auth, DB session, rate limiting
│   ├── templating.py     # Jinja2 instance + filtreler
│   ├── config.py         # .env ayar okuyucu
│   ├── routers/
│   │   ├── public.py     # Herkese açık rotalar
│   │   └── admin.py      # Admin rotalar
│   ├── templates/
│   │   ├── base.html     # Ana layout
│   │   ├── index.html    # Anasayfa + arama + kategori
│   │   ├── detail.html   # İndirme detay sayfası
│   │   ├── errors/       # 404, 500, 429
│   │   └── admin/        # Admin paneli template'ları
│   └── static/
│       ├── css/app.css   # Tailwind üstü özel stiller
│       └── uploads/      # Yüklenen dosyalar
├── alembic/              # DB migrasyon dosyaları
├── .env                  # Yapılandırma (commit'lemeyin)
├── .env.example          # Örnek yapılandırma
├── Makefile              # Kısayol komutlar
└── requirements.txt      # Python bağımlılıkları
```

---

## Özellikler

- **Dış link & lokal dosya** — Her iki tür indirme desteklenir
- **Kategori & etiket** — Çok-çoklu ilişki, sidebar'da anlık sayım
- **Sürüm geçmişi** — Dosyalar arasında parent-child ilişkisi
- **Rate limiting** — IP başına saatlik indirme limiti
- **Öne çıkanlar** — Featured dosyalar anasayfada ayrı bölümde
- **Güvenli admin** — Bcrypt şifre, session cookie (HttpOnly)
- **Sayfalama** — Tüm listelerde `?page=x` ile

### Medya koruması, raporlar ve güvenlik

- **Korumalı medya silme:** Medya arşivinde dosyanın kullanıldığı içerikler
  gösterilir. Pasif içerikler, ikonlar, küçük görseller ve açıklamaya eklenen
  bağlantılar da kontrol edilir. Kullanılan dosyanın silinmesi HTTP 409 ile
  engellenir; önce ilgili içerikteki bağlantıyı kaldırın.
- **Bağlantı Raporu — `/admin/links`:** Dış indirme adreslerini tek tek veya
  sayfa başına en fazla 20 kayıt olarak kontrol eder. Sonuçlar kalıcıdır;
  adres düzenlenirse eski sonuç gösterilmez. 404/410 kırık, 401/403/429 erişim
  sınırlı olarak ayrılır. Özel ağlara ve bu ağlara yönlendirmelere erişim
  engellenir. Dosya gövdesi indirilmez. Kontrol admin tarafından başlatılır.
- **Admin güvenliği:** Girişlerde IP başına 15 dakikalık pencerede 5 deneme
  sınırı uygulanır; başarılı denemenin rezervasyonu kaldırılır. Kota SQLite
  üzerinde olduğundan worker'lar arasında paylaşılır. Admin POST işlemleri,
  giriş ve çıkış dahil, oturuma bağlı CSRF jetonu ister. Formlar gizli alanla,
  AJAX istekleri `X-CSRF-Token` başlığıyla gönderir. Eski açık sekmelerde
  güvenlik doğrulaması hatası görülürse sayfayı yenileyin.
- **SHA-256:** Yükleme arşivindeki yerel dosyaların detay sayfasında otomatik
  hesaplanır ve gösterilir. Dosya değişirse önbellek yenilenir. Dış bağlantılı
  dosyalara tahmini bir özet atanmaz. Karşılaştırmak için macOS'ta
  `shasum -a 256 dosya.zip`, Windows PowerShell'de
  `Get-FileHash dosya.zip -Algorithm SHA256` kullanılabilir.
- **İşlem Geçmişi — `/admin/audit`:** İçerik, kategori, etiket, menü, ayar ve
  medya değişikliklerinde kullanıcı, zaman ve değişen alanlar tutulur.
  Silinen kayıtların geçmişi kalır. Parolalar maskelenir; geçmiş kayıtları
  arayüzden düzenlenemez/silinemez. Zamanlar UTC gösterilir. Özellik
  kurulmadan önceki işlemler için geçmiş üretilmez.

Mevcut kurulumda yeni tabloları oluşturmak için sunucuyu durdurup
`make migrate`, ardından `make dev` çalıştırın. Migration mevcut içerikleri
korur; bu özellikler yeni bir Python bağımlılığı gerektirmez.

---

## Sık Kullanılan Komutlar

```bash
make dev                    # Geliştirme sunucusu
make migrate                # Bekleyen migrasyonları uygula
make migration msg="açıklama" # Yeni migrasyon oluştur
make hash pw=şifreniz       # Admin şifre hash'i üret
make freeze                 # requirements.txt güncelle
make test                   # Test paketini çalıştır (tests/)
make css                    # Tailwind CSS'i yeniden derle (şablon class değişikliğinden sonra)
make css-watch              # Şablonları izleyip Tailwind CSS'i otomatik derle
```

> **Not:** Tailwind CSS, performans için `cdn.tailwindcss.com` yerine önceden derlenmiş statik bir dosyadan (`app/static/css/tailwind.css`) servis edilir. Şablonlarda yeni bir Tailwind class'ı kullandıysanız `make css` çalıştırmayı unutmayın — aksi halde yeni class sitede görünmez. `make install` bunu ilk kurulumda otomatik yapar.
