"""Account-photo copy for every supported interface language."""

COPY = {
    "photo_title": ("Profile photo", "Foto de perfil", "Photo de profil", "Profil fotoğrafı"),
    "photo_help": ("Maximum 5 MB. Images are cropped to 256 × 256, compressed, and stripped of metadata. Stored privately and included in your media quota.", "Máximo 5 MB. Las imágenes se recortan a 256 × 256, se comprimen y se eliminan sus metadatos. Se guardan de forma privada y cuentan para su cuota multimedia.", "Maximum 5 Mo. Les images sont recadrées à 256 × 256, compressées et leurs métadonnées supprimées. Elles sont privées et comptent dans votre quota média.", "En fazla 5 MB. Görseller 256 × 256 boyutuna kırpılır, sıkıştırılır ve meta verileri kaldırılır. Özel olarak saklanır ve medya kotanıza dahil edilir."),
    "photo_save": ("Save photo", "Guardar foto", "Enregistrer la photo", "Fotoğrafı kaydet"),
    "photo_remove": ("Remove photo", "Eliminar foto", "Supprimer la photo", "Fotoğrafı kaldır"),
    "photo_saved": ("Profile photo updated.", "Foto de perfil actualizada.", "Photo de profil mise à jour.", "Profil fotoğrafı güncellendi."),
    "photo_removed": ("Profile photo removed.", "Foto de perfil eliminada.", "Photo de profil supprimée.", "Profil fotoğrafı kaldırıldı."),
    "photo_invalid": ("Choose a valid PNG, JPEG, WebP, GIF, BMP or ICO image.", "Seleccione una imagen PNG, JPEG, WebP, GIF, BMP o ICO válida.", "Choisissez une image PNG, JPEG, WebP, GIF, BMP ou ICO valide.", "Geçerli bir PNG, JPEG, WebP, GIF, BMP veya ICO görseli seçin."),
}
STRINGS = {language: {key: values[index] for key, values in COPY.items()}
           for index, language in enumerate(("en", "es", "fr", "tr"))}
