# -*- coding: utf-8 -*-
"""
Robô de achadinhos Shopee
-------------------------
Todo dia ele:
  1. pega os mais vendidos de algumas palavras-chave na Shopee;
  2. acha uma opção parecida e bem mais barata;
  3. gera seus links de afiliado;
  4. monta um vídeo vertical (9:16) com narração;
  5. manda o vídeo + legenda pronta pro seu Telegram
     (e, se você tiver, posta a oferta no seu canal).

Você só precisa mexer na parte "CONFIGURAÇÃO" logo abaixo.
"""

import datetime as dt
import hashlib
import json
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
VENDAS_MINIMAS = 100      # vendas mínimas da opção barata
ECONOMIA_MINIMA = 0.30    # a opção barata precisa ser pelo menos 30% mais barata
DIAS_SEM_REPETIR = 30     # não repete o mesmo produto por esse tempo

# Texto do final do vídeo (onde está o link pra pessoa)
CHAMADA_FINAL = "Link no perfil"
VOZ = "pt-BR-AntonioNeural"   # ou "pt-BR-FranciscaNeural" (voz feminina)

# ============================================================
# (daqui pra baixo não precisa mexer)
# ============================================================

API_URL = "https://open-api.affiliate.shopee.com.br/graphql"
PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / "saida"
HISTORICO = PASTA / "historico.json"
W, H = 1080, 1920

APP_ID = os.environ.get("SHOPEE_APP_ID", "").strip()
SECRET = os.environ.get("SHOPEE_SECRET", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TG_CANAL = os.environ.get("TELEGRAM_CANAL", "").strip()

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
        candidatas = [
            p for p in bons
            if p["id"] != famoso["id"] and p["id"] not in usados
            and p["preco"] <= teto and p["vendas"] >= VENDAS_MINIMAS
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
    return f"{inteiro} reais" + (f" e {cent}" if cent else "")


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
        (f"São {reais_falado(dif)} de diferença. Nota {nota} e {vendas_texto(barato['vendas'])} vendidos.",
         f"{reais(dif)} de diferença"),
    ]
    finais = [
        ("O link dos dois tá no meu perfil. Salva pra não perder!", CHAMADA_FINAL),
        ("Link no perfil. Me segue pra mais achadinhos assim.", CHAMADA_FINAL),
    ]
    return [rnd.choice(ganchos), rnd.choice(viradas), rnd.choice(comparacoes), rnd.choice(finais)]


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
    texto_central(d, texto_tela, 130, 84)
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


def main():
    if not MODO_TESTE and not (APP_ID and SECRET):
        avisar("Robô: faltam os segredos SHOPEE_APP_ID e SHOPEE_SECRET no GitHub.")
        sys.exit(1)

    hoje = dt.date.today()
    rnd = random.Random(hoje.toordinal())
    pasta_dia = SAIDA / hoje.isoformat()
    pasta_dia.mkdir(parents=True, exist_ok=True)
    hist = ler_historico()
    feitos = 0

    for palavra in palavras_de_hoje():
        if feitos >= VIDEOS_POR_DIA:
            break
        print(f"> {palavra}")
        try:
            if MODO_TESTE:
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
            if MODO_TESTE:
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
                           + f"  •  {vendas_texto(barato['vendas'])} vendidos")
            cenas = [
                cena_produto(famoso, f1, telas[0], (200, 50, 60), "MAIS VENDIDO"),
                cena_produto(barato, f2, telas[1], (30, 160, 90), "OPÇÃO BARATA"),
                cena_comparacao(famoso, barato, f1, f2, telas[2], nota_vendas),
                cena_final(barato, f2, telas[3]),
            ]
            video = pasta_dia / f"{slug}.mp4"
            montar_video(cenas, falas, pasta, video)

            texto_post = legenda(famoso, barato, palavra, link_f, link_b)
            comissao = barato["comissao"] or barato["preco"] * barato["taxa"]
            resumo = (f"🎬 {palavra} — pronto pra postar\n"
                      f"Comissão estimada na opção barata: {reais(comissao)} "
                      f"({barato['taxa'] * 100:.0f}%)\n\n"
                      f"Narração: {' '.join(falas)}")

            if TG_CHAT:
                with open(video, "rb") as fv:
                    telegram("sendVideo", {"chat_id": TG_CHAT, "caption": resumo[:1000],
                                           "supports_streaming": "true"}, {"video": fv})
                avisar("Legenda pra copiar:\n\n" + texto_post)
            else:
                print(resumo + "\n\n" + texto_post)

            if TG_CANAL:
                telegram("sendPhoto", {"chat_id": TG_CANAL, "photo": barato["imagem"],
                                       "caption": texto_post[:1000]})

            hist[famoso["id"]] = hoje.isoformat()
            hist[barato["id"]] = hoje.isoformat()
            feitos += 1
        except Exception as e:
            print(f"  erro em '{palavra}': {e}")
            if "Shopee respondeu erro" in str(e) and feitos == 0:
                avisar(f"Robô parou: {e}\nConfira o App ID e o Secret da Shopee nos segredos do GitHub.")
                break

    salvar_historico(hist)
    if feitos == 0:
        avisar("Robô: hoje não achei nenhum par bom. Tente mais palavras ou baixe ECONOMIA_MINIMA.")
    print(f"Pronto: {feitos} vídeo(s).")


if __name__ == "__main__":
    main()
