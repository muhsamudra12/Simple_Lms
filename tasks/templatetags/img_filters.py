from django import template

register = template.Library()


@register.filter
def optimize_img(url, size="600x400"):
    """
    Optimasi URL gambar sebelum dikirim ke browser:
    1. Foto dari Unsplash di-resize & dikompres lewat parameter URL resmi
       mereka (?w=...&q=...&auto=format) — drastis mengurangi ukuran file
       dibanding resolusi asli (bisa beberapa MB) tanpa kualitas yang
       kelihatan beda jauh di ukuran kartu kursus.
    2. via.placeholder.com diganti ke placehold.co — domain yang sama
       dipakai untuk fallback onerror, karena placeholder.com sering
       lambat/down sehingga sempat memicu flicker gambar patah dulu
       sebelum fallback jalan.
    """
    if not url:
        return url

    width, _, height = size.partition("x")

    if "images.unsplash.com" in url and "?" not in url:
        return f"{url}?w={width}&h={height or width}&q=70&auto=format&fit=crop"

    if "via.placeholder.com" in url:
        return f"https://placehold.co/{size}/0a0f2c/ffffff?text=LMS"

    return url
