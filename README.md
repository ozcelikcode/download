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

---

## Sık Kullanılan Komutlar

```bash
make dev                    # Geliştirme sunucusu
make migrate                # Bekleyen migrasyonları uygula
make migration msg="açıklama" # Yeni migrasyon oluştur
make hash pw=şifreniz       # Admin şifre hash'i üret
make freeze                 # requirements.txt güncelle
```
