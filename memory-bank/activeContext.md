# Active Context

## Current work focus
İlk memory-bank oluşturuluyor (2026-07-09) — bu, proje kod tabanının statik analizinden türetildi, geliştiriciyle canlı bir oturumdan değil. Bu yüzden "current work" burada bilinen son commit durumu üzerinden çıkarım.

## Recent changes (git history'den)
- `5be56f7 update`, `cc15ea8 Update download.db` — genel güncellemeler.
- `24336b8 Create Finder_Icon_macOS_Tahoe.png` — `app/static/uploads/icons/` altına macOS ikon asset'i eklendi.
- Alembic'te iki migration var: `initial_schema` ve `add_os_icon_fields` → `Download.os_compatibility`, `icon_image_path`, `icon_image_url` alanları sonradan eklendi (models.py:147-151).

## Active decisions / open questions
- `.env` dosyası repoda mevcut ve gerçek değerler içerebilir — commit edilmemesi gerekiyor ama şu an git status'ta görünmüyor (muhtemelen zaten ignore'lu/tracked değil, kontrol edilmeli).
- Admin varsayılan şifresi (`admin123`) README'de belirtilmiş — prod'a geçmeden değiştirilmesi gerektiği not düşülmüş.
- `.idea/` klasörü git status'ta untracked görünüyor — JetBrains IDE config, muhtemelen .gitignore'a eklenmesi gerekir.

## Next steps
- Bir sonraki oturumda kullanıcının talebine göre bu bölüm güncellenecek.
- **update memory bank** komutu geldiğinde tüm dosyalar (özellikle bu dosya ve [progress.md](progress.md)) gözden geçirilmeli.
