#!/usr/bin/env python3
"""Coloca las fotos ilustrativas en las notas del blog.

Uso:
  1. Genera las imágenes con los prompts de blog/image-prompts.json.
  2. Guárdalas en img/blog/src/ con estos nombres:
       <slug>.jpg      portada de la nota
       <slug>-1.jpg    historia 1 de "Qué pasó"
       <slug>-2.jpg    historia 2 ...
     (también acepta .jpeg, .png y .webp)
  3. Corre:  python3 tools/blog_images.py

El script es idempotente; puedes correrlo cada vez que agregues imágenes.
Hace lo siguiente:
  - Recorta a 3:2 y guarda img/blog/<nombre>.webp (1600 px portada, 900 px historias).
  - Genera img/blog/<slug>-og.jpg (1200x630) para WhatsApp/redes.
  - Agrega "image" a cada post (y a sus historias) en blog/posts.json.
  - Copia posts.json al respaldo FALLBACK dentro de blog.html.
  - Inserta la portada y el og:image en la página estática blog-<slug>.html.
"""
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Falta Pillow: pip install Pillow")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "img" / "blog" / "src"
OUT = ROOT / "img" / "blog"
POSTS = ROOT / "blog" / "posts.json"
PROMPTS = ROOT / "blog" / "image-prompts.json"
BLOG = ROOT / "blog.html"
SITE = "https://deocko.github.io/bluedatagrid/"
CAPTION = "Imagen ilustrativa generada con IA"
EXTS = (".jpg", ".jpeg", ".png", ".webp")


def find_src(name):
    for ext in EXTS:
        f = SRC / (name + ext)
        if f.exists():
            return f
    return None


def crop(img, ratio):
    w, h = img.size
    if w / h > ratio:
        nw = int(h * ratio)
        x = (w - nw) // 2
        return img.crop((x, 0, x + nw, h))
    nh = int(w / ratio)
    y = (h - nh) // 2
    return img.crop((0, y, w, y + nh))


def make(src, name, width, og=False):
    img = Image.open(src).convert("RGB")
    c = crop(img, 3 / 2)
    if c.width > width:
        c = c.resize((width, round(width * 2 / 3)), Image.LANCZOS)
    dst = OUT / (name + ".webp")
    c.save(dst, "WEBP", quality=80, method=6)
    if og:
        o = crop(img, 1200 / 630).resize((1200, 630), Image.LANCZOS)
        o.save(OUT / (name + "-og.jpg"), "JPEG", quality=82, optimize=True, progressive=True)
    return "img/blog/" + dst.name, c.width, c.height


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def update_static(slug, image):
    page = ROOT / ("blog-" + slug + ".html")
    if not page.exists():
        print("  ! no existe", page.name)
        return
    s = page.read_text(encoding="utf-8")
    fig = ('<!--img--><figure class="ahf"><img src="{src}" alt="{alt}" width="{w}" height="{h}" '
           'decoding="async"><figcaption>{cap}</figcaption></figure><!--/img-->').format(
        src=image["src"], alt=esc(image["alt"]), w=image["w"], h=image["h"], cap=CAPTION)
    if "<!--img-->" in s:
        s = re.sub(r"<!--img-->.*?<!--/img-->", lambda m: fig, s, flags=re.S)
    else:
        s = s.replace('<article class="w">', '<article class="w">\n' + fig, 1)
    css = ('<style id="blog-img">.ahf{margin:clamp(24px,4vw,40px) 0 0}'
           '.ahf img{display:block;width:100%;height:auto;aspect-ratio:3/2;object-fit:cover;border-radius:18px;background:#DDE3EA}'
           '.ahf figcaption{margin-top:8px;font-size:12px;color:#5B6B7B;text-align:right}</style>')
    if 'id="blog-img"' not in s:
        s = s.replace("</head>", css + "\n</head>", 1)
    og = SITE + "img/blog/" + slug + "-og.jpg"
    s = re.sub(r'(<meta property="og:image" content=")[^"]*(")', lambda m: m.group(1) + og + m.group(2), s)
    s = re.sub(r'(<meta property="og:image:alt" content=")[^"]*(")',
               lambda m: m.group(1) + esc(image["alt"]) + m.group(2), s)
    if 'name="twitter:image"' not in s:
        s = s.replace('<meta name="twitter:card"', '<meta name="twitter:image" content="' + og + '">\n<meta name="twitter:card"', 1)
    page.write_text(s, encoding="utf-8")


def main():
    data = json.loads(POSTS.read_text(encoding="utf-8"))
    prompts = json.loads(PROMPTS.read_text(encoding="utf-8")).get("posts", {})
    OUT.mkdir(parents=True, exist_ok=True)
    changed = 0
    for p in data["posts"]:
        slug = p["slug"]
        meta = prompts.get(slug, {})
        src = find_src(slug)
        if src:
            path, w, h = make(src, slug, 1600, og=True)
            p["image"] = {"src": path, "alt": meta.get("alt") or p["title"], "w": w, "h": h}
            update_static(slug, p["image"])
            changed += 1
            print("✓ portada", slug)
        for i, st in enumerate(p.get("stories", []), 1):
            ssrc = find_src(slug + "-" + str(i))
            if ssrc:
                smeta = (meta.get("stories") or [{}] * i)
                alt = smeta[i - 1].get("alt") if len(smeta) >= i else None
                path, w, h = make(ssrc, slug + "-" + str(i), 900)
                st["image"] = {"src": path, "alt": alt or st["title"], "w": w, "h": h}
                changed += 1
                print("✓ historia", slug, i)
    if not changed:
        print("No encontré imágenes en", SRC.relative_to(ROOT))
        return
    POSTS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    b = BLOG.read_text(encoding="utf-8")
    new = "FALLBACK=" + json.dumps(data, ensure_ascii=False) + ";"
    b, n = re.subn(r'FALLBACK=\{"version".*?\};(?=\s*var MES=)', lambda m: new, b, count=1, flags=re.S)
    if n != 1:
        sys.exit("No encontré FALLBACK en blog.html")
    BLOG.write_text(b, encoding="utf-8")
    print("Listo:", changed, "imágenes. Revisa blog.html y haz commit.")


if __name__ == "__main__":
    main()
