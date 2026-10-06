"""Panel message navigation and browser-icon settings."""

STRINGS = {
    "en": {"panel_messages": "Messages", "notice_empty": "No new updates.", "notice_update": "New panel updates are available.", "content_updates": "Content review updates", "favicon": "Site favicon", "favicon_help": "Upload an image or import it from a web address. It is safely stored on this site and converted to a square browser icon.", "favicon_saved": "Site favicon updated.", "favicon_invalid": "Choose an image file or a complete HTTP/HTTPS image address."},
    "es": {"panel_messages": "Mensajes", "notice_empty": "No hay novedades.", "notice_update": "Hay novedades en el panel.", "content_updates": "Novedades de revisión de contenido", "favicon": "Icono del sitio", "favicon_help": "Suba una imagen o impórtela desde una dirección web. Se guarda de forma segura en este sitio y se convierte en un icono cuadrado.", "favicon_saved": "Icono del sitio actualizado.", "favicon_invalid": "Seleccione una imagen o una dirección HTTP/HTTPS completa de imagen."},
    "fr": {"panel_messages": "Messages", "notice_empty": "Aucune nouvelle mise à jour.", "notice_update": "De nouvelles mises à jour sont disponibles dans le panneau.", "content_updates": "Mises à jour de validation du contenu", "favicon": "Icône du site", "favicon_help": "Téléversez une image ou importez-la depuis une adresse web. Elle est stockée sur ce site et convertie en icône carrée.", "favicon_saved": "Icône du site mise à jour.", "favicon_invalid": "Choisissez une image ou une adresse HTTP/HTTPS complète d’image."},
    "tr": {"panel_messages": "Mesajlar", "notice_empty": "Yeni bildirim yok.", "notice_update": "Panelde yeni bildirimler var.", "content_updates": "İçerik değerlendirme sonuçları", "favicon": "Site ikonu (favicon)", "favicon_help": "Bir görsel yükleyin veya web adresinden içe aktarın. Görsel güvenle bu sitede saklanır ve kare tarayıcı ikonuna dönüştürülür.", "favicon_saved": "Site ikonu güncellendi.", "favicon_invalid": "Bir görsel dosyası veya tam HTTP/HTTPS görsel adresi seçin."},
}

_NOTIFICATION_COPY = {
    "notice_unread": ("Unread notifications", "Notificaciones sin leer", "Notifications non lues", "Okunmamış bildirimler"),
    "notice_read": ("Seen", "Leído", "Vu", "Görüldü"),
    "notice_new": ("Unread", "Sin leer", "Non lu", "Okunmadı"),
    "notice_read_all": ("Mark all as read", "Marcar todo como leído", "Tout marquer comme lu", "Tümünü okundu işaretle"),
    "notice_read_all_done": ("All current notifications marked as read.", "Todas las notificaciones actuales se han marcado como leídas.", "Toutes les notifications actuelles sont marquées comme lues.", "Mevcut bildirimlerin tümü okundu olarak işaretlendi."),
    "notice_read_failed": ("Could not mark notifications as read. Please try again.", "No se pudieron marcar las notificaciones como leídas. Inténtelo de nuevo.", "Impossible de marquer les notifications comme lues. Réessayez.", "Bildirimler okundu olarak işaretlenemedi. Lütfen tekrar deneyin."),
    "notice_overview_title": ("Updates and pending work", "Novedades y tareas pendientes", "Actualités et tâches en attente", "Gelişmeler ve bekleyen işler"),
    "notice_overview_help": ("Reading an update does not complete the underlying task.", "Leer una notificación no completa la tarea pendiente.", "Lire une notification ne termine pas la tâche en attente.", "Bildirimi okumak, bekleyen işlemi tamamlamaz."),
}
for index, language in enumerate(("en", "es", "fr", "tr")):
    STRINGS[language].update({key: values[index] for key, values in _NOTIFICATION_COPY.items()})
