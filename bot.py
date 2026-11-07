# -*- coding: utf-8 -*-
"""
Robô de achadinhos Shopee
-------------------------
Todo dia ele:
  1. baixa o feed de produtos do seu painel de afiliado Shopee
     (ou usa a Open API, se um dia ela for liberada);
  2. pega os mais populares de algumas palavras-chave e acha uma opção
     parecida e bem mais barata;
  3. usa os seus links de afiliado que já vêm no feed;
  4. monta um vídeo vertical (9:16) com narração;
  5. manda o vídeo + legenda pronta pro seu Telegram
     (e, se você tiver, posta a oferta no seu canal).

Você só precisa mexer na parte "CONFIGURAÇÃO" logo abaixo.
"""

import csv
import datetime as dt
import hashlib
import html
import io
import json
import urllib.parse
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# ============================================================
# CONFIGURAÇÃO  (pode editar à vontade pelo GitHub)
# ============================================================

# Produtos que o robô vai pesquisar. Ele usa alguns por dia, em rodízio.
# Dica: escolha um nicho (casa, cozinha, tecnologia...) e coloque 10 a 30 termos.
PALAVRAS = [
    "fone bluetooth",
    "air fryer",
    "aspirador portátil",
    "garrafa térmica",
    "organizador de cozinha",
    "smartwatch",
    "caixa de som bluetooth",
    "mop giratório",
    "luminária led",
    "mini processador",
    "suporte celular",
    "kit facas cozinha",
]

VIDEOS_POR_DIA = 3        # quantos vídeos por dia
NOTA_MINIMA = 4.5         # nota mínima dos produtos (0 a 5)
VENDAS_MINIMAS = 100      # vendas mínimas da opção barata (só no modo Open API)
CURTIDAS_MINIMAS = 30     # curtidas mínimas da opção barata (modo feed)
ECONOMIA_MINIMA = 0.30    # a opção barata precisa ser pelo menos 30% mais barata
ECONOMIA_MAXIMA = 0.85    # mais de 85% mais barata costuma ser outra coisa (ou preço isca)
SO_ENVIO_NACIONAL = True  # só produtos enviados do Brasil (entrega mais rápida)
DIAS_SEM_REPETIR = 30     # não repete o mesmo produto por esse tempo

# Texto do final do vídeo (onde está o link pra pessoa)
CHAMADA_FINAL = "Link no perfil"

# Página automática com as ofertas (vai no link da bio)
NOME_PAGINA = "Achadinhos Baratos"
OFERTAS_NA_PAGINA = 40    # quantas ofertas recentes a página mostra
PALAVRA_DM = "QUERO"      # palavra do "comenta que eu mando no direct" (Instagram)
# Link do seu canal do WhatsApp (WhatsApp → Atualizações → seu canal → Compartilhar link).
# Deixe vazio ("") pra esconder o botão "Receber no WhatsApp" da página.
CANAL_WHATSAPP = "https://whatsapp.com/channel/0029VbEeN7aElagzyls0tb0N"
VOZ = "pt-BR-AntonioNeural"   # ou "pt-BR-FranciscaNeural" (voz feminina)

# ============================================================
# (daqui pra baixo não precisa mexer)
# ============================================================

API_URL = "https://open-api.affiliate.shopee.com.br/graphql"
PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / "saida"
HISTORICO = PASTA / "historico.json"
OFERTAS = PASTA / "ofertas.json"
SITE = PASTA / "site"
W, H = 1080, 1920

APP_ID = os.environ.get("SHOPEE_APP_ID", "").strip()
SECRET = os.environ.get("SHOPEE_SECRET", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TG_CANAL = os.environ.get("TELEGRAM_CANAL", "").strip()
FEED_URLS = os.environ.get("SHOPEE_FEED_URL", "").split()
_repo = os.environ.get("GITHUB_REPOSITORY", "")          # "usuario/repositorio" quando roda no GitHub
PAGINA_URL = (f"https://{_repo.split('/')[0]}.github.io/{_repo.split('/')[1]}/" if "/" in _repo else "")   # pode ter mais de um, separados por espaço

METRICA = "vendidos"      # no modo feed vira "curtidas" (o feed não informa vendas)

MODO_TESTE = "--teste" in sys.argv


# ------------------------------------------------------------
# Shopee (API oficial de afiliados)
# ------------------------------------------------------------
def shopee(query):
    corpo = json.dumps({"query": query}, ensure_ascii=False, separators=(",", ":"))
    ts = str(int(time.time()))
    assinatura = hashlib.sha256((APP_ID + ts + corpo + SECRET).encode("utf-8")).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={APP_ID}, Timestamp={ts}, Signature={assinatura}",
    }
    for tentativa in range(3):
        r = requests.post(API_URL, data=corpo.encode("utf-8"), headers=headers, timeout=30)
        dados = r.json()
        erros = dados.get("errors")
        if erros:
            msg = erros[0].get("message", str(erros))
            codigo = (erros[0].get("extensions") or {}).get("code")
            if codigo == 10030 and tentativa < 2:   # limite de requisições: espera e tenta de novo
                time.sleep(5 * (tentativa + 1))
                continue
            raise RuntimeError(f"Shopee respondeu erro {codigo}: {msg}")
        return dados["data"]
    raise RuntimeError("Shopee: limite de requisições atingido")


CAMPOS = ("itemId productName productLink offerLink imageUrl priceMin priceMax "
          "sales ratingStar commissionRate commission shopName")


def buscar(palavra, ordem, limite=50):
    # ordem: 1 = relevância, 2 = mais vendidos, 4 = menor preço
    q = (f'{{productOfferV2(keyword:{json.dumps(palavra, ensure_ascii=False)},'
         f'sortType:{ordem},page:1,limit:{limite})'
         f'{{nodes{{{CAMPOS}}}}}}}')
    nodes = shopee(q)["productOfferV2"]["nodes"] or []
    return [normalizar(n) for n in nodes]


def link_curto(url_produto, sub):
    q = (f'mutation{{generateShortLink(input:{{originUrl:{json.dumps(url_produto)},'
         f'subIds:{json.dumps(sub)}}}){{shortLink}}}}')
    return shopee(q)["generateShortLink"]["shortLink"]


def normalizar(n):
    def num(v, padrao=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return padrao
    return {
        "id": str(n.get("itemId")),
        "nome": (n.get("productName") or "").strip(),
        "url": n.get("productLink") or "",
        "oferta": n.get("offerLink") or n.get("productLink") or "",
        "imagem": n.get("imageUrl") or "",
        "preco": num(n.get("priceMin")),
        "vendas": int(num(n.get("sales"))),
        "nota": num(n.get("ratingStar")),
        "taxa": num(n.get("commissionRate")),
        "comissao": num(n.get("commission")),
        "loja": n.get("shopName") or "",
    }


# ------------------------------------------------------------
# Feed de produtos (painel de afiliado → Criativo → Feed de produto)
# ------------------------------------------------------------
def do_feed(linha):
    def num(v):
        try:
            return float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            return 0.0
    cb = (linha.get("cb_option") or "").lower()
    return {
        "id": str(linha.get("itemid") or ""),
        "nome": (linha.get("title") or "").strip(),
        "url": linha.get("product_link") or "",
        "oferta": linha.get("product_short link") or linha.get("product_link") or "",
        "imagem": linha.get("image_link") or "",
        "preco": num(linha.get("sale_price")) or num(linha.get("price")),
        "vendas": int(num(linha.get("like"))),          # no feed: curtidas
        "nota": num(linha.get("item_rating")),
        "taxa": 0.0, "comissao": 0.0,
        "loja": linha.get("shop_name") or "",
        "cat": linha.get("global_catid3") or linha.get("global_catid2") or "",
        "nacional": not ("cross" in cb and "non" not in cb),
        "novo": (linha.get("condition") or "new").strip().lower().startswith("new"),
    }


def combina(chave, titulo_norm, tokens_titulo):
    # todas as palavras da busca aparecem no título (aceita plural: "organizador" -> "organizadores")
    return all(k in titulo_norm for k in chave) and all(
        any(t.startswith(k) for t in tokens_titulo) for k in chave)


def ler_feed(palavras):
    """Lê o feed inteiro uma vez (sem guardar em disco) e separa os produtos de cada palavra."""
    csv.field_size_limit(2**31 - 1)
    chaves = {p: palavras_de(p) for p in palavras}
    achados = {p: [] for p in palavras}
    total = 0
    for url in FEED_URLS:
        with requests.get(url, stream=True, timeout=180,
                          headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            r.raw.decode_content = True
            r.raw.auto_close = False   # senão o arquivo "fecha" antes do leitor terminar
            texto = io.TextIOWrapper(r.raw, encoding="utf-8-sig", errors="replace", newline="")
            for linha in csv.DictReader(texto):
                total += 1
                titulo = sem_acento((linha.get("title") or "").lower())
                tokens = None
                for p, chave in chaves.items():
                    if not chave or not all(k in titulo for k in chave):
                        continue
                    if tokens is None:
                        tokens = re.findall(r"[a-z0-9]+", titulo)
                    if combina(chave, titulo, tokens):
                        achados[p].append(do_feed(linha))
    print(f"Feed: {total} produtos lidos; " +
          ", ".join(f"{p}: {len(v)}" for p, v in achados.items()))
    if total == 0:
        raise RuntimeError("o feed veio vazio")
    return achados


def comeca_com(palavra, nome):
    """O título começa pelo produto buscado? ("Fone Bluetooth..." sim, "Capa para Fone..." não)"""
    chave = [k for k in re.findall(r"[a-z0-9]+", sem_acento(palavra.lower())) if k not in PARADAS]
    titulo = [t for t in re.findall(r"[a-z0-9]+", sem_acento(nome.lower())) if t not in PARADAS]
    return bool(chave and titulo and titulo[0].startswith(chave[0]))


def filtrar_feed(lista, palavra):
    lista = [p for p in lista if p["novo"] and (p["nacional"] or not SO_ENVIO_NACIONAL)]
    if not lista:
        return []
    # fica só com a categoria do produto em si (evita misturar fone com capinha de fone):
    # vence a categoria com mais títulos que começam pelo nome buscado
    pontos = {}
    for p in lista:
        pontos[p["cat"]] = pontos.get(p["cat"], 0) + (1000 if comeca_com(palavra, p["nome"]) else 1)
    principal = max(pontos, key=pontos.get)
    return [p for p in lista if p["cat"] == principal]


# ------------------------------------------------------------
# Escolha do par "famoso x opção barata"
# ------------------------------------------------------------
PARADAS = set("de da do das dos e com para pra p sem em a o as os kit novo nova original "
              "promocao oferta frete gratis envio imediato 1 2 3 un unidade".split())


def sem_acento(texto):
    t = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in t if not unicodedata.combining(c))


def palavras_de(texto):
    t = sem_acento(texto.lower())
    return {p for p in re.findall(r"[a-z0-9]+", t) if p not in PARADAS and len(p) > 1}


def parecido(a, b, palavra_chave):
    pa, pb = palavras_de(a["nome"]), palavras_de(b["nome"])
    chave = palavras_de(palavra_chave)
    if chave and chave <= pb:
        return True
    return len(pa & pb) >= 2


def escolher_par(produtos, palavra, usados):
    bons = [p for p in produtos if p["preco"] > 0 and p["nota"] >= NOTA_MINIMA and p["imagem"]]
    if len(bons) < 2:
        return None
    famosos = sorted(bons, key=lambda p: p["vendas"], reverse=True)[:8]
    for famoso in famosos:
        if famoso["id"] in usados:
            continue
        teto = famoso["preco"] * (1 - ECONOMIA_MINIMA)
        piso = famoso["preco"] * (1 - ECONOMIA_MAXIMA)
        minimo = CURTIDAS_MINIMAS if METRICA == "curtidas" else VENDAS_MINIMAS
        candidatas = [
            p for p in bons
            if p["id"] != famoso["id"] and p["id"] not in usados
            and piso <= p["preco"] <= teto and p["vendas"] >= minimo
            and p.get("cat", "") == famoso.get("cat", "")
            and parecido(famoso, p, palavra)
        ]
        if candidatas:
            # a mais vendida entre as baratas, desempatando pela nota
            barato = max(candidatas, key=lambda p: (p["vendas"], p["nota"]))
            return famoso, barato
    return None


# ------------------------------------------------------------
# Textos
# ------------------------------------------------------------
def reais(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$\u00a0{s}"   # espaço que não quebra linha


def reais_falado(v):
    inteiro = int(v)
    cent = int(round((v - inteiro) * 100))
    if cent == 100:
        inteiro, cent = inteiro + 1, 0
    if not cent:
        return f"{inteiro} reais"
    return f"{inteiro} reais e {cent}" + (" centavos" if cent < 10 else "")


def vendas_texto(n):
    if n >= 1000:
        return f"mais de {n // 1000} mil"
    if n >= 100:
        return f"mais de {n // 100 * 100}"
    return str(n)


def roteiro(famoso, barato, palavra, rnd):
    p1, p2 = famoso["preco"], barato["preco"]
    dif = p1 - p2
    nota = f"{barato['nota']:.1f}".replace(".", ",")
    if METRICA == "curtidas":
        ganchos = [
            (f"Todo mundo de olho em {palavra} de {reais_falado(p1)}.",
             f"Todo mundo de olho em {palavra} de {reais(p1)}..."),
            (f"Antes de pagar {reais_falado(p1)} em {palavra}, olha isso.",
             f"Antes de pagar {reais(p1)} em {palavra}..."),
            (f"Procurando {palavra}? O mais curtido custa {reais_falado(p1)}.",
             f"O mais curtido custa {reais(p1)}"),
        ]
    else:
        ganchos = [
            (f"Todo mundo tá comprando {palavra} de {reais_falado(p1)}.",
             f"Todo mundo comprando {palavra} de {reais(p1)}..."),
            (f"Antes de pagar {reais_falado(p1)} em {palavra}, olha isso.",
             f"Antes de pagar {reais(p1)} em {palavra}..."),
            (f"Procurando {palavra}? O mais vendido custa {reais_falado(p1)}.",
             f"O mais vendido custa {reais(p1)}"),
        ]
    viradas = [
        (f"Mas achei uma opção parecida por {reais_falado(p2)}.",
         f"...achei uma opção parecida por {reais(p2)}"),
        (f"Só que tem esse aqui, bem avaliado, por {reais_falado(p2)}.",
         f"Esse aqui, bem avaliado, por {reais(p2)}"),
    ]
    comparacoes = [
        (f"São {reais_falado(dif)} de diferença. Nota {nota} e {vendas_texto(barato['vendas'])} {METRICA}.",
         f"{reais(dif)} de diferença"),
    ]
    finais = [
        ("O link dos dois tá no meu perfil. Salva pra não perder!", CHAMADA_FINAL),
        ("Link no perfil. Me segue pra mais achadinhos assim.", CHAMADA_FINAL),
    ]
    return [rnd.choice(ganchos), rnd.choice(viradas), rnd.choice(comparacoes), rnd.choice(finais)]


def selo_famoso():
    return "MAIS CURTIDO" if METRICA == "curtidas" else "MAIS VENDIDO"


def legenda_social(famoso, barato, palavra):
    """Legenda pro TikTok/Reels (lá link não é clicável, então aponta pro canal)."""
    dif = famoso["preco"] - barato["preco"]
    tag = re.sub(r"[^A-Za-z0-9]", "", sem_acento(palavra).title())
    return (
        f"{palavra.capitalize()}: {reais(famoso['preco'])} x {reais(barato['preco'])} "
        f"({reais(dif)} de diferença)\n\n"
        f"🔗 Link dos dois na bio\n"
        f"📩 No Instagram: comenta {PALAVRA_DM} que eu te mando no direct\n\n"
        f"#achadinhos #shopee #{tag} #publi (links de afiliado)"
    )


def post_canal(famoso, barato, palavra, link_famoso, link_barato):
    """Post do canal do Telegram, com links clicáveis (formato HTML)."""
    e = html.escape
    dif = famoso["preco"] - barato["preco"]
    return (
        f"<b>{e(palavra.capitalize())}: {reais(famoso['preco'])} x {reais(barato['preco'])}</b>\n"
        f"Economia de {reais(dif)}\n\n"
        f"🟢 <a href=\"{e(link_barato, quote=True)}\">Opção barata: {reais(barato['preco'])}</a>\n"
        f"{e(nome_curto(barato['nome'], 90))}\n\n"
        f"🔴 <a href=\"{e(link_famoso, quote=True)}\">{selo_famoso().capitalize()}: {reais(famoso['preco'])}</a>\n"
        f"{e(nome_curto(famoso['nome'], 90))}\n\n"
        f"#publi · links de afiliado"
    )


def texto_whatsapp(famoso, barato, palavra, link_famoso, link_barato):
    """Texto pronto pra colar no canal ou grupo do WhatsApp."""
    dif = famoso["preco"] - barato["preco"]
    return (
        f"*{palavra.capitalize()}*: {reais(famoso['preco'])} x *{reais(barato['preco'])}*\n"
        f"Economia de {reais(dif)}\n\n"
        f"🟢 Opção barata: {link_barato}\n"
        f"🔴 {selo_famoso().capitalize()}: {link_famoso}\n\n"
        f"_Links de afiliado_"
    )


def legenda(famoso, barato, palavra, link_famoso, link_barato):
    dif = famoso["preco"] - barato["preco"]
    tag = re.sub(r"[^A-Za-z0-9]", "", sem_acento(palavra).title())
    return (
        f"{palavra.capitalize()}: {reais(famoso['preco'])} x {reais(barato['preco'])} "
        f"({reais(dif)} de diferença)\n\n"
        f"Opção barata: {link_barato}\n"
        f"Mais vendido: {link_famoso}\n\n"
        f"#achadinhos #shopee #{tag} #publi (links de afiliado)"
    )


# ------------------------------------------------------------
# Imagens e vídeo
# ------------------------------------------------------------
FONTES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def fonte(tam):
    for f in FONTES:
        if os.path.exists(f):
            return ImageFont.truetype(f, tam)
    return ImageFont.load_default(size=tam)


def quebrar(draw, texto, f, largura):
    linhas, atual = [], ""
    for p in texto.split(" "):
        teste = (atual + " " + p).strip()
        if draw.textlength(teste, font=f) <= largura:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def texto_central(draw, texto, y, tam, cor="white", largura=W - 120, max_linhas=4):
    f = fonte(tam)
    linhas = quebrar(draw, texto, f, largura)
    while len(linhas) > max_linhas and tam > 40:
        tam -= 6
        f = fonte(tam)
        linhas = quebrar(draw, texto, f, largura)
    for linha in linhas[:max_linhas]:
        lw = draw.textlength(linha, font=f)
        draw.text(((W - lw) / 2, y), linha, font=f, fill=cor,
                  stroke_width=max(3, tam // 14), stroke_fill="black")
        y += int(tam * 1.18)
    return y


def fundo():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(24 + 30 * t), int(18 + 10 * t), int(48 + 40 * t)))
    return img


def colar_produto(img, foto, caixa):
    x0, y0, x1, y1 = caixa
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(caixa, radius=40, fill="white")
    pad = 30
    f = foto.copy()
    f.thumbnail((x1 - x0 - 2 * pad, y1 - y0 - 2 * pad))
    img.paste(f, (x0 + (x1 - x0 - f.width) // 2, y0 + (y1 - y0 - f.height) // 2),
              f if f.mode == "RGBA" else None)


def etiqueta(img, texto, centro_y, cor_fundo, tam=110):
    d = ImageDraw.Draw(img)
    f = fonte(tam)
    tw = d.textlength(texto, font=f)
    x0 = (W - tw) / 2 - 40
    d.rounded_rectangle((x0, centro_y - tam * 0.75, x0 + tw + 80, centro_y + tam * 0.75),
                        radius=30, fill=cor_fundo)
    d.text(((W - tw) / 2, centro_y - tam * 0.6), texto, font=f, fill="white",
           stroke_width=3, stroke_fill="black")


def nome_curto(nome, n=70):
    return nome if len(nome) <= n else nome[: n - 1].rsplit(" ", 1)[0] + "…"


def cena_produto(produto, foto, texto_tela, cor, selo):
    img = fundo()
    d = ImageDraw.Draw(img)
    texto_central(d, texto_tela, 130, 84, max_linhas=3)
    colar_produto(img, foto, (110, 560, W - 110, 1380))
    d.rounded_rectangle((110, 500, 110 + d.textlength(selo, font=fonte(48)) + 50, 580),
                        radius=20, fill=cor)
    d.text((135, 510), selo, font=fonte(48), fill="white")
    etiqueta(img, reais(produto["preco"]), 1520, cor)
    texto_central(d, nome_curto(produto["nome"]), 1660, 40, cor=(220, 220, 230), max_linhas=2)
    return img


def cena_comparacao(famoso, barato, f1, f2, texto_tela, nota_vendas):
    img = fundo()
    d = ImageDraw.Draw(img)
    texto_central(d, texto_tela, 160, 96, cor=(255, 230, 80))
    meia = (W - 60) // 2
    for i, (p, foto, cor) in enumerate([(famoso, f1, (200, 50, 60)), (barato, f2, (30, 160, 90))]):
        x0 = 20 + i * (meia + 20)
        colar_produto(img, foto, (x0, 560, x0 + meia, 1160))
        f = fonte(72)
        t = reais(p["preco"])
        tw = d.textlength(t, font=f)
        d.rounded_rectangle((x0, 1200, x0 + meia, 1320), radius=24, fill=cor)
        d.text((x0 + (meia - tw) / 2, 1218), t, font=f, fill="white")
    texto_central(d, nota_vendas, 1440, 60)
    return img


def cena_final(barato, foto, texto_tela):
    img = fundo()
    d = ImageDraw.Draw(img)
    colar_produto(img, foto, (240, 360, W - 240, 960))
    y = texto_central(d, texto_tela, 1100, 120, cor=(255, 230, 80))
    texto_central(d, "Salva pra não perder", y + 40, 64)
    return img


def baixar_foto(url, destino):
    if MODO_TESTE:
        return foto_falsa(url, destino)
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    destino.write_bytes(r.content)
    return Image.open(destino).convert("RGBA")


def foto_falsa(semente, destino):
    rnd = random.Random(semente)
    cor = tuple(rnd.randint(60, 220) for _ in range(3))
    img = Image.new("RGBA", (800, 800), (245, 245, 245, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((150, 150, 650, 650), fill=cor)
    d.rectangle((300, 600, 500, 720), fill=tuple(c // 2 for c in cor))
    img.convert("RGB").save(destino, "JPEG")
    return img


def narrar(texto, destino):
    """Gera a narração. Tenta edge-tts, depois gTTS; se nada funcionar, deixa em silêncio."""
    try:
        import asyncio
        import edge_tts
        asyncio.run(edge_tts.Communicate(texto, VOZ, rate="+12%").save(str(destino)))
        if destino.exists() and destino.stat().st_size > 1000:
            return True
    except Exception as e:
        print(f"  (edge-tts falhou: {e})")
    try:
        from gtts import gTTS
        gTTS(texto, lang="pt", tld="com.br").save(str(destino))
        return True
    except Exception as e:
        print(f"  (gTTS falhou: {e})")
    return False


def duracao(arquivo):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)],
        capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def montar_video(cenas, falas, pasta, destino):
    partes = []
    for i, (img, fala) in enumerate(zip(cenas, falas)):
        png = pasta / f"cena{i}.png"
        img.save(png)
        audio = pasta / f"fala{i}.mp3"
        tem_audio = narrar(fala, audio)
        seg = (duracao(audio) + 0.35) if tem_audio else max(2.5, len(fala) / 14)
        quadros = int(seg * 30)
        parte = pasta / f"parte{i}.mp4"
        zoom = (f"scale=2160:3840,zoompan=z='min(zoom+0.0006,1.06)':d={quadros}"
                f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png)]
        if tem_audio:
            cmd += ["-i", str(audio)]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-vf", zoom, "-t", f"{seg:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-af", "apad", "-shortest", str(parte)]
        subprocess.run(cmd, check=True)
        partes.append(parte)
    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{p.name}'\n" for p in partes))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c", "copy", "-movflags", "+faststart", str(destino)],
                   check=True)


# ------------------------------------------------------------
# Telegram
# ------------------------------------------------------------
def telegram(metodo, dados, arquivos=None):
    if MODO_TESTE or not TG_TOKEN:
        print(f"[telegram:{metodo}] {dados.get('caption') or dados.get('text', '')}"[:300])
        return
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{metodo}",
                      data=dados, files=arquivos, timeout=120)
    if not r.ok:
        print(f"Telegram erro: {r.text[:300]}")


def avisar(texto):
    if TG_CHAT:
        telegram("sendMessage", {"chat_id": TG_CHAT, "text": texto[:4000],
                                 "disable_web_page_preview": "true"})
    else:
        print(texto)


# ------------------------------------------------------------
# Página de ofertas (link da bio)
# ------------------------------------------------------------
def ler_ofertas():
    try:
        return json.loads(OFERTAS.read_text())
    except Exception:
        return []


def salvar_ofertas(ofertas):
    OFERTAS.write_text(json.dumps(ofertas[:OFERTAS_NA_PAGINA * 2], ensure_ascii=False, indent=1))


def oferta_registro(famoso, barato, palavra, link_f, link_b):
    def item(p, link):
        return {"nome": nome_curto(p["nome"], 90), "preco": p["preco"], "imagem": p["imagem"],
                "link": link, "nota": p["nota"], "pop": p["vendas"]}
    return {"data": dt.date.today().isoformat(), "palavra": palavra, "metrica": METRICA,
            "famoso": item(famoso, link_f), "barato": item(barato, link_b)}


PAGINA_CSS = """
:root{--bg:#fff7f2;--card:#fff;--txt:#1d1a18;--sub:#6b625c;--borda:#f0e2d8;--laranja:#ee4d2d;--verde:#14915a;--chip:#fde9e3}
@media (prefers-color-scheme:dark){:root{--bg:#141111;--card:#1f1b1a;--txt:#f5efeb;--sub:#b3a7a0;--borda:#332b28;--laranja:#ff6a4d;--verde:#3ccf8e;--chip:#3a2420}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:28px 16px 12px;text-align:center}h1{margin:0;font-size:28px;letter-spacing:-.5px}
header p{margin:6px auto 14px;max-width:420px;color:var(--sub)}
.acoes{display:flex;flex-wrap:wrap;justify-content:center;gap:8px}
.tg,.zap,.comp{display:inline-block;padding:9px 14px;border-radius:999px;background:var(--chip);color:var(--txt);text-decoration:none;font-weight:600;font-size:14px;border:0;font-family:inherit;cursor:pointer}
.zap{background:var(--verde);color:#fff}
main{max-width:560px;margin:0 auto;padding:8px 16px 32px}
input{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--borda);background:var(--card);color:var(--txt);font-size:16px;margin-bottom:14px}
.card{display:flex;gap:12px;background:var(--card);border:1px solid var(--borda);border-radius:16px;padding:12px;margin-bottom:12px}
.card img{width:104px;height:104px;object-fit:contain;border-radius:12px;background:#fff;flex-shrink:0}
.info{min-width:0;flex:1}.data{font-size:12px;color:var(--sub);text-transform:uppercase;letter-spacing:.4px}
.nome{margin:2px 0 6px;font-size:14px;color:var(--sub);overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.preco{font-size:24px;font-weight:800;color:var(--verde)}.antes{font-size:13px;color:var(--sub)}
.antes a{color:var(--sub)}.botoes{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.btn{display:inline-block;padding:9px 14px;border-radius:10px;background:var(--laranja);color:#fff;text-decoration:none;font-weight:700;font-size:15px}
.btn.wa{background:transparent;color:var(--verde);border:1.5px solid var(--verde);padding:7.5px 12px}
footer{max-width:560px;margin:0 auto;padding:0 16px 40px;color:var(--sub);font-size:13px;text-align:center}
.vazio{text-align:center;color:var(--sub);padding:40px 0}
"""


def gerar_pagina(ofertas):
    e = html.escape
    canal = TG_CANAL.lstrip("@")
    cartoes = []
    for o in ofertas[:OFERTAS_NA_PAGINA]:
        f, b = o["famoso"], o["barato"]
        d = dt.date.fromisoformat(o["data"]).strftime("%d/%m")
        rotulo = "o mais curtido" if o.get("metrica") == "curtidas" else "o mais vendido"
        busca = sem_acento(f"{o['palavra']} {b['nome']}".lower())
        msg = (f"Olha esse achadinho: {b['nome']} por {reais(b['preco'])} "
               f"({rotulo} custa {reais(f['preco'])}) {b['link']}")
        zap = "https://wa.me/?text=" + urllib.parse.quote(msg)
        cartoes.append(
            f'<article class="card" data-busca="{e(busca, quote=True)}">'
            f'<img src="{e(b["imagem"], quote=True)}" alt="{e(b["nome"], quote=True)}" loading="lazy">'
            f'<div class="info"><div class="data">{e(o["palavra"])} · {d}</div>'
            f'<div class="nome">{e(b["nome"])}</div>'
            f'<div class="preco">{reais(b["preco"])}</div>'
            f'<div class="antes">{rotulo} custa <a href="{e(f["link"], quote=True)}" rel="sponsored noopener">'
            f'{reais(f["preco"])}</a> · economia de {reais(f["preco"] - b["preco"])}</div>'
            f'<div class="botoes"><a class="btn" href="{e(b["link"], quote=True)}" rel="sponsored noopener">Ver na Shopee</a>'
            f'<a class="btn wa" href="{e(zap, quote=True)}">Enviar no WhatsApp</a></div>'
            f'</div></article>')
    lista = "\n".join(cartoes) or '<p class="vazio">As primeiras ofertas aparecem aqui amanhã cedo.</p>'
    botoes = []
    if CANAL_WHATSAPP:
        botoes.append(f'<a class="zap" href="{e(CANAL_WHATSAPP, quote=True)}">Receber no WhatsApp</a>')
    if canal:
        botoes.append(f'<a class="tg" href="https://t.me/{e(canal, quote=True)}">Receber no Telegram</a>')
    botoes.append('<button class="comp" id="compartilhar" type="button">Compartilhar a página</button>')
    botao_tg = '<div class="acoes">' + "".join(botoes) + '</div>'
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(NOME_PAGINA)}</title>
<meta name="description" content="Versões baratas dos produtos mais populares da Shopee, atualizado todo dia.">
<style>{PAGINA_CSS}</style></head>
<body><header><h1>{e(NOME_PAGINA)}</h1>
<p>Versões baratas dos produtos mais populares da Shopee. Atualizado todo dia.</p>{botao_tg}</header>
<main><input id="busca" type="search" placeholder="Buscar (ex.: fone, air fryer)" aria-label="Buscar">
{lista}</main>
<footer>Os links são de afiliado: posso ganhar uma comissão se você comprar, sem custo extra pra você.
Preços do dia indicado; podem mudar na Shopee.</footer>
<script>
const c=document.querySelectorAll('.card');
document.getElementById('busca').addEventListener('input',ev=>{{
const q=ev.target.value.toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
c.forEach(x=>x.style.display=x.dataset.busca.includes(q)?'':'none');}});
document.getElementById('compartilhar').addEventListener('click',async()=>{{
const t='Achadinhos baratos da Shopee, atualizados todo dia: '+location.href;
if(navigator.share){{try{{await navigator.share({{title:document.title,text:t,url:location.href}});}}catch(e){{}}}}
else{{location.href='https://wa.me/?text='+encodeURIComponent(t);}}}});
</script></body></html>"""


def publicar_pagina(ofertas):
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(gerar_pagina(ofertas), encoding="utf-8")


# ------------------------------------------------------------
# Histórico (pra não repetir produto)
# ------------------------------------------------------------
def ler_historico():
    try:
        dados = json.loads(HISTORICO.read_text())
    except Exception:
        dados = {}
    limite = (dt.date.today() - dt.timedelta(days=DIAS_SEM_REPETIR)).isoformat()
    return {k: v for k, v in dados.items() if v >= limite}


def salvar_historico(hist):
    HISTORICO.write_text(json.dumps(hist, indent=1, sort_keys=True))


# ------------------------------------------------------------
# Dados de teste (sem internet)
# ------------------------------------------------------------
def produtos_teste(palavra):
    rnd = random.Random(palavra)
    lista = []
    for i in range(12):
        lista.append({
            "id": f"{abs(hash(palavra)) % 10**6}{i}",
            "nome": f"{palavra.title()} Modelo {chr(65 + i)} Premium Original Envio Rápido",
            "url": f"https://shopee.com.br/produto-i.1.{i}",
            "oferta": f"https://s.shopee.com.br/teste{i}",
            "imagem": f"{palavra}-{i}",
            "preco": round(rnd.uniform(40, 260), 2),
            "vendas": rnd.randint(50, 9000),
            "nota": round(rnd.uniform(4.3, 5.0), 1),
            "taxa": 0.08, "comissao": 0, "loja": "Loja Teste",
        })
    return lista


# ------------------------------------------------------------
# Principal
# ------------------------------------------------------------
def palavras_de_hoje():
    hoje = dt.date.today().toordinal()
    n = min(VIDEOS_POR_DIA * 2, len(PALAVRAS))   # pega o dobro, caso alguma não dê par
    inicio = (hoje * VIDEOS_POR_DIA) % len(PALAVRAS)
    return [PALAVRAS[(inicio + i) % len(PALAVRAS)] for i in range(n)]


def ordem_de_hoje():
    """Todas as palavras, começando por um ponto diferente a cada dia."""
    inicio = (dt.date.today().toordinal() * VIDEOS_POR_DIA) % len(PALAVRAS)
    return PALAVRAS[inicio:] + PALAVRAS[:inicio]


def main():
    global METRICA
    usar_feed = bool(FEED_URLS)
    if usar_feed:
        METRICA = "curtidas"
    elif not MODO_TESTE and not (APP_ID and SECRET):
        avisar("Robô: falta o segredo SHOPEE_FEED_URL no GitHub "
               "(link do Feed de produto do painel de afiliado).")
        sys.exit(1)

    achados = {}
    palavras = ordem_de_hoje() if usar_feed else palavras_de_hoje()
    if usar_feed:
        try:
            achados = ler_feed(palavras)
        except Exception as e:
            avisar(f"Robô: não consegui ler o feed da Shopee ({e}). "
                   "Confira o segredo SHOPEE_FEED_URL.")
            sys.exit(1)

    hoje = dt.date.today()
    rnd = random.Random(hoje.toordinal())
    pasta_dia = SAIDA / hoje.isoformat()
    pasta_dia.mkdir(parents=True, exist_ok=True)
    hist = ler_historico()
    ofertas = ler_ofertas()
    blocos_whatsapp = []
    feitos = 0

    for palavra in palavras:
        if feitos >= VIDEOS_POR_DIA:
            break
        print(f"> {palavra}")
        try:
            if usar_feed:
                produtos = filtrar_feed(achados.get(palavra, []), palavra)
            elif MODO_TESTE:
                produtos = produtos_teste(palavra)
            else:
                vistos = {}
                for ordem in (2, 1):          # mais vendidos + relevância
                    for p in buscar(palavra, ordem):
                        vistos[p["id"]] = p
                produtos = list(vistos.values())

            par = escolher_par(produtos, palavra, hist)
            if not par:
                print("  nenhum par bom hoje")
                continue
            famoso, barato = par

            sub = ["robo", hoje.strftime("%Y%m%d")]
            if MODO_TESTE or usar_feed:
                link_f, link_b = famoso["oferta"], barato["oferta"]
            else:
                try:
                    link_f = link_curto(famoso["url"], sub)
                    link_b = link_curto(barato["url"], sub)
                except Exception as e:
                    print(f"  (link curto falhou, usando link de oferta: {e})")
                    link_f, link_b = famoso["oferta"], barato["oferta"]

            slug = re.sub(r"[^a-z0-9]+", "-", sem_acento(palavra).lower()).strip("-")
            pasta = pasta_dia / slug
            pasta.mkdir(exist_ok=True)
            f1 = baixar_foto(famoso["imagem"], pasta / "famoso.jpg")
            f2 = baixar_foto(barato["imagem"], pasta / "barato.jpg")

            r = roteiro(famoso, barato, palavra, rnd)
            falas = [x[0] for x in r]
            telas = [x[1] for x in r]
            nota_vendas = (f"Nota {barato['nota']:.1f}".replace(".", ",")
                           + f"  •  {vendas_texto(barato['vendas'])} {METRICA}")
            cenas = [
                cena_produto(famoso, f1, telas[0], (200, 50, 60), selo_famoso()),
                cena_produto(barato, f2, telas[1], (30, 160, 90), "OPÇÃO BARATA"),
                cena_comparacao(famoso, barato, f1, f2, telas[2], nota_vendas),
                cena_final(barato, f2, telas[3]),
            ]
            video = pasta_dia / f"{slug}.mp4"
            montar_video(cenas, falas, pasta, video)

            texto_post = legenda_social(famoso, barato, palavra)
            texto_canal = post_canal(famoso, barato, palavra, link_f, link_b)
            resumo = f"🎬 {palavra} — pronto pra postar\n"
            comissao = barato["comissao"] or barato["preco"] * barato["taxa"]
            if comissao:
                resumo += (f"Comissão estimada na opção barata: {reais(comissao)} "
                           f"({barato['taxa'] * 100:.0f}%)\n")
            if usar_feed and "an_redir" not in link_b and "affiliate" not in link_b:
                resumo += "Atenção: o link não parece ser de afiliado. Me avise.\n"
            resumo += f"\nNarração: {' '.join(falas)}"

            if TG_CHAT:
                with open(video, "rb") as fv:
                    telegram("sendVideo", {"chat_id": TG_CHAT, "caption": resumo[:1000],
                                           "supports_streaming": "true"}, {"video": fv})
                avisar("Legenda pra copiar:\n\n" + texto_post)
                blocos_whatsapp.append(texto_whatsapp(famoso, barato, palavra, link_f, link_b))
                telegram("sendMessage", {"chat_id": TG_CHAT, "text": "Links:\n\n" + texto_canal,
                                         "parse_mode": "HTML", "disable_web_page_preview": "true"})
            else:
                print(resumo + "\n\n" + texto_post + "\n\n" + texto_canal)

            if TG_CANAL:
                telegram("sendPhoto", {"chat_id": TG_CANAL, "photo": barato["imagem"],
                                       "caption": texto_canal, "parse_mode": "HTML"})

            hist[famoso["id"]] = hoje.isoformat()
            hist[barato["id"]] = hoje.isoformat()
            ofertas.insert(0, oferta_registro(famoso, barato, palavra, link_f, link_b))
            feitos += 1
        except Exception as e:
            print(f"  erro em '{palavra}': {e}")
            if "Shopee respondeu erro" in str(e) and feitos == 0:
                avisar(f"Robô parou: {e}\nConfira o App ID e o Secret da Shopee nos segredos do GitHub.")
                break

    salvar_historico(hist)
    salvar_ofertas(ofertas)
    publicar_pagina(ofertas)
    if blocos_whatsapp:
        # um texto só por dia, com todas as ofertas, pra colar no canal do WhatsApp
        texto = f"*Achadinhos de hoje* ({hoje:%d/%m})\n\n" + "\n\n— — —\n\n".join(blocos_whatsapp)
        if PAGINA_URL:
            texto += f"\n\nTodas as ofertas: {PAGINA_URL}"
        avisar("Pro WhatsApp (copie tudo abaixo e cole no seu canal):")
        avisar(texto)
    if feitos == 0:
        avisar("Robô: hoje não achei nenhum par bom. Tente outras palavras em PALAVRAS "
               "ou baixe ECONOMIA_MINIMA / CURTIDAS_MINIMAS.")
    print(f"Pronto: {feitos} vídeo(s).")


if __name__ == "__main__":
    main()
