"""Vitrine Ofertas Explosivas: renderização estática do JSON já gerado pelo robô.

Não faz requisições nem publica nada. CSS e JS são incorporados no HTML para
funcionar como um único arquivo no GitHub Pages e no preview local.
"""
import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent

CATEGORIES = (
    "Cozinha", "Eletrônicos", "Casa", "Beleza", "Acessórios", "Outros",
)

KEYWORDS = {
    "Cozinha": ("cozinha", "air fryer", "processador", "facas", "panela", "cafeteira", "liquidificador", "frigideira", "churrasco", "espremedor"),
    "Eletrônicos": ("bluetooth", "fone", "caixa de som", "smartwatch", "relogio", "carregador", "power bank", "notebook", "teclado", "tablet"),
    "Casa": ("aspirador", "mop", "vassoura", "organizador", "luminaria", "lampada", "casa", "limpeza", "tapete", "cama"),
    "Beleza": ("beleza", "maquiagem", "cabelo", "secador", "escova", "barbeador", "perfume"),
    "Acessórios": ("suporte", "celular", "capinha", "bolsa", "mochila", "carteira", "oculos"),
}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def money(value):
    try:
        n = float(value)
        return "R$ " + f"{n:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    except (ValueError, TypeError, OverflowError):
        return "Preço indisponível"


def category_for(term, name=""):
    value = (str(term) + " " + str(name)).lower()
    import unicodedata
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    for category, keywords in KEYWORDS.items():
        if any(word in value for word in keywords):
            return category
    return "Outros"


def safe_shopee(url):
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() for c in url):
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    return url if (parsed.scheme == "https" and
                   (parsed.hostname or "").lower() in ("shope.ee", "s.shopee.com.br", "shopee.com.br", "www.shopee.com.br") and
                   parsed.path and not parsed.username and not parsed.password) else ""


def safe_image(url):
    try:
        p = urllib.parse.urlsplit(url or "")
        return url if p.scheme == "https" and p.hostname and not p.username and not p.password else ""
    except (ValueError, TypeError):
        return ""


def product_identity(product, link):
    """Identificador do item Shopee independente do link rastreável.

    Recupera shopId/itemId da URL longa, do origin_link de an_redir,
    ou utiliza o itemId salvo pelo robô na próxima oferta.
    """
    def ids_from_url(url):
        try:
            parsed = urllib.parse.urlsplit(url or "")
        except (ValueError, TypeError):
            return None
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            return None
        if hostname == "shope.ee" and parsed.path.rstrip("/") == "/an_redir":
            original = urllib.parse.parse_qs(parsed.query).get("origin_link", [""])[0]
            return ids_from_url(original)
        if hostname not in ("shopee.com.br", "www.shopee.com.br"):
            return None
        path = urllib.parse.unquote(parsed.path)
        match = re.search(r"/product/(\d+)/(\d+)(?:/|$)", path)
        if not match:
            match = re.search(r"-i\.(\d+)\.(\d+)(?:/|$)", path)
        return match.groups() if match else None

    details = ids_from_url(product.get("url")) or ids_from_url(link)
    if details:
        return "shopee-" + "-".join(details)
    item_id = str(product.get("id") or "").strip()
    if item_id.isdecimal():
        return "item-" + item_id
    name = re.sub(r"\s+", " ", str(product.get("nome") or "").strip().casefold())
    return "nome-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


def prepare_offers(offers, max_offers=40):
    records = []
    seen = set()
    for item in offers[:max_offers]:
        if not isinstance(item, dict):
            continue
        is_promo = item.get("tipo") == "promo"
        product = item.get("produto") if is_promo else item.get("barato")
        if not isinstance(product, dict):
            continue
        name = str(product.get("nome") or "").strip()
        link = safe_shopee(product.get("link"))
        if not name or not link:
            continue
        identity = product_identity(product, link)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            price = float(product.get("preco") or 0)
        except (TypeError, ValueError):
            continue
        if not (0 < price < 1000000):
            continue
        original = product.get("preco_cheio") if is_promo else None
        try:
            original = float(original) if original is not None else None
        except (ValueError, TypeError):
            original = None
        discount = round(max(0, min(99, (1 - price / original) * 100))) if original and original > price else 0
        image = safe_image(product.get("imagem"))
        term = str(item.get("palavra") or "")
        category = category_for(term, name)
        date = str(item.get("data") or "")
        try:
            date_label = dt.date.fromisoformat(date).strftime("%d/%m/%Y")
        except ValueError:
            date, date_label = "0000-00-00", "Data não informada"
        legacy_id = "oferta-" + hashlib.sha256((name + "|" + link).encode("utf-8")).hexdigest()[:12]
        stable_id = "oferta-" + identity
        reference = item.get("famoso") or {}
        records.append({
            "id": stable_id, "legacy_id": legacy_id,
            "name": name, "price": price, "original": original,
            "discount": discount, "image": image, "url": link,
            "category": category, "date": date, "date_label": date_label,
            "comparison": not is_promo,
            "reference_price": reference.get("preco") if isinstance(reference, dict) else None,
            "search": (name + " " + term + " " + category),
        })
    return records


def render_card(item):
    image = (f'<img src="{esc(item["image"])}" alt="{esc(item["name"])}" loading="lazy" decoding="async">'
             if item["image"] else '<span aria-hidden="true" style="font-size:3rem">📦</span>')
    badge = (f'<span class="discount">{item["discount"]}% OFF</span>'
             if item["discount"] else ('<span class="discount">COMPARE</span>' if item["comparison"] else ""))
    original = (f'<span>De <s>{money(item["original"])}</s></span>'
                if item["original"] and item["original"] > item["price"] else "")
    return f"""<article class="card" id="{esc(item['id'])}" data-legacy-id="{esc(item['legacy_id'])}" data-search="{esc(item['search'])}"
      data-category="{esc(item['category'])}" data-price="{item['price']:.2f}"
      data-discount="{item['discount']}" data-date="{esc(item['date'])}">
    <div class="media">{image}{badge}
      <button type="button" class="favorite" aria-label="Adicionar aos favoritos" aria-pressed="false" title="Favoritar">♡</button>
    </div>
    <div class="card-body">
      <span class="category-label">{esc(item['category'])}</span>
      <h3>{esc(item['name'])}</h3>
      <div class="price-old">{original}</div>
      <div class="price">{esc(money(item['price']))}</div>
      <p class="mini-note">Preço de {esc(item['date_label'])} · Confira na Shopee</p>
      <div class="card-actions">
        <a class="shop-link" href="{esc(item['url'])}" target="_blank" rel="sponsored noopener noreferrer" aria-label="Ver {esc(item['name'])} na Shopee">Ver na Shopee ↗</a>
        <button type="button" class="share-item" aria-label="Opções para compartilhar {esc(item['name'])}" aria-expanded="false" title="Compartilhar">↗</button>
      </div>
      <div class="share-menu" hidden aria-label="Compartilhar produto">
        <button type="button" class="share-whatsapp">WhatsApp</button>
        <button type="button" class="share-copy">Copiar link</button>
      </div>
    </div>
    </article>"""


def render_site(offers, *, title="Achadinhos Baratos", subtitle="Ofertas selecionadas da Shopee",
                telegram="", whatsapp="", max_offers=40):
    products = prepare_offers(offers, max_offers=max_offers)
    css = (HERE / "vitrine.css").read_text(encoding="utf-8")
    js = (HERE / "vitrine.js").read_text(encoding="utf-8")
    # A aplicação é totalmente estática: nenhuma variável do feed entra no JS.
    all_categories = [c for c in CATEGORIES if any(i["category"] == c for i in products)]
    chips = ('<button type="button" class="category-chip" data-category="Todas" aria-pressed="true">✨ Todas</button>' +
             "".join(f'<button type="button" class="category-chip" data-category="{esc(c)}" aria-pressed="false">{esc(c)}</button>' for c in all_categories))
    channel = str(telegram or "").strip().lstrip("@")
    social = []
    if whatsapp and safe_external(whatsapp):
        social.append(f'<a href="{esc(whatsapp)}" target="_blank" rel="noopener noreferrer">WhatsApp</a>')
    if channel and re.fullmatch(r"[A-Za-z0-9_]{5,32}", channel):
        social.append(f'<a href="https://t.me/{esc(channel)}" target="_blank" rel="noopener noreferrer">Telegram</a>')
    social_nav = "".join(social)
    count = len(products)
    cards = "\n".join(render_card(i) for i in products)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#f04d27">
<meta name="description" content="Ofertas da Shopee organizadas por categorias. Compare preços, filtre e compartilhe seus achadinhos.">
<title>{esc(title)} — Achados e Ofertas</title>
<style>{css}</style>
</head>
<body>
<div class="topline">🛍️ Descubra produtos com preços registrados e links diretos para a Shopee</div>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="#inicio" aria-label="Achadinhos Baratos - início"><span class="brand-mark" aria-hidden="true">⚡</span><span>Achadinhos <span>Baratos</span></span></a>
    <nav class="header-links" aria-label="Links rápidos">{social_nav}<button type="button" class="header-share" data-share-site>↗ Compartilhar</button></nav>
  </div>
</header>
<main class="wrap" id="inicio">
  <section class="hero" aria-label="Apresentação das ofertas">
    <div class="hero-main">
      <span class="eyebrow">🔥 Garimpo de ofertas</span>
      <h1>Achados incríveis.<br>Preços que surpreendem.</h1>
      <p>{esc(subtitle)} Compare, filtre e encontre seu próximo achadinho sem complicação.</p>
      <a class="hero-cta" href="#ofertas">Explorar ofertas ↓</a>
    </div>
    <aside class="hero-side">
      <div><span class="tag">✨ Feito para você</span><h2>Seus favoritos em um só lugar.</h2>
      <p>Guarde produtos e compartilhe achados com quem você gosta.</p></div>
      <a href="#ofertas">Veja os produtos disponíveis ↓</a>
    </aside>
  </section>
  <div class="stats" aria-label="Informações da vitrine">
    <span class="stat">🛍️ {count} produtos na vitrine</span>
    <span class="stat">🔎 Busca e filtros rápidos</span>
    <span class="stat">💬 Compartilhe pelo WhatsApp</span>
  </div>
  <section id="ofertas" aria-labelledby="ofertas-titulo">
    <div class="section-heading">
      <div><h2 id="ofertas-titulo">Garimpe seus achadinhos <span aria-hidden="true">✨</span></h2>
      <p>Encontre o que procura no seu ritmo, pelo celular ou computador.</p></div>
    </div>
    <div class="filters" aria-label="Filtros de produtos">
      <div class="filter-top">
        <div class="filter-field search"><label for="busca">Buscar produto</label><input id="busca" type="search" placeholder="Ex.: fone Bluetooth, cozinha..." autocomplete="off"></div>
        <div class="filter-field"><label for="preco-max">Preço máximo</label><select id="preco-max">
          <option value="">Qualquer preço</option><option value="25">Até R$ 25</option>
          <option value="50">Até R$ 50</option><option value="100">Até R$ 100</option>
          <option value="150">Até R$ 150</option><option value="300">Até R$ 300</option>
        </select></div>
        <div class="filter-field"><label for="desconto-min">Desconto mínimo</label><select id="desconto-min">
          <option value="0">Qualquer desconto</option><option value="20">20% ou mais</option>
          <option value="30">30% ou mais</option><option value="50">50% ou mais</option>
        </select></div>
        <div class="filter-field"><label for="ordenar">Ordenar por</label><select id="ordenar">
          <option value="recentes">Mais recentes</option><option value="barato">Menor preço</option>
          <option value="caro">Maior preço</option><option value="desconto">Maior desconto</option>
        </select></div>
      </div>
      <div class="categories" role="group" aria-label="Filtrar por categoria">{chips}
        <button type="button" id="favorites-filter" class="category-chip" aria-pressed="false">♡ Meus favoritos</button>
      </div>
    </div>
    <div class="results-row">
      <div><strong id="results-count" role="status" aria-live="polite">{count} ofertas encontradas</strong>
        <div id="active-filters" class="active-filters" aria-label="Filtros ativos" role="group"></div></div>
      <button type="button" class="clear" data-clear>Limpar filtros</button></div>
    <div id="cards" class="cards">{cards}</div>
    <div id="empty-state" class="empty" hidden><h3>Ops! Nenhum achadinho por aqui.</h3>
      <p>Tente remover algum filtro ou buscar outro produto.</p>
      <button type="button" id="all-favorites" hidden>Ver todos os favoritos</button>
      <button type="button" data-clear>Limpar filtros</button></div>
  </section>
</main>
<footer>
  <div class="wrap footer-inner">
    <div><h2>⚡ {esc(title)}</h2><p>Este site divulga links de afiliado e pode receber comissão por compras qualificadas, sem custo adicional para você.</p>
    <p>Os preços foram registrados nas datas indicadas e podem mudar sem aviso. Confirme o valor, frete e disponibilidade na Shopee antes de comprar.</p></div>
    <div><h2>Espalhe os achadinhos</h2><p>Gostou das ofertas? Compartilhe com amigos e familiares!</p>
    <button type="button" class="header-share" data-share-site>↗ Compartilhar página</button></div>
  </div>
</footer>
<div id="feedback" class="toast" role="status" aria-live="polite" hidden></div>
<script>{js}</script>
</body></html>"""


def safe_external(url):
    try:
        p = urllib.parse.urlsplit(str(url))
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def generate_preview(source="ofertas.json", destination="preview-site/index.html"):
    records = json.loads(Path(source).read_text(encoding="utf-8"))
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_site(records), encoding="utf-8")
    return target


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="ofertas.json")
    parser.add_argument("--output", default="preview-site/index.html")
    args = parser.parse_args()
    print(generate_preview(args.source, args.output))
