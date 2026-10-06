"""Download-page disclosure and privacy-preserving visitor reports."""

_COPY = {
    "publisher_reports": ("Content feedback", "Comentarios sobre el contenido", "Retours sur le contenu", "İçerik bildirimleri"),
    "publisher_reports_help": ("Visitor feedback about your content. Reports follow the activity-log retention policy.", "Comentarios de visitantes sobre su contenido. Se conservan según la política del registro de actividad.", "Retours des visiteurs sur votre contenu. La durée de conservation suit celle du journal d’activité.", "İçerikleriniz hakkında ziyaretçi bildirimleri. Kayıtlar işlem geçmişinin saklama politikasına tabidir."),
    "detail_report_publisher": ("Notify publisher", "Avisar al autor", "Informer l’auteur", "Yayıncıya bildir"),
    "detail_details": ("Details", "Detalles", "Détails", "Detaylar"),
    "detail_sections": ("Content sections", "Secciones de contenido", "Sections du contenu", "İçerik bölümleri"),
    "detail_download_count": ("Downloads", "Descargas", "Téléchargements", "İndirme sayısı"),
    "report_reason": ("Issue", "Problema", "Problème", "Sorun"),
    "detail_show_more": ("Read more", "Leer más", "Lire la suite", "Devamını göster"),
    "detail_show_less": ("Show less", "Mostrar menos", "Réduire", "Daha az göster"),
    "detail_report": ("Report a problem", "Informar de un problema", "Signaler un problème", "Sorun bildir"),
    "detail_report_help": ("Choose the issue. No personal information is requested.", "Seleccione el problema. No se solicitan datos personales.", "Choisissez le problème. Aucune donnée personnelle n’est demandée.", "Sorun türünü seçin. Kişisel bilgi istenmez."),
    "detail_report_broken": ("Download link does not work", "El enlace de descarga no funciona", "Le lien de téléchargement ne fonctionne pas", "İndirme bağlantısı çalışmıyor"),
    "detail_report_incorrect": ("Content or version information is incorrect", "El contenido o la versión son incorrectos", "Le contenu ou la version sont incorrects", "İçerik veya sürüm bilgisi hatalı"),
    "detail_report_unsafe": ("Potentially unsafe content", "Contenido posiblemente inseguro", "Contenu potentiellement dangereux", "İçerik güvenli olmayabilir"),
    "detail_report_send": ("Send report", "Enviar informe", "Envoyer le signalement", "Bildirimi gönder"),
    "detail_report_received": ("Your report was received for review.", "Su informe se ha recibido para revisión.", "Votre signalement a été reçu pour examen.", "Bildiriminiz inceleme için alındı."),
    "detail_report_limit": ("Too many reports. Try again in 15 minutes.", "Demasiados informes. Inténtelo en 15 minutos.", "Trop de signalements. Réessayez dans 15 minutes.", "Çok fazla bildirim. 15 dakika sonra tekrar deneyin."),
    "detail_report_invalid": ("Choose a valid issue type.", "Seleccione un tipo de problema válido.", "Choisissez un type de problème valide.", "Geçerli bir sorun türü seçin."),
    "visitor_reports": ("Visitor reports", "Informes de visitantes", "Signalements des visiteurs", "Ziyaretçi bildirimleri"),
    "visitor_reports_help": ("Anonymous reports are not verified link checks. These records follow Activity Log retention.", "Los informes anónimos no son comprobaciones verificadas. Se aplica la retención del historial de actividad.", "Ces signalements anonymes ne sont pas des vérifications de liens. La conservation du journal d’activité s’applique.", "Anonim bildirimler doğrulanmış bağlantı kontrolleri değildir. Kayıtlar işlem geçmişinin saklama sınırına tabidir."),
    "visitor_reports_empty": ("No visitor reports.", "No hay informes de visitantes.", "Aucun signalement de visiteur.", "Ziyaretçi bildirimi yok."),
    "visitor_report_event": ("Visitor reported a content issue", "Un visitante informó de un problema", "Un visiteur a signalé un problème", "Ziyaretçi içerikle ilgili sorun bildirdi"),
}
STRINGS = {language: {key: values[index] for key, values in _COPY.items()}
           for index, language in enumerate(("en", "es", "fr", "tr"))}
