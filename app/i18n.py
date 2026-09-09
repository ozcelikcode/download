"""Public arayüz metinleri için küçük, sunucu taraflı çeviri katmanı."""

from fastapi import Request

SUPPORTED_LANGUAGES = {"tr", "en"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "tr": {
        "meta_default": "Güvenli ve ücretsiz yazılımları indirin.", "admin_panel": "Admin Panel", "logout": "Çıkış Yap",
        "theme": "Tema seç", "light": "Aydınlık", "dark": "Karanlık", "system": "Sistem", "menu_open": "Menüyü aç",
        "language": "Dil seç", "search": "Ara", "search_placeholder": "İndirme ara...", "categories": "Kategoriler", "all": "Tümü", "tags": "Etiketler",
        "no_results": "Sonuç bulunamadı", "downloads": "indirme", "page": "Sayfa", "all_downloads": "Tüm İndirmeler",
        "featured": "Öne Çıkanlar", "download": "İndir", "results": "sonuç", "previous_page": "Önceki sayfa",
        "next_page": "Sonraki sayfa", "try_another_search": "Farklı bir arama terimi deneyin veya kategorilere göz atın.",
        "home_return": "Ana Sayfaya Dön", "home": "Anasayfa", "actions": "Aksiyonlar", "edit_content": "İçeriği Düzenle",
        "delete_content": "İçeriği Sil", "delete_title": "İçeriği sil", "delete_warning": "kalıcı olarak silinecek. Bu işlem geri alınamaz. Emin misiniz?",
        "cancel": "Vazgeç", "yes_delete": "Evet, Sil", "old_version": "uygulamasının eski bir sürümüdür.",
        "latest_version": "En güncel sürüme geç →", "downloaded_times": "kez indirildi", "open_link": "Bağlantıya Git",
        "download_now": "Şimdi İndir", "source": "Kaynak", "file_size": "Dosya boyutu", "official_site": "Resmî Site",
        "third_party": "Üçüncü Parti Site", "safe_download": "Güvenli indirme", "file_info": "Dosya Bilgileri",
        "version": "Sürüm", "type": "Tür", "external_link": "Dış Bağlantı", "local_file": "Lokal Dosya",
        "checksum_help": "İndirdiğiniz dosyanın özetini bu değerle karşılaştırarak bütünlüğünü doğrulayabilirsiniz.",
        "source_type": "Kaynak Türü", "added": "Eklendi", "updated": "Güncellendi", "version_history": "Sürüm Geçmişi",
        "versions": "sürüm", "current_version": "Güncel sürüm", "old_value": "Eski değer", "view": "Görüntüle",
        "no_versions": "Bu içerik için henüz bir sürüm geçmişi yok.", "delete_failed": "İçerik silinemedi. Lütfen tekrar deneyin.",
        "not_found": "Sayfa Bulunamadı", "not_found_text": "Aradığınız sayfa taşınmış, silinmiş ya da hiç var olmamış olabilir.",
        "search_anything": "Bir şey arayın…", "too_many": "Çok Fazla İstek", "limit_reached": "Saatlik indirme limitinize ulaştınız.",
        "limit_text": "Spam'i önlemek amacıyla her IP adresi için saatlik indirme sınırı uygulanmaktadır. Lütfen bir süre bekleyip tekrar deneyin.",
        "limit_reset": "Limit 1 saat içinde sıfırlanacaktır.", "server_error": "Sunucu Hatası",
        "server_error_text": "Beklenmedik bir hata oluştu. Sunucumuz bu hatayı kayıt altına aldı. Lütfen birkaç saniye bekleyip tekrar deneyin.",
        "refresh": "Yenile", "filter_clear": "Filtreyi temizle", "search_results": "için arama sonuçları",
        "search_meta": "için indirme sonuçları.", "search_page": "Arama", "search_meta_default": "İndirme arama.",
        "category_meta": "kategorisindeki indirmeler.", "tag_meta": "etiketli indirmeler.",
        "compatibility": "Uyumluluk", "not_specified": "Belirtilmedi", "latest_release": "Güncel sürüm",
    },
    "en": {
        "meta_default": "Download safe and free software.", "admin_panel": "Admin Panel", "logout": "Sign Out",
        "theme": "Choose theme", "light": "Light", "dark": "Dark", "system": "System", "menu_open": "Open menu",
        "language": "Choose language", "search": "Search", "search_placeholder": "Search downloads...", "categories": "Categories", "all": "All", "tags": "Tags",
        "no_results": "No results found", "downloads": "downloads", "page": "Page", "all_downloads": "All Downloads",
        "featured": "Featured", "download": "Download", "results": "results", "previous_page": "Previous page",
        "next_page": "Next page", "try_another_search": "Try another search term or browse the categories.",
        "home_return": "Return to Home", "home": "Home", "actions": "Actions", "edit_content": "Edit Content",
        "delete_content": "Delete Content", "delete_title": "Delete content", "delete_warning": "will be permanently deleted. This action cannot be undone. Are you sure?",
        "cancel": "Cancel", "yes_delete": "Yes, Delete", "old_version": "is an older version of this application.",
        "latest_version": "Go to latest version →", "downloaded_times": "downloads", "open_link": "Open Link",
        "download_now": "Download Now", "source": "Source", "file_size": "File size", "official_site": "Official Site",
        "third_party": "Third-party Site", "safe_download": "Safe download", "file_info": "File Information",
        "version": "Version", "type": "Type", "external_link": "External Link", "local_file": "Local File",
        "checksum_help": "Compare the downloaded file's checksum with this value to verify its integrity.",
        "source_type": "Source Type", "added": "Added", "updated": "Updated", "version_history": "Version History",
        "versions": "versions", "current_version": "Current version", "old_value": "Previous value", "view": "View",
        "no_versions": "This content does not have any version history yet.", "delete_failed": "Content could not be deleted. Please try again.",
        "not_found": "Page Not Found", "not_found_text": "The page may have been moved, deleted, or never existed.",
        "search_anything": "Search for something…", "too_many": "Too Many Requests", "limit_reached": "You have reached the hourly download limit.",
        "limit_text": "An hourly download limit is applied per IP address to prevent spam. Please wait and try again.",
        "limit_reset": "The limit will reset within 1 hour.", "server_error": "Server Error",
        "server_error_text": "An unexpected error occurred and was logged. Please wait a few seconds and try again.",
        "refresh": "Refresh", "filter_clear": "Clear filter", "search_results": "search results",
        "search_meta": "download results.", "search_page": "Search", "search_meta_default": "Search downloads.",
        "category_meta": "category downloads.", "tag_meta": "tagged downloads.",
        "compatibility": "Compatibility", "not_specified": "Not specified", "latest_release": "Latest version",
    },
}


def ui_language(request: Request) -> str:
    language = request.cookies.get("ui_language", "tr")
    return language if language in SUPPORTED_LANGUAGES else "tr"


def translate(request: Request, key: str) -> str:
    language = ui_language(request)
    return TRANSLATIONS.get(language, TRANSLATIONS["tr"]).get(key, TRANSLATIONS["tr"].get(key, key))
