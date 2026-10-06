"""Image policy and site-wide statistics interface copy."""

_COPY = {
    'compression_failed': ('Image processing failed. Try another image.', 'No se pudo procesar la imagen. Pruebe otra imagen.', 'Le traitement de l’image a échoué. Essayez une autre image.', 'Resim işlenemedi. Başka bir resim deneyin.'),
    'site_statistics': ('Statistics', 'Estadísticas', 'Statistiques', 'İstatistikler'),
    'compression_title': ('Image compression', 'Compresión de imágenes', 'Compression des images', 'Resim sıkıştırma'),
    'compression_help': ('Apply a default to new content images. Content uploads can override it. Profile photos are always optimized. Existing images are unchanged.', 'Aplique un valor predeterminado a las nuevas imágenes. Cada carga puede cambiarlo. Las fotos de perfil siempre se optimizan. Las imágenes existentes no cambian.', 'Appliquez un réglage aux nouvelles images. Chaque envoi peut le modifier. Les photos de profil sont toujours optimisées. Les images existantes restent inchangées.', 'Yeni içerik resimleri için varsayılanı belirleyin. Yükleme sırasında değiştirilebilir. Profil resimleri daima optimize edilir. Mevcut resimler değişmez.'),
    'compression_enabled': ('Compress content images by default', 'Comprimir imágenes de contenido por defecto', 'Compresser les images du contenu par défaut', 'İçerik resimlerini varsayılan olarak sıkıştır'),
    'compression_upload': ('Compress this image', 'Comprimir esta imagen', 'Compresser cette image', 'Bu resmi sıkıştır'),
    'compression_saved': ('Image compression settings saved.', 'Ajustes de compresión guardados.', 'Réglages de compression enregistrés.', 'Resim sıkıştırma ayarları kaydedildi.'),
    'compression_minimum': ('Minimum', 'Mínima', 'Minimale', 'En az'),
    'compression_low': ('Low', 'Baja', 'Faible', 'Az'),
    'compression_medium': ('Medium', 'Media', 'Moyenne', 'Orta'),
    'compression_high': ('High', 'Alta', 'Élevée', 'Yüksek'),
    'compression_ultra': ('Ultra', 'Ultra', 'Ultra', 'Ultra'),
    'statistics_help': ('Site-wide cumulative downloads and current published content. No visitor identities are collected.', 'Descargas acumuladas y contenido publicado del sitio. No se recopilan identidades de visitantes.', 'Téléchargements cumulés et contenu publié du site. Aucune identité de visiteur n’est collectée.', 'Site genelindeki toplam indirmeler ve mevcut yayınlanmış içerikler. Ziyaretçi kimlikleri toplanmaz.'),
    'statistics_top': ('Most downloaded content', 'Contenido más descargado', 'Contenu le plus téléchargé', 'En çok indirilen içerikler'),
    'statistics_categories': ('Published content by category', 'Contenido publicado por categoría', 'Contenu publié par catégorie', 'Kategoriye göre yayınlanmış içerikler'),
    'statistics_empty': ('No published content yet.', 'Aún no hay contenido publicado.', 'Aucun contenu publié pour le moment.', 'Henüz yayınlanmış içerik yok.'),
}
STRINGS = {language: {key: values[index] for key, values in _COPY.items()}
           for index, language in enumerate(('en', 'es', 'fr', 'tr'))}
