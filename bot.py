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
import math
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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

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

VIDEOS_POR_DIA = 2        # quantos vídeos por dia
PRECO_MAXIMO = 150        # achadinho vende por impulso: acima desse preço o produto fica de fora (0 = sem limite)
NOTA_MINIMA = 4.5         # nota mínima dos produtos (0 a 5)
VENDAS_MINIMAS = 100      # vendas mínimas da opção barata (só no modo Open API)
CURTIDAS_MINIMAS = 30     # curtidas mínimas da opção barata (modo feed)
ECONOMIA_MINIMA = 0.30    # a opção barata precisa ser pelo menos 30% mais barata
ECONOMIA_MAXIMA = 0.85    # mais de 85% mais barata costuma ser outra coisa (ou preço isca)
SO_ENVIO_NACIONAL = True  # só produtos enviados do Brasil (entrega mais rápida)
DIAS_SEM_REPETIR = 30     # não repete o mesmo produto por esse tempo

# Formato do vídeo:
#   "telaverde"   -> produto em tela cheia trocando de enquadramento e o Lupi no canto apresentando
#                    (a amiga abre com uma pergunta), no estilo "tela verde" dos afiliados do TikTok
#   "conversa"    -> o Lupi (mascote) conversa com uma amiga sobre um produto em promoção
#   "promo"       -> um produto em promoção: "de R$ X por R$ Y", funções do produto, nota e curtidas
#   "comparativo" -> produto famoso x opção parecida mais barata
FORMATO = "telaverde"
DESCONTO_MINIMO = 0.20    # promo: só produtos com pelo menos 20% de desconto na Shopee
DESCONTO_MAXIMO = 0.75    # promo: desconto acima disso costuma ser preço "cheio" inflado
USAR_IA = True            # IA gratuita do Google (Gemini) escreve o roteiro; precisa do segredo GEMINI_API_KEY

# Texto do final do vídeo (onde está o link pra pessoa)
CHAMADA_FINAL = "Link no perfil"

# Página automática com as ofertas (vai no link da bio)
NOME_PAGINA = "Achadinhos Baratos"
SUBTITULO = "Promoções dos produtos mais curtidos da Shopee. Atualizado todo dia."
OFERTAS_NA_PAGINA = 40    # quantas ofertas recentes a página mostra
PALAVRA_DM = "QUERO"      # palavra do "comenta que eu mando no direct" (Instagram)
# Link do seu canal do WhatsApp (WhatsApp → Atualizações → seu canal → Compartilhar link).
# Deixe vazio ("") pra esconder o botão "Receber no WhatsApp" da página.
CANAL_WHATSAPP = "https://whatsapp.com/channel/0029VbEeN7aElagzyls0tb0N"
NOME_PAINEL = "painel.html"   # sua página com os vídeos do dia (não aparece na página pública)
VOZ = "pt-BR-FranciscaNeural"   # voz feminina; "pt-BR-AntonioNeural" é a masculina
VELOCIDADE = "+8%"               # ritmo da narração ("+0%" normal, "+15%" mais rápido)
RITMO_TELA_VERDE = "+15%"        # tela verde: fala mais rápida, como nos vídeos de afiliado que vendem

# Clipes do Google Flow: de manhã o robô manda no Telegram as fotos e o texto pronto de cada produto;
# você gera o clipe no Flow (celular) e manda de volta pro robô. Ele confere se o produto saiu igual
# e usa o clipe em quase todo o vídeo: inteiro no começo, depois trechos dele com zoom, e a foto do
# produto só no final, com a chamada. Se o clipe não chegar a tempo, o vídeo sai só com as fotos.
USAR_FLOW = True
MODELO_FLOW = "Omni 1.2 Flash"     # 24 créditos por clipe; o "Veo 3.1 - Lite" custa 10, mas erra mais o produto
CREDITOS_FLOW = 24
HORARIOS_POSTAGEM = ["11:47", "19:47"]   # só pra avisar no kit; os horários de verdade ficam no robo.yml

# ============================================================
# (daqui pra baixo não precisa mexer)
# ============================================================

API_URL = "https://open-api.affiliate.shopee.com.br/graphql"
PASTA = Path(__file__).resolve().parent
SAIDA = PASTA / "saida"
HISTORICO = PASTA / "historico.json"
OFERTAS = PASTA / "ofertas.json"
FILA = PASTA / "fila.json"          # produtos do dia esperando o clipe do Flow
SITE = PASTA / "site"
W, H = 1080, 1920

APP_ID = os.environ.get("SHOPEE_APP_ID", "").strip()
SECRET = os.environ.get("SHOPEE_SECRET", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
TG_CANAL = os.environ.get("TELEGRAM_CANAL", "").strip()
FEED_URLS = os.environ.get("SHOPEE_FEED_URL", "").split()
AFILIADO_ID = os.environ.get("SHOPEE_AFFILIATE_ID", "").strip()   # seu ID de afiliado (painel da Shopee)
_repo = os.environ.get("GITHUB_REPOSITORY", "")          # "usuario/repositorio" quando roda no GitHub
PAGINA_URL = (f"https://{_repo.split('/')[0]}.github.io/{_repo.split('/')[1]}/" if "/" in _repo else "")

METRICA = "vendidos"      # no modo feed vira "curtidas" (o feed não informa vendas)

MODO_TESTE = "--teste" in sys.argv
# kit = manda as fotos e o texto do Flow; postar = monta e entrega o próximo vídeo do dia;
# completo = o jeito antigo (escolhe e monta tudo de uma vez, sem Flow)
MODO = next((a for a in sys.argv[1:] if a in ("kit", "postar", "completo")), "completo")


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
          "priceDiscountRate sales ratingStar commissionRate commission shopName")


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
        "desconto": num(n.get("priceDiscountRate")) / 100,
        "preco_cheio": (num(n.get("priceMin")) / (1 - num(n.get("priceDiscountRate")) / 100)
                        if 0 < num(n.get("priceDiscountRate")) < 100 else num(n.get("priceMin"))),
        "descricao": "", "imagem2": "", "imagens": [n.get("imageUrl")] if n.get("imageUrl") else [],
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
    preco = num(linha.get("sale_price")) or num(linha.get("price"))
    cheio = num(linha.get("price"))
    # todas as fotos do anúncio (image_link, image_link_2, image_link_3...), sem repetir
    extras = sorted((k for k in linha if k and re.fullmatch(r"image_link_\d+", k)),
                    key=lambda k: int(k.rsplit("_", 1)[1]))
    imagens = [u for u in dict.fromkeys([linha.get("image_link") or ""] + [linha.get(k) or "" for k in extras]) if u]
    return {
        "id": str(linha.get("itemid") or ""),
        "nome": (linha.get("title") or "").strip(),
        "url": linha.get("product_link") or "",
        "oferta": linha.get("product_short link") or linha.get("product_link") or "",
        "imagem": linha.get("image_link") or "",
        "preco": preco,
        "preco_cheio": cheio if cheio > preco else preco,
        "desconto": (1 - preco / cheio) if cheio > preco > 0 else 0.0,
        "descricao": (linha.get("description") or "")[:1500],
        "imagem2": linha.get("image_link_3") or "",
        "imagens": imagens[:6],
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


def escolher_promo(produtos, usados):
    minimo = CURTIDAS_MINIMAS if METRICA == "curtidas" else VENDAS_MINIMAS
    bons = [p for p in produtos
            if p["id"] not in usados and p["imagem"] and p["preco"] > 0
            and (not PRECO_MAXIMO or p["preco"] <= PRECO_MAXIMO)
            and DESCONTO_MINIMO <= p.get("desconto", 0) <= DESCONTO_MAXIMO
            and p["nota"] >= NOTA_MINIMA and p["vendas"] >= minimo]
    if not bons:
        return None
    # o mais popular entre os que estão com desconto de verdade
    return max(bons, key=lambda p: (p["vendas"], p["desconto"]))


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


def reais_curto(v):
    """Preço do jeito que se fala rápido: '49 e 90' (ou '50 reais' quando não tem centavos)."""
    inteiro = int(v)
    cent = int(round((v - inteiro) * 100))
    if cent == 100:
        inteiro, cent = inteiro + 1, 0
    if not cent:
        return f"{inteiro} reais"
    return f"{inteiro} e {cent}" if cent >= 10 else reais_falado(v)


def vendas_texto(n):
    if 1000 <= n < 2000:
        return "mais de mil"
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
        f"🔴 {selo_famoso().capitalize()}: {link_famoso}"
    )


# ------------------------------------------------------------
# Roteiro com IA: Gemini, do Google (plano gratuito; a chave fica no segredo GEMINI_API_KEY).
# O robô escolhe sozinho um modelo "flash" disponível, porque o Google troca os nomes
# dos modelos de tempos em tempos.
# ------------------------------------------------------------
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_RESERVA = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
IA_INFO = {"modelo": "", "erro": ""}    # o painel mostra se a IA funcionou e, se não, por quê
_MODELOS_GEMINI = []
PROIBIDO = ["pouco tempo", "ultimas unidades", "so hoje", "acaba hoje", "estoque limitado",
            "relampago", "corre que acaba", "nao vai durar", "por tempo limitado"]

IA_SISTEMA = (
    "Você escreve roteiros de anúncios curtos (vídeos de 15 segundos) para TikTok e Reels, "
    "em português do Brasil, com tom animado e natural. Regras: use SOMENTE informações que "
    "estão no título e na descrição; não invente medidas, materiais, garantias, resultados nem "
    "depoimentos; não fale de prazo da promoção, de estoque nem de 'pouco tempo'; não mencione "
    "preço (ele entra depois); nunca fale como se alguém tivesse usado, comprado ou testado o produto "
    "(nada de 'eu uso', 'comprei', 'paguei', 'na minha casa'); não use emojis nem hashtags. "
    "Responda apenas com um objeto JSON."
)
# frases de quem diz que usou/comprou: o Lupi não pode dizer isso (seria depoimento falso)
EXPERIENCIA = re.compile(r"\b(eu (uso|usei|comprei|testei|paguei|tenho)|comprei|paguei|testei|"
                         r"minha casa|aqui em casa|a minha|o meu|na minha|no meu)\b")


def _motivo(r):
    try:
        return str(r.json().get("error", {}).get("message", "")).strip()[:180] or r.text[:180]
    except Exception:
        return r.text[:180]


def _modelos_gemini(chave):
    """Modelos 'flash' que a chave pode usar: primeiro os estáveis e mais novos, depois os 'lite' e prévias."""
    if _MODELOS_GEMINI:
        return _MODELOS_GEMINI
    nomes = []
    try:
        r = requests.get(f"{GEMINI_URL}/models", params={"pageSize": 1000},
                         headers={"x-goog-api-key": chave}, timeout=30)
        if r.ok:
            nomes = [m.get("name", "").split("/", 1)[-1] for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
        else:
            IA_INFO["erro"] = f"o Google recusou a chave ({r.status_code}): {_motivo(r)}"
    except Exception as e:
        IA_INFO["erro"] = f"não consegui falar com o Google ({e})"
    ruins = ("image", "tts", "audio", "live", "embed", "thinking", "exp", "native", "computer", "robotics")

    def ordem(n):
        v = re.match(r"gemini-(\d+(?:\.\d+)?)", n)
        return ("preview" in n, "lite" in n, -(float(v.group(1)) if v else 0.0), n)
    bons = sorted({n for n in nomes if n.startswith("gemini") and "flash" in n
                   and not any(x in n for x in ruins)}, key=ordem)
    _MODELOS_GEMINI[:] = (bons + [m for m in GEMINI_RESERVA if m not in bons])[:6]
    return _MODELOS_GEMINI


def _jpeg_b64(img, lado=768):
    import base64
    f = img.convert("RGB")
    f.thumbnail((lado, lado))
    buf = io.BytesIO()
    f.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def chamar_ia(mensagens, imagens=None):
    """Manda o pedido pro Gemini e devolve o texto da resposta ("" se não deu; o motivo fica em IA_INFO).
    imagens: fotos (PIL) que vão junto com a última mensagem, pra IA olhar."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if MODO_TESTE or not USAR_IA:
        IA_INFO["erro"] = "modo teste (a IA não é chamada)" if MODO_TESTE else "a IA está desligada (USAR_IA = False)"
        return ""
    if not chave:
        IA_INFO["erro"] = "falta o segredo GEMINI_API_KEY no GitHub (ou a linha dele no robo.yml)"
        return ""
    sistema = "\n".join(m["content"] for m in mensagens if m["role"] == "system")
    corpo = {"contents": [{"role": "model" if m["role"] == "assistant" else "user",
                           "parts": [{"text": m["content"]}]} for m in mensagens if m["role"] != "system"],
             "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192,
                                  "responseMimeType": "application/json"}}
    if sistema:
        corpo["systemInstruction"] = {"parts": [{"text": sistema}]}
    if imagens and corpo["contents"]:
        corpo["contents"][-1]["parts"] += [{"inline_data": {"mime_type": "image/jpeg", "data": _jpeg_b64(im)}}
                                           for im in imagens]
    for modelo in _modelos_gemini(chave):
        for _ in range(2):
            try:
                r = requests.post(f"{GEMINI_URL}/models/{modelo}:generateContent", json=corpo, timeout=90,
                                  headers={"x-goog-api-key": chave, "Content-Type": "application/json"})
            except Exception as e:
                IA_INFO["erro"] = f"{modelo}: {e}"
                break
            if r.status_code == 400 and "responseMimeType" in corpo["generationConfig"]:
                corpo["generationConfig"].pop("responseMimeType")   # tenta de novo sem o "só JSON"
                continue
            if not r.ok:
                IA_INFO["erro"] = f"{modelo} respondeu {r.status_code}: {_motivo(r)}"
                print(f"  (IA {IA_INFO['erro']})")
                break
            try:
                partes = r.json()["candidates"][0]["content"]["parts"]
                texto = "".join(p.get("text", "") for p in partes if not p.get("thought"))
            except Exception:
                texto = ""
            if texto.strip():
                IA_INFO["modelo"] = modelo
                return texto
            IA_INFO["erro"] = f"{modelo} devolveu uma resposta vazia"
            break
    return ""


def limpar_texto(t, limite):
    t = re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF#*_~`]", "", str(t or ""))
    t = re.sub(r"\s+", " ", t).strip(" \"'-•")
    return t[:limite].rstrip(" ,;:")


def validar_ia(d):
    if not isinstance(d, dict):
        return {}
    out = {}
    nome = limpar_texto(d.get("nome_curto"), 45)
    if len(nome) >= 3:
        out["nome_curto"] = nome
    gancho = limpar_texto(d.get("gancho"), 90)
    if len(gancho) >= 8 and "r$" not in gancho.lower() and "reais" not in gancho.lower():
        out["gancho"] = gancho if gancho.endswith((".", "!", "?")) else gancho + "!"
    itens = d.get("beneficios") if isinstance(d.get("beneficios"), list) else []
    itens = [limpar_texto(b, 42) for b in itens if isinstance(b, str)]
    itens = [b for b in itens if len(b) >= 3][:3]
    if itens:
        out["beneficios"] = itens
    pergunta = limpar_texto(d.get("pergunta_amiga"), 110)
    if len(pergunta) >= 10 and "r$" not in pergunta.lower():
        out["pergunta_amiga"] = pergunta if pergunta.endswith("?") else pergunta.rstrip(".!") + "?"
    fala = limpar_texto(d.get("fala_beneficios"), 240)
    if len(fala) >= 15:
        out["fala_beneficios"] = fala if fala.endswith((".", "!", "?")) else fala + "."
    # tela verde: o que é e como funciona, usos concretos, volta no gancho e resumo
    como = limpar_texto(d.get("como_funciona"), 170)
    if len(como) >= 12 and "r$" not in como.lower() and "reais" not in como.lower():
        out["como_funciona"] = como if como.endswith((".", "!", "?")) else como + "."
    usos = d.get("usos") if isinstance(d.get("usos"), list) else []
    usos = [limpar_texto(u, 24) for u in usos if isinstance(u, str)]
    usos = [u for u in usos if len(u) >= 2][:4]
    fala_usos = limpar_texto(d.get("fala_usos"), 170)
    if len(usos) >= 2 and len(fala_usos) >= 10 and "r$" not in fala_usos.lower():
        out["usos"] = usos
        out["fala_usos"] = fala_usos if fala_usos.endswith((".", "!", "?")) else fala_usos + "."
    volta = limpar_texto(d.get("volta_gancho"), 50)
    if len(volta) >= 4 and len(volta.split()) <= 8:
        out["volta_gancho"] = volta if volta.endswith((".", "!", "?")) else volta + "!"
    resumo = limpar_texto(d.get("resumo"), 90)
    if len(resumo) >= 10 and "r$" not in resumo.lower():
        out["resumo"] = resumo if resumo.endswith((".", "!", "?")) else resumo + "."
    for chave in ("gancho", "fala_beneficios", "como_funciona", "fala_usos", "volta_gancho", "resumo"):
        if chave in out and EXPERIENCIA.search(sem_acento(out[chave]).lower()):
            print(f"  (IA falou como se tivesse usado o produto em '{chave}'; tirei essa frase)")
            out.pop(chave)
            if chave == "fala_usos":
                out.pop("usos", None)
    tudo = sem_acento(" ".join([out.get(c, "") for c in ("gancho", "fala_beneficios", "pergunta_amiga",
                                                         "como_funciona", "fala_usos", "volta_gancho",
                                                         "resumo")]
                               + out.get("beneficios", []) + out.get("usos", [])).lower())
    if any(re.search(rf"\b{re.escape(x)}\b", tudo) for x in PROIBIDO):
        print("  (IA escreveu promessa que não dá pra garantir; usando texto padrão)")
        IA_INFO["erro"] = "a IA escreveu uma promessa que não dá pra garantir (ex.: 'só hoje'), então usei o texto padrão"
        return {}
    return out


def roteiro_ia(p):
    """Pede pra IA: nome curto, chamada, 3 funções e uma fala sobre o produto."""
    pedido = (
        f"Produto: {p['nome']}\n"
        f"Descrição do vendedor (pode estar bagunçada): {p.get('descricao', '')[:1500]}\n\n"
        "Devolva JSON com estas chaves:\n"
        '"nome_curto": nome simples do produto, até 4 palavras, do jeito que as pessoas falam no dia a dia;\n'
        '"pergunta_amiga": pergunta bem curta (até 9 palavras) que uma amiga faria ao Lupi sobre o problema '
        'do dia a dia que esse produto resolve, sem citar o produto (ex.: "Lupi, tem jeito de ... sem ...?");\n'
        '"gancho": frase de abertura que prende a atenção nos 2 primeiros segundos, até 8 palavras, '
        'de preferência uma pergunta sobre o problema que o produto resolve ou uma curiosidade;\n'
        '"beneficios": lista com 3 funções ou vantagens reais do produto, cada uma com até 5 palavras;\n'
        '"fala_beneficios": 1 ou 2 frases curtas para narração, em tom de conversa, começando pelo '
        'problema que ele resolve, até 25 palavras;\n'
        '"como_funciona": resposta do Lupi à pergunta da amiga, uma frase só, até 14 palavras: diz o que '
        'o produto é e o principal problema que ele resolve ou o diferencial dele, sem explicar passo a passo '
        '(ex.: "Esse mop lava e seca no próprio balde, sem pôr a mão na água.").'
    )
    texto = chamar_ia([{"role": "system", "content": IA_SISTEMA},
                       {"role": "user", "content": pedido}])
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        if texto:
            IA_INFO["erro"] = "a resposta da IA veio num formato que o robô não entendeu"
        return {}
    try:
        return validar_ia(json.loads(m.group(0)))
    except Exception:
        IA_INFO["erro"] = "a resposta da IA veio num formato que o robô não entendeu"
        return {}


def nome_promo(p, ia, palavra):
    nome = ia.get("nome_curto") or palavra
    return nome[0].upper() + nome[1:]


def roteiro_promo(p, ia, rnd):
    pct = round(p["desconto"] * 100)
    nota = f"{p['nota']:.1f}".replace(".", ",")
    gancho = ia.get("gancho") or rnd.choice([
        "Você precisa ver o preço disso!", "Para tudo e olha esse desconto!",
        "Achei esse achadinho em promoção!"])
    cenas = [("gancho", gancho, gancho),
             ("preco", f"Na Shopee, de {reais_falado(p['preco_cheio'])} por {reais_falado(p['preco'])}. "
                       f"São {pct} por cento de desconto.", "")]
    if ia.get("fala_beneficios") and ia.get("beneficios"):
        cenas.append(("beneficios", ia["fala_beneficios"], ""))
    if p["nota"] >= 1:
        envio = " E é enviado do Brasil." if p.get("nacional", True) else ""
        cenas.append(("prova", f"Nota {nota} na Shopee, com {vendas_texto(p['vendas'])} {METRICA}.{envio}", ""))
    cenas.append(("cta", rnd.choice([
        "O preço pode mudar a qualquer momento. O link tá no meu perfil!",
        "Preço bom assim pode mudar a qualquer hora. Corre no link do perfil!"]), ""))
    return cenas


def legenda_promo(p, ia, palavra, ia_video=False):
    pct = round(p["desconto"] * 100)
    tag = re.sub(r"[^A-Za-z0-9]", "", sem_acento(palavra).title())
    linhas = [f"#publi | {nome_promo(p, ia, palavra)}: de {reais(p['preco_cheio'])} por "
              f"{reais(p['preco'])} na Shopee (-{pct}%) 🔥", ""]
    for b in ia.get("beneficios", []):
        linhas.append(f"✅ {b}")
    if ia.get("beneficios"):
        linhas.append("")
    linhas += ["🔗 Link na bio",
               f"📩 No Instagram: comenta {PALAVRA_DM} que eu te mando no direct", ""]
    if ia_video:
        linhas.append("🤖 Cenas do produto em uso geradas por IA; o produto é o do anúncio.")
    linhas += [f"Preço visto em {dt.date.today():%d/%m}, pode mudar.",
               f"#achadinhos #shopee #{tag} (link de afiliado)"]
    return "\n".join(linhas)


def canal_promo(p, ia, palavra, link):
    e = html.escape
    pct = round(p["desconto"] * 100)
    itens = "".join(f"✅ {e(b)}\n" for b in ia.get("beneficios", []))
    return (f"<b>{e(nome_promo(p, ia, palavra))}</b>\n"
            f"De <s>{reais(p['preco_cheio'])}</s> por <b>{reais(p['preco'])}</b> (-{pct}%)\n\n"
            f"{itens}"
            f"\n🛒 <a href=\"{e(link, quote=True)}\">Ver na Shopee</a>\n\n"
            f"Preço de {dt.date.today():%d/%m}, pode mudar · #publi")


def whatsapp_promo(p, ia, palavra, link):
    pct = round(p["desconto"] * 100)
    itens = "".join(f"✅ {b}\n" for b in ia.get("beneficios", []))
    return (f"*{nome_promo(p, ia, palavra)}*\n"
            f"De ~{reais(p['preco_cheio'])}~ por *{reais(p['preco'])}* (-{pct}%)\n"
            f"{itens}"
            f"🛒 {link}")


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


# ------------------------------------------------------------
# Design v2 do formato promo (fundo com a foto, cartão, etiqueta de preço,
# checklist, legendas sincronizadas e efeitos sonoros)
# Tudo dentro da área segura do TikTok/Reels: x 120–960, y 220–1580.
# ------------------------------------------------------------
LARANJA = (255, 92, 40)
AMARELO = (255, 214, 10)
VERDE = (22, 178, 104)
VERMELHO = (229, 38, 47)
CINZA = (205, 200, 215)
PRETO = (18, 16, 22)
LEGENDA_Y = 1335          # centro das legendas (acima da área de botões e textos do app)

_DIRS_FONTE = ["/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/inter",
               str(Path.home() / ".fonts"), str(Path.home() / ".local/share/fonts"),
               str(PASTA / "fontes")]


def _achar_fonte(nome):
    for d in _DIRS_FONTE:
        f = Path(d) / nome
        if f.exists():
            return str(f)
    return ""


FONTE_FORTE = _achar_fonte("InterDisplay-Black.otf") or _achar_fonte("Inter-Black.otf")
FONTE_MEDIA = _achar_fonte("InterDisplay-Bold.otf") or _achar_fonte("Inter-Bold.otf") or FONTE_FORTE


def forte(tam):
    return ImageFont.truetype(FONTE_FORTE, tam) if FONTE_FORTE else fonte(tam)


def media(tam):
    return ImageFont.truetype(FONTE_MEDIA, tam) if FONTE_MEDIA else fonte(tam)


def fundo_foto(foto):
    """Fundo com a própria foto do produto desfocada e escurecida (cada vídeo fica com a cor do produto)."""
    base = foto.convert("RGB")
    esc = max(W / base.width, H / base.height)
    b = base.resize((int(base.width * esc) + 2, int(base.height * esc) + 2))
    x, y = (b.width - W) // 2, (b.height - H) // 2
    b = b.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(40))
    # tom escuro arroxeado por cima, mais forte no topo e embaixo (onde ficam os textos do app)
    tom = Image.new("RGB", (W, H), (20, 14, 38))
    mascara = Image.new("L", (1, H))
    for yy in range(H):
        t = abs(yy / H - 0.45) / 0.55
        mascara.putpixel((0, yy), int(255 * (0.62 + 0.30 * min(1, t))))
    b = Image.composite(tom, b, mascara.resize((W, H)))
    return b.convert("RGBA")


def _borda(foto):
    """Pontos da borda da foto (pra saber a cor do fundo)."""
    f = foto.convert("RGB")
    w, h = f.size
    pts = ([(int((w - 1) * i / 40), y) for i in range(41) for y in (1, h - 2)]
           + [(x, int((h - 1) * i / 40)) for i in range(41) for x in (1, w - 2)])
    return [f.getpixel(p) for p in pts]


def _fundo_branco(foto):
    """Foto de estúdio: quase toda a borda é branca (aceita uma marca ou sujeira num canto)."""
    borda = _borda(foto)
    return sum(1 for c in borda if min(c) > 225) >= 0.85 * len(borda)


def cartao(img, foto, caixa, raio=46):
    """Foto num cartão com sombra. Foto com fundo branco: inteira; foto de uso: preenche o cartão."""
    x0, y0, x1, y1 = [int(v) for v in caixa]
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((x0 + 8, y0 + 26, x1 + 8, y1 + 26), raio, fill=(0, 0, 0, 160))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(26)))
    ImageDraw.Draw(img).rounded_rectangle((x0, y0, x1, y1), raio, fill="white")
    w, h = x1 - x0, y1 - y0
    f = foto.convert("RGBA")
    if _fundo_branco(f):
        pad = int(min(w, h) * 0.05)
        f.thumbnail((w - 2 * pad, h - 2 * pad), Image.LANCZOS)
        img.alpha_composite(f, (x0 + (w - f.width) // 2, y0 + (h - f.height) // 2))
    else:
        esc = max(w / f.width, h / f.height)
        f = f.resize((int(f.width * esc) + 1, int(f.height * esc) + 1), Image.LANCZOS)
        fx, fy = (f.width - w) // 2, (f.height - h) // 2
        f = f.crop((fx, fy, fx + w, fy + h))
        masc = Image.new("L", (w, h), 0)
        ImageDraw.Draw(masc).rounded_rectangle((0, 0, w - 1, h - 1), raio, fill=255)
        img.paste(f, (x0, y0), masc)


def pilula(img, texto, cx, cy, fnt, fundo, cor, px=34, py=18, angulo=0):
    """Texto dentro de uma 'pílula' arredondada (estilo texto nativo do TikTok)."""
    d0 = ImageDraw.Draw(img)
    bb = d0.textbbox((0, 0), texto, font=fnt)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    w, h = tw + 2 * px, th + 2 * py
    camada = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    d.rounded_rectangle((20, 20, 20 + w, 20 + h), min(h // 2, 40), fill=fundo)
    d.text((20 + px - bb[0], 20 + py - bb[1]), texto, font=fnt, fill=cor)
    if angulo:
        camada = camada.rotate(angulo, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(camada, (int(cx - camada.width / 2), int(cy - camada.height / 2)))
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def selo(img, texto, cx, cy, r, fundo=VERMELHO, angulo=-10):
    camada = Image.new("RGBA", (2 * r + 20, 2 * r + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    d.ellipse((10, 10, 10 + 2 * r, 10 + 2 * r), fill=fundo, outline="white", width=7)
    fnt = forte(int(r * 0.62))
    bb = d.textbbox((0, 0), texto, font=fnt)
    d.text((10 + r - (bb[2] - bb[0]) / 2 - bb[0], 10 + r - (bb[3] - bb[1]) / 2 - bb[1]), texto,
           font=fnt, fill="white")
    camada = camada.rotate(angulo, resample=Image.BICUBIC, expand=True)
    img.alpha_composite(camada, (int(cx - camada.width / 2), int(cy - camada.height / 2)))


def estrelas(img, nota, cy, r=50, gap=118):
    d = ImageDraw.Draw(img)
    for i in range(5):
        cx = W / 2 + (i - 2) * gap
        estrela(d, cx, cy, r, (95, 88, 110))
        parte = max(0.0, min(1.0, nota - i))
        if parte > 0:
            camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
            estrela(ImageDraw.Draw(camada), cx, cy, r, AMARELO)
            corte = Image.new("L", img.size, 0)
            ImageDraw.Draw(corte).rectangle((cx - r, cy - r, cx - r + 2 * r * parte, cy + r), fill=255)
            img.paste(camada, (0, 0), Image.composite(camada.split()[3], Image.new("L", img.size, 0), corte))


def estrela(d, cx, cy, r, cor):
    import math
    pontos = []
    for i in range(10):
        raio = r if i % 2 == 0 else r * 0.45
        ang = math.pi / 2 + i * math.pi / 5
        pontos.append((cx + raio * math.cos(ang), cy - raio * math.sin(ang)))
    d.polygon(pontos, fill=cor)


def check(d, x, y, tam=64):
    d.ellipse((x, y, x + tam, y + tam), fill=VERDE)
    d.line([(x + tam * 0.26, y + tam * 0.52), (x + tam * 0.44, y + tam * 0.70),
            (x + tam * 0.76, y + tam * 0.32)], fill="white", width=max(6, tam // 9), joint="curve")


def caber(d, texto, fnt, largura):
    if d.textlength(texto, font=fnt) <= largura:
        return texto
    while texto and d.textlength(texto + "…", font=fnt) > largura:
        texto = texto[:-1]
    return texto.rstrip() + "…"


def topo(img, texto):
    pilula(img, texto, W / 2, 262, media(40), (0, 0, 0, 150), "white", px=30, py=14)


CARTAO_GRANDE = (150, 360, 930, 1140)
CARTAO_MEDIO = (270, 340, 810, 880)


def cena_gancho(p, foto, pct):
    img = fundo_foto(foto)
    topo(img, "ACHADO DO DIA")
    cartao(img, foto, CARTAO_GRANDE)
    if pct:
        selo(img, f"-{pct}%", 842, 400, 100)
    return img


def cena_preco(p, foto, pct):
    img = fundo_foto(foto)
    topo(img, "link no perfil  ↗")
    cartao(img, foto, CARTAO_MEDIO)
    if pct:
        selo(img, f"-{pct}%", 790, 372, 84)
    d = ImageDraw.Draw(img)
    fnt = media(62)
    t = f"de {reais(p['preco_cheio'])}"
    tw = d.textlength(t, font=fnt)
    x = (W - tw) / 2
    d.text((x, 940), t, font=fnt, fill=CINZA)
    d.line((x - 10, 978, x + tw + 10, 978), fill=VERMELHO, width=9)
    pilula(img, f"por {reais(p['preco'])}", W / 2, 1118, forte(120), AMARELO, PRETO, px=44, py=26, angulo=3)
    pilula(img, f"preço visto em {dt.date.today():%d/%m}", W / 2, 1268, media(36), (0, 0, 0, 140),
           (230, 225, 240), px=24, py=10)
    return img


def cena_beneficios(foto_fundo, foto, itens, mostrar):
    img = fundo_foto(foto_fundo)
    topo(img, "link no perfil  ↗")
    cartao(img, foto, CARTAO_MEDIO)
    d = ImageDraw.Draw(img)
    fnt = media(48)
    y = 930
    for item in itens[:mostrar]:
        d.rounded_rectangle((130, y, 950, y + 104), 52, fill="white")
        check(d, 152, y + 20, 64)
        d.text((240, y + 52), caber(d, item, fnt, 690), font=fnt, fill=PRETO, anchor="lm")
        y += 128
    return img


def cena_prova(p, foto):
    img = fundo_foto(foto)
    topo(img, "link no perfil  ↗")
    cartao(img, foto, CARTAO_MEDIO)
    d = ImageDraw.Draw(img)
    nota = f"{p['nota']:.1f}".replace(".", ",")
    d.text((W / 2, 975), f"{nota} na Shopee", font=forte(84), fill="white", anchor="mm",
           stroke_width=3, stroke_fill=PRETO)
    estrelas(img, p["nota"], 1085)
    y = 1205
    pilula(img, f"{vendas_texto(p['vendas'])} {METRICA}", W / 2, y, media(46), "white", PRETO)
    if p.get("nacional", True):
        pilula(img, "enviado do Brasil", W / 2, y + 108, media(46), VERDE, "white")
    return img


def cena_cta(foto):
    img = fundo_foto(foto)
    cartao(img, foto, CARTAO_MEDIO)
    pilula(img, "LINK NO PERFIL", W / 2, 1010, forte(96), AMARELO, PRETO, px=46, py=26, angulo=-2)
    pilula(img, "salva pra não perder", W / 2, 1150, media(46), "white", PRETO)
    return img


# ------------------------------------------------------------
# Narração com o tempo de cada palavra (pras legendas)
# ------------------------------------------------------------
VOZES_RESERVA = ["pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"]


def _tempos_estimados(texto, total):
    palavras = texto.split()
    pesos = [len(p) + 2 for p in palavras]
    soma = sum(pesos) or 1
    t, out = 0.05, []
    util = max(0.5, total - 0.15)
    for p, w in zip(palavras, pesos):
        dur = util * w / soma
        out.append((t, t + dur, p))
        t += dur
    return out


def narrar_tempos(texto, destino, voz=None, tom="+0Hz", ritmo=None):
    """Devolve (ok, [(início, fim, palavra), ...]). Tenta a voz escolhida, depois as reservas e o gTTS."""
    import asyncio
    ritmo = ritmo or VELOCIDADE

    async def edge(voz):
        import edge_tts
        try:
            com = edge_tts.Communicate(texto, voz, rate=ritmo, pitch=tom, boundary="WordBoundary")
        except TypeError:
            com = edge_tts.Communicate(texto, voz, rate=ritmo, pitch=tom)
        audio, palavras = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                ini = ch["offset"] / 1e7
                palavras.append((ini, ini + ch["duration"] / 1e7, ch["text"]))
        destino.write_bytes(bytes(audio))
        return palavras

    escolhida = voz or VOZ
    for v_ in [escolhida] + [v for v in VOZES_RESERVA if v != escolhida]:
        try:
            palavras = asyncio.run(edge(v_))
            if destino.exists() and destino.stat().st_size > 1000:
                return True, palavras or _tempos_estimados(texto, duracao(destino))
        except Exception as e:
            print(f"  (voz {v_} falhou: {e})")
    try:
        from gtts import gTTS
        gTTS(texto, lang="pt", tld="com.br").save(str(destino))
        return True, _tempos_estimados(texto, duracao(destino))
    except Exception as e:
        print(f"  (gTTS falhou: {e})")
    return False, []


# ------------------------------------------------------------
# Legendas (ASS) e efeitos sonoros
# ------------------------------------------------------------
def _t_ass(s):
    s = max(0.0, s)
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{sec:05.2f}"


def _palavra_legenda(p):
    p = re.sub(r"[\U0001F000-\U0001FFFF☀-➿]", "", p)
    return p.strip().rstrip(",.;:").upper()


def gerar_ass(cenas_palavras, caminho):
    """Legenda palavra por palavra: blocos de até 3 palavras, a palavra falada fica amarela.
    cenas_palavras = [(fim_da_cena, [(início, fim, palavra), ...]), ...] — nada passa de uma cena pra outra."""
    nome_fonte = "Inter Display Black" if FONTE_FORTE else "DejaVu Sans"
    cab = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: L,{nome_fonte},92,&H00FFFFFF,&H00FFFFFF,&H00101016,&H96000000,0,0,0,0,100,100,0,0,1,"
        "8,4,5,120,120,0,1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    linhas = []
    for fim_cena, palavras in cenas_palavras:
        itens = [(a, b, _palavra_legenda(w)) for a, b, w in palavras if _palavra_legenda(w)]
        blocos, atual = [], []
        for it in itens:
            if atual and (len(atual) >= 3 or len(" ".join(x[2] for x in atual + [it])) > 18):
                blocos.append(atual)
                atual = []
            atual.append(it)
        if atual:
            blocos.append(atual)
        for bi, bloco in enumerate(blocos):
            if bi + 1 < len(blocos):
                fim_bloco = blocos[bi + 1][0][0]
            else:
                fim_bloco = min(fim_cena, bloco[-1][1] + 0.5)
            for k, (ini, fim, _) in enumerate(bloco):
                fim_ev = bloco[k + 1][0] if k + 1 < len(bloco) else fim_bloco
                fim_ev = min(fim_ev, fim_cena)
                if fim_ev <= ini:
                    continue
                partes = [("{\\c&H0AD6FF&}" + w + "{\\c&HFFFFFF&}") if j == k else w
                          for j, (_, _, w) in enumerate(bloco)]
                pop = "{\\fscx82\\fscy82\\t(0,90,\\fscx100\\fscy100)}" if k == 0 else ""
                linhas.append(f"Dialogue: 0,{_t_ass(ini)},{_t_ass(fim_ev)},L,,0,0,0,,"
                              f"{{\\pos(540,{LEGENDA_Y})}}{pop}{' '.join(partes)}")
    caminho.write_text(cab + "\n".join(linhas) + "\n", encoding="utf-8")


def gerar_efeitos(pasta):
    """Sons curtos gerados na hora (sem baixar nada): passagem, plim de preço e pop."""
    sons = {
        "whoosh": "anoisesrc=d=0.38:c=pink:a=0.5,highpass=f=500,lowpass=f=5000,"
                  "afade=t=in:d=0.14,afade=t=out:st=0.16:d=0.22",
        "plim": "aevalsrc='0.42*sin(2*PI*1318*t)*exp(-5*t)+0.32*sin(2*PI*1976*t)*exp(-4*t)':s=44100:d=0.9",
        "pop": "aevalsrc='0.55*sin(2*PI*(500+1800*t)*t)*exp(-28*t)':s=44100:d=0.2",
    }
    caminhos = {}
    for nome, filtro in sons.items():
        arq = pasta / f"sfx_{nome}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", filtro,
                        "-ac", "2", "-ar", "44100", str(arq)], check=True)
        caminhos[nome] = arq
    return caminhos


def montar_video_v2(cenas, falas, tipos, pasta, destino):
    """Cenas com 'pulinho' de zoom, narração, legendas sincronizadas (gancho e final) e efeitos."""
    partes, inicios, palavras_ass, eventos = [], [], [], []
    t0 = 0.0
    for i, (cena, fala, tipo) in enumerate(zip(cenas, falas, tipos)):
        imagens = cena if isinstance(cena, list) else [cena]
        audio = pasta / f"fala{i}.mp3"
        ok, palavras = narrar_tempos(fala, audio)
        seg = (duracao(audio) + 0.30) if ok else max(2.5, len(fala) / 14)
        n = len(imagens)
        quadros = max(1, int(round(seg * 30 / n)))
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for j, im in enumerate(imagens):
            png = pasta / f"cena{i}_{j}.png"
            im.convert("RGB").save(png)
            cmd += ["-i", str(png)]
        if ok:
            cmd += ["-i", str(audio)]
        else:
            cmd += ["-f", "lavfi", "-t", f"{seg:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filtros = []
        for j in range(n):
            z0 = 1.10 if j == 0 else 1.035
            z = f"if(lte(on,7),{z0}-({z0}-1)*on/7,1+0.0004*(on-7))"
            filtros.append(f"[{j}:v]scale=2160:3840,zoompan=z='{z}':d={quadros}"
                           f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,setsar=1[v{j}]")
            if tipo == "beneficios":
                eventos.append((t0 + j * quadros / 30 + 0.02, "pop"))
        filtros.append("".join(f"[v{j}]" for j in range(n)) + f"concat=n={n}:v=1:a=0[v]")
        parte = pasta / f"parte{i}.mp4"
        cmd += ["-filter_complex", ";".join(filtros), "-map", "[v]", "-map", f"{n}:a",
                "-t", f"{seg:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-af", "apad", str(parte)]
        subprocess.run(cmd, check=True)
        partes.append(parte)
        inicios.append(t0)
        fim_cena = t0 + n * quadros / 30
        if tipo in ("gancho", "cta"):
            palavras_ass.append((fim_cena - 0.05, [(t0 + a, t0 + b, w) for a, b, w in palavras]))
        if i > 0:
            eventos.append((max(0.0, t0 - 0.12), "whoosh"))
        if tipo == "preco":
            eventos.append((t0 + 0.30, "plim"))
        t0 += n * quadros / 30

    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{p.name}'\n" for p in partes))
    base = pasta / "base.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c", "copy", str(base)], check=True)

    ass = pasta / "legendas.ass"
    gerar_ass(palavras_ass, ass)
    sons = gerar_efeitos(pasta)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(base)]
    for _, nome in eventos:
        cmd += ["-i", str(sons[nome])]
    fontes = f":fontsdir={Path(FONTE_FORTE).parent}" if FONTE_FORTE else ""
    filtro = [f"[0:v]ass={ass.name}{fontes}[v]"]
    mix = ["[0:a]"]
    for k, (t, nome) in enumerate(eventos, start=1):
        ms = int(t * 1000)
        vol = 0.35 if nome == "whoosh" else 0.5
        filtro.append(f"[{k}:a]adelay={ms}|{ms},volume={vol}[s{k}]")
        mix.append(f"[s{k}]")
    filtro.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0[a]")
    cmd += ["-filter_complex", ";".join(filtro), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(Path(destino).resolve())]
    subprocess.run(cmd, check=True, cwd=str(pasta))


# ------------------------------------------------------------
# Formato "conversa": o Lupi (mascote) conversa com uma amiga sobre o achado.
# O Lupi fica no canto de baixo, a boca mexe junto com a voz dele, e a fala
# aparece num balão. As cenas de fundo (foto, preço, estrelas) vêm do design v2.
# ------------------------------------------------------------
VOZ_LUPI = "pt-BR-AntonioNeural"
TOM_LUPI = "+28Hz"          # voz mais aguda, de personagem
VOZ_AMIGA = "pt-BR-FranciscaNeural"
TOM_AMIGA = "+0Hz"
FAIXA_Y = 1040              # onde começa a faixa do Lupi e dos balões (até 1600)
FAIXA_H = 560

# --- desenho do Lupi (personagem original) ---
_AA = 4
_LL, _LA = 700, 800
_CONTORNO, _ARO, _ARO_CLARO = (22, 34, 64), (0, 196, 176), (120, 235, 220)
_VIDRO, _CABO, _CABO_CLARO = (236, 250, 255), (104, 66, 214), (150, 118, 245)
_METAL, _TENIS, _SOLA = (205, 210, 228), (255, 214, 10), (255, 255, 255)
_BOCHECHA, _BOCA, _LINGUA = (255, 140, 170, 170), (110, 24, 52), (255, 112, 136)


def _m(v):
    return [int(x * _AA) for x in v] if isinstance(v, (list, tuple)) else int(v * _AA)


def _oval(d, cx, cy, rx, ry, **kw):
    d.ellipse(_m((cx - rx, cy - ry, cx + rx, cy + ry)), **kw)


def _traco(d, pts, cor, larg):
    d.line([(_m(x), _m(y)) for x, y in pts], fill=cor, width=_m(larg), joint="curve")
    for x, y in (pts[0], pts[-1]):
        _oval(d, x, y, larg / 2, larg / 2, fill=cor)


def _braco(d, ombro, mao, cotovelo):
    pts = [ombro, cotovelo, mao]
    _traco(d, pts, _CONTORNO, 30)
    _traco(d, pts, _ARO, 18)
    _oval(d, *mao, 30, 30, fill=_CONTORNO)
    _oval(d, *mao, 23, 23, fill=_ARO)


def desenhar_lupi(altura=520, boca="sorriso", olhos="abertos", pose="normal"):
    img = Image.new("RGBA", (_LL * _AA, _LA * _AA), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, R = 350, 270, 205
    _traco(d, [(cx, cy + R - 10), (cx, 690)], _CONTORNO, 92)
    _traco(d, [(cx, cy + R - 10), (cx, 690)], _CABO, 78)
    _traco(d, [(cx - 18, cy + R + 30), (cx - 18, 670)], _CABO_CLARO, 14)
    for dx in (-58, 58):
        d.rounded_rectangle(_m((cx + dx - 58, 722, cx + dx + 58, 756)), radius=_m(16), fill=_CONTORNO)
        d.rounded_rectangle(_m((cx + dx - 52, 728, cx + dx + 52, 750)), radius=_m(11), fill=_SOLA)
        d.pieslice(_m((cx + dx - 58, 672, cx + dx + 58, 772)), 180, 360, fill=_CONTORNO)
        d.pieslice(_m((cx + dx - 51, 679, cx + dx + 51, 765)), 180, 360, fill=_TENIS)
    d.rounded_rectangle(_m((cx - 58, cy + R - 30, cx + 58, cy + R + 22)), radius=_m(14),
                        fill=_METAL, outline=_CONTORNO, width=_m(6))
    if pose == "aponta":
        _braco(d, (cx + R - 30, cy + 40), (cx + R + 70, cy - 150), (cx + R + 70, cy - 20))
        _oval(d, cx + R + 80, cy - 182, 11, 26, fill=_CONTORNO)
        _oval(d, cx + R + 80, cy - 182, 6, 21, fill=_ARO)
    else:
        _braco(d, (cx + R - 30, cy + 40), (cx + R + 60, cy - 70), (cx + R + 75, cy + 30))
    _braco(d, (cx - R + 30, cy + 60), (cx - R - 30, cy + 190), (cx - R - 50, cy + 110))
    _oval(d, cx, cy, R + 6, R + 6, fill=_CONTORNO)
    _oval(d, cx, cy, R, R, fill=_ARO)
    _oval(d, cx, cy, R - 34, R - 34, fill=_CONTORNO)
    _oval(d, cx, cy, R - 40, R - 40, fill=_VIDRO)
    d.arc(_m((cx - R + 10, cy - R + 10, cx + R - 10, cy + R - 10)), 200, 250, fill=_ARO_CLARO, width=_m(12))
    d.arc(_m((cx - R + 62, cy - R + 62, cx + R - 62, cy + R - 62)), 205, 245, fill=(255, 255, 255), width=_m(16))
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(camada)
    _oval(dc, cx - 105, cy + 62, 30, 17, fill=_BOCHECHA)
    _oval(dc, cx + 105, cy + 62, 30, 17, fill=_BOCHECHA)
    img.alpha_composite(camada)
    for ex in (cx - 62, cx + 62):
        if olhos == "fechados":
            d.arc(_m((ex - 32, cy - 40, ex + 32, cy + 10)), 200, 340, fill=_CONTORNO, width=_m(9))
        else:
            _oval(d, ex, cy - 22, 36, 44, fill=_CONTORNO)
            _oval(d, ex, cy - 22, 30, 38, fill="white")
            _oval(d, ex + 4, cy - 14, 18, 20, fill=_CONTORNO)
            _oval(d, ex - 2, cy - 22, 7, 7, fill="white")
        d.arc(_m((ex - 30, cy - 105, ex + 30, cy - 55)), 205, 335, fill=_CONTORNO, width=_m(10))
    mx, my = cx, cy + 70
    if boca == "sorriso":
        d.arc(_m((mx - 42, my - 34, mx + 42, my + 22)), 20, 160, fill=_CONTORNO, width=_m(10))
    else:
        rx, ry = (34, 20) if boca == "meia" else (44, 36)
        d.chord(_m((mx - rx, my - ry, mx + rx, my + ry * 1.6)), 0, 180, fill=_CONTORNO)
        d.chord(_m((mx - rx + 6, my - ry + 6, mx + rx - 6, my + ry * 1.6 - 6)), 0, 180, fill=_BOCA)
        _oval(d, mx, my + ry * 0.95, rx * 0.55, ry * 0.42, fill=_LINGUA)
    img = img.resize((_LL, _LA), Image.LANCZOS)
    return img.resize((int(_LL * altura / _LA), altura), Image.LANCZOS)


# --- roteiro da conversa ---
def roteiro_conversa(p, ia, palavra, rnd):
    """Lista de (cena, quem, fala). quem = 'lupi' ou 'amiga'."""
    pct = round(p["desconto"] * 100)
    nome = (ia.get("nome_curto") or palavra).strip()
    nota = f"{p['nota']:.1f}".replace(".", ",")
    gancho = ia.get("gancho") or rnd.choice(["Achei um achadinho que você precisa ver!",
                                             "Para tudo, olha o que eu achei!"])
    pergunta = ia.get("pergunta_amiga") or rnd.choice(["Lupi, achou alguma coisa boa hoje?",
                                                       "E aí, Lupi, qual é o achado de hoje?"])
    resposta = gancho if ia.get("pergunta_amiga") else rnd.choice(["Achei! Olha só isso!",
                                                                   "Achei sim, e tá com desconto!"])
    falas = [
        ("gancho", "amiga", pergunta),
        ("gancho", "lupi", resposta),
        ("preco", "lupi", f"{nome[0].upper() + nome[1:]}, de {reais_falado(p['preco_cheio'])} "
                          f"por {reais_falado(p['preco'])} na Shopee!"),
        ("preco", "amiga", rnd.choice([f"Sério? {pct} por cento de desconto?", f"Nossa, {pct} por cento mais barato!"])),
    ]
    if ia.get("fala_beneficios"):
        falas.append(("beneficios", "lupi", ia["fala_beneficios"]))
    if p["nota"] >= 1:
        envio = ", e é enviado do Brasil" if p.get("nacional", True) else ""
        falas += [("prova", "amiga", rnd.choice(["E é bom mesmo?", "Mas presta?"])),
                  ("prova", "lupi", f"Nota {nota} na Shopee, com {vendas_texto(p['vendas'])} {METRICA}{envio}!")]
    falas += [("cta", "amiga", rnd.choice(["Onde eu compro?", "Me passa o link!"])),
              ("cta", "lupi", "O link tá no meu perfil! Corre, que o preço pode mudar a qualquer momento!")]
    return falas


# --- cenas de fundo (o Lupi e os balões entram por cima, na faixa de baixo) ---
CARTAO_CONVERSA = (300, 330, 780, 810)


def fundo_conversa(tipo, p, f1, f2, ia):
    pct = round(p["desconto"] * 100)
    img = fundo_foto(f1)
    topo(img, "ACHADO DO DIA" if tipo == "gancho" else "link no perfil  ↗")
    cartao(img, f2 if tipo == "beneficios" else f1, CARTAO_CONVERSA)
    d = ImageDraw.Draw(img)
    if tipo in ("gancho", "preco") and pct:
        selo(img, f"-{pct}%", 770, 360, 84)
    if tipo == "preco":
        fnt = media(54)
        t = f"de {reais(p['preco_cheio'])}"
        tw = d.textlength(t, font=fnt)
        x = (W - tw) / 2
        d.text((x, 826), t, font=fnt, fill=CINZA)
        d.line((x - 10, 859, x + tw + 10, 859), fill=VERMELHO, width=8)
        pilula(img, f"por {reais(p['preco'])}", W / 2, 975, forte(100), AMARELO, PRETO, px=40, py=20, angulo=3)
    elif tipo == "beneficios":
        y = 838
        for item in ia.get("beneficios", [])[:3]:
            d.rounded_rectangle((170, y, 910, y + 62), 31, fill="white")
            check(d, 184, y + 8, 46)
            d.text((246, y + 31), caber(d, item, media(36), 640), font=media(36), fill=PRETO, anchor="lm")
            y += 70
    elif tipo == "prova":
        nota = f"{p['nota']:.1f}".replace(".", ",")
        d.text((W / 2, 868), f"{nota} na Shopee", font=forte(64), fill="white", anchor="mm",
               stroke_width=3, stroke_fill=PRETO)
        estrelas(img, p["nota"], 960, r=40, gap=96)
    elif tipo == "cta":
        pilula(img, "LINK NO PERFIL", W / 2, 940, forte(92), AMARELO, PRETO, px=44, py=24, angulo=-2)
    return img


# --- balões de fala ---
BALAO = (440, 40, 975, 380)       # dentro da faixa (x0, y0, x1, y1)


def _paginas(palavras, fnt, largura, max_linhas=3):
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    paginas, linhas, atual = [], [], []
    for i, w in enumerate(palavras):
        if atual and d.textlength(" ".join(palavras[j] for j in atual + [i]), font=fnt) > largura:
            linhas.append(atual)
            atual = []
            if len(linhas) == max_linhas:
                paginas.append(linhas)
                linhas = []
        atual.append(i)
    if atual:
        linhas.append(atual)
    if linhas:
        paginas.append(linhas)
    return paginas


def desenhar_balao(quem, palavras, pagina, ativo):
    img = Image.new("RGBA", (W, FAIXA_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = BALAO
    fundo, borda = ((255, 255, 255), PRETO) if quem == "lupi" else ((255, 222, 234), PRETO)
    d.rounded_rectangle(BALAO, 42, fill=fundo, outline=borda, width=6)
    if quem == "lupi":      # rabinho apontando pro Lupi
        d.polygon([(x0 + 6, y1 - 110), (x0 - 70, y1 - 30), (x0 + 30, y1 - 52)], fill=fundo)
        d.line([(x0 + 2, y1 - 112), (x0 - 70, y1 - 30), (x0 + 34, y1 - 50)], fill=borda, width=6)
    else:                   # a amiga está "fora da tela", à direita
        pilula(img, "AMIGA", x1 - 110, y0 - 2, media(30), (233, 64, 120), "white", px=18, py=8)
    fnt = forte(60)
    linhas = pagina
    y = (y0 + y1) / 2 - len(linhas) * 37
    for ln in linhas:
        texto = " ".join(palavras[i] for i in ln)
        x = (x0 + x1) / 2 - d.textlength(texto, font=fnt) / 2
        for i in ln:
            cor = LARANJA if i == ativo else PRETO
            d.text((x, y), palavras[i], font=fnt, fill=cor)
            x += d.textlength(palavras[i] + " ", font=fnt)
        y += 74
    return img


# --- volume da voz quadro a quadro (pra mexer a boca) ---
def volume_por_quadro(audio, fps=30):
    import numpy as np
    bruto = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-f", "s16le", "-ac", "1",
                            "-ar", "16000", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(bruto, dtype=np.int16).astype("float32")
    passo = 16000 // fps
    n = max(1, len(x) // passo)
    v = np.array([np.sqrt(np.mean(x[i * passo:(i + 1) * passo] ** 2) + 1e-6) for i in range(n)])
    return (v / (v.max() or 1)).tolist()


def montar_video_conversa(linhas_roteiro, fundos, pasta, destino):
    """linhas_roteiro: [(cena, quem, fala)]; fundos: {cena: imagem}."""
    fps = 30
    linhas = []
    t = 0.25
    for k, (cena, quem, fala) in enumerate(linhas_roteiro):
        audio = pasta / f"fala{k}.mp3"
        voz, tom = (VOZ_LUPI, TOM_LUPI) if quem == "lupi" else (VOZ_AMIGA, TOM_AMIGA)
        ok, pals = narrar_tempos(fala, audio, voz=voz, tom=tom)
        dur = duracao(audio) if ok else max(1.5, len(fala) / 14)
        vol = volume_por_quadro(audio, fps) if ok else []
        palavras = [_palavra_legenda(w) for w in fala.split()]
        palavras = [w for w in palavras if w]
        # tempos por palavra (do texto escrito) — usa os da voz quando batem, senão estima
        tempos = ([(a, b) for a, b, _ in pals] if len(pals) == len(palavras)
                  else [(a, b) for a, b, _ in _tempos_estimados(" ".join(palavras), dur)])
        linhas.append({"cena": cena, "quem": quem, "fala": fala, "audio": audio if ok else None,
                       "ini": t, "dur": dur, "vol": vol, "palavras": palavras, "tempos": tempos,
                       "paginas": _paginas(palavras, forte(60), BALAO[2] - BALAO[0] - 60)})
        t += dur + 0.18
    total = t + 0.4

    # cenas de fundo: blocos seguidos com a mesma cena
    blocos = []
    for ln in linhas:
        if blocos and blocos[-1]["cena"] == ln["cena"]:
            blocos[-1]["fim"] = ln["ini"] + ln["dur"] + 0.18
        else:
            blocos.append({"cena": ln["cena"], "ini": ln["ini"] if blocos else 0.0,
                           "fim": ln["ini"] + ln["dur"] + 0.18})
    blocos[-1]["fim"] = total
    for a, b in zip(blocos, blocos[1:]):
        b["ini"] = a["fim"]

    partes = []
    for i, bl in enumerate(blocos):
        png = pasta / f"fundo{i}.png"
        fundos[bl["cena"]].convert("RGB").save(png)
        quadros = max(1, int(round((bl["fim"] - bl["ini"]) * fps)))
        z = "if(lte(on,7),1.08-0.08*on/7,1+0.0003*(on-7))"
        parte = pasta / f"bloco{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-vf",
                        f"scale=2160:3840,zoompan=z='{z}':d={quadros}:x='iw/2-(iw/zoom/2)'"
                        f":y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps},setsar=1",
                        "-frames:v", str(quadros), "-c:v", "libx264", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-an", str(parte)], check=True)
        partes.append(parte)
    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{p.name}'\n" for p in partes))
    base = pasta / "base.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lista), "-c", "copy", str(base)], check=True)
    n_quadros = sum(int(round((bl["fim"] - bl["ini"]) * fps)) for bl in blocos)

    # áudio: falas no tempo certo + efeitos
    sons = gerar_efeitos(pasta)
    entradas, filtros, mix = [], [], []
    for ln in linhas:
        if ln["audio"]:
            entradas.append(ln["audio"])
            ms = int(ln["ini"] * 1000)
            filtros.append(f"[{len(entradas) - 1}:a]adelay={ms}|{ms}[a{len(entradas) - 1}]")
            mix.append(f"[a{len(entradas) - 1}]")
    for i, bl in enumerate(blocos):
        eventos = []
        if i > 0:
            eventos.append((bl["ini"] - 0.1, "whoosh", 0.3))
        if bl["cena"] == "preco":
            eventos.append((bl["ini"] + 0.35, "plim", 0.45))
        for tt, nome, vol in eventos:
            entradas.append(sons[nome])
            ms = int(max(0, tt) * 1000)
            k = len(entradas) - 1
            filtros.append(f"[{k}:a]adelay={ms}|{ms},volume={vol}[a{k}]")
            mix.append(f"[a{k}]")
    audio_final = pasta / "audio.wav"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for e in entradas:
        cmd += ["-i", str(e)]
    if not entradas:
        cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filtros, mix = ["[0:a]anull[a0]"], ["[a0]"]
    filtros.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0,apad[out]")
    cmd += ["-filter_complex", ";".join(filtros), "-map", "[out]", "-t", f"{n_quadros / fps:.3f}",
            "-ar", "44100", "-ac", "2", str(audio_final)]
    subprocess.run(cmd, check=True)

    # faixa animada (Lupi + balões) gerada quadro a quadro e enviada direto pro ffmpeg
    sprites = {}

    def sprite(boca, olhos, pose):
        chave = (boca, olhos, pose)
        if chave not in sprites:
            sprites[chave] = desenhar_lupi(500, boca, olhos, pose)
        return sprites[chave]

    baloes = {}
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(base),
         "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{FAIXA_H}", "-r", str(fps), "-i", "-",
         "-i", str(audio_final),
         "-filter_complex", f"[0:v][1:v]overlay=0:{FAIXA_Y}:format=auto[v]",
         "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
         "-movflags", "+faststart", str(Path(destino).resolve())],
        stdin=subprocess.PIPE)
    import math
    for q in range(n_quadros):
        tt = q / fps
        atual = None
        for ln in linhas:
            if ln["ini"] - 0.05 <= tt <= ln["ini"] + ln["dur"] + 0.18:
                atual = ln
        quadro = Image.new("RGBA", (W, FAIXA_H), (0, 0, 0, 0))
        falando = atual is not None and atual["quem"] == "lupi"
        boca = "sorriso"
        if falando and atual["vol"]:
            i = int((tt - atual["ini"]) * fps)
            v = atual["vol"][i] if 0 <= i < len(atual["vol"]) else 0
            boca = "aberta" if v > 0.55 else ("meia" if v > 0.22 else "sorriso")
        olhos = "fechados" if (q % 96) in (0, 1, 2, 3) else "abertos"
        pose = "aponta" if atual is not None and atual["cena"] == "cta" else "normal"
        pulo = abs(math.sin(tt * 7)) * 12 if falando else 4 * math.sin(tt * 2)
        lupi = sprite(boca, olhos, pose)
        quadro.alpha_composite(lupi, (-25, int(FAIXA_H - lupi.height - 20 - pulo)))
        if atual is not None:
            ativo = 0
            for k, (a, b) in enumerate(atual["tempos"]):
                if tt - atual["ini"] >= a:
                    ativo = k
            pag = 0
            for k, pg in enumerate(atual["paginas"]):
                if any(ativo in ln for ln in pg):
                    pag = k
            chave = (id(atual), pag, ativo)
            if chave not in baloes:
                baloes.clear()
                baloes[chave] = desenhar_balao(atual["quem"], atual["palavras"], atual["paginas"][pag], ativo)
            quadro.alpha_composite(baloes[chave])
        proc.stdin.write(quadro.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg falhou ao montar a conversa")


def fazer_conversa(produtos, palavra, hist, pasta_dia, rnd, usar_feed, sub):
    p = escolher_promo(produtos, hist)
    if not p:
        return None
    link = obter_link(p, usar_feed, sub)
    ia = roteiro_ia(p)
    print(f"  produto: {p['nome'][:70]} | IA: {'sim' if ia else 'não (texto padrão)'}")
    nome = nome_promo(p, ia, palavra)
    pct = round(p["desconto"] * 100)
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento(palavra).lower()).strip("-")
    pasta = pasta_dia / slug
    pasta.mkdir(exist_ok=True)
    f1 = baixar_foto(p["imagem"], pasta / "foto1.jpg")
    f2 = f1
    if p.get("imagem2"):
        try:
            f2 = baixar_foto(p["imagem2"], pasta / "foto2.jpg")
        except Exception:
            f2 = f1
    roteiro = roteiro_conversa(p, ia, palavra, rnd)
    fundos = {c: fundo_conversa(c, p, f1, f2, ia) for c in {c for c, _, _ in roteiro}}
    video = pasta_dia / f"{slug}.mp4"
    montar_video_conversa(roteiro, fundos, pasta, video)
    dialogo = "\n".join(f"{'Lupi' if q == 'lupi' else 'Amiga'}: {f}" for _, q, f in roteiro)
    resumo = (f"🎬 {nome} — pronto pra postar\n"
              f"De {reais(p['preco_cheio'])} por {reais(p['preco'])} (-{pct}%)\n"
              + aviso_link(link, usar_feed) + f"\n{dialogo}")
    return {"titulo": nome, "video": video, "resumo": resumo,
            "legenda": legenda_promo(p, ia, palavra), "ia": bool(ia),
            "canal": canal_promo(p, ia, palavra, link),
            "whatsapp": whatsapp_promo(p, ia, palavra, link),
            "foto_canal": p["imagem"], "ids": [p["id"]],
            "registro": oferta_registro_promo(p, ia, palavra, link)}


# ------------------------------------------------------------
# Formato "tela verde": o produto em tela cheia, trocando de enquadramento a cada 2–3 s,
# e o Lupi no canto apresentando (como os afiliados que gravam com o efeito Tela Verde).
# A amiga abre com a pergunta; o resto o Lupi fala sozinho, mais rápido.
# Roteiro curto (uns 15 s): dor -> o que é e o que resolve -> preço -> nota -> chamada.
# Cada quadro é desenhado aqui no Python e vai direto pro ffmpeg.
# ------------------------------------------------------------
TV_TEXTO_Y = 300            # topo dos textos de cima (pergunta, nome, preço, usos, nota, chamada)
TV_LUPI_ALTURA = 440        # o Lupi fica embaixo à esquerda (o lado direito tem os botões do app)
TV_LUPI_PE = 1600           # onde ficam os pés do Lupi
TV_LEGENDA = (690, 1425)    # centro da legenda, ao lado do Lupi
TV_LEGENDA_LARG = 520
TV_PLANO = 2.4              # duração média de cada enquadramento (segundos)
TV_MOVIMENTOS = ["detalhe", "panorama", "sobe", "panorama2", "detalhe2"]
# cenários coloridos (cor de cima, cor de baixo) pro produto recortado do fundo branco
TV_CORES = [((244, 239, 255), (212, 200, 250)),     # lilás
            ((233, 251, 246), (190, 236, 224)),     # menta
            ((255, 244, 233), (255, 214, 190))]     # pêssego


def roteiro_tela_verde(p, ia, palavra, rnd):
    """Falas do vídeo: [{'secao', 'quem', 'fala'}]. O Lupi não diz que usou nem que comprou
    (seria depoimento falso): fala só do que o anúncio mostra."""
    nome = (ia.get("nome_curto") or palavra).strip()
    nome = nome[0].upper() + nome[1:]
    nota = f"{p['nota']:.1f}".replace(".", ",")
    tem_ia = bool(ia.get("pergunta_amiga") and ia.get("como_funciona"))
    pergunta = ia["pergunta_amiga"] if tem_ia else rnd.choice([
        "Lupi, achou alguma coisa boa hoje?", "E aí, Lupi, qual é o achado de hoje?"])
    if len(pergunta.split()) > 11 and ia.get("gancho", "").endswith("?"):
        pergunta = ia["gancho"]                   # a pergunta veio comprida: o gancho é mais curto
    apresenta = ia["como_funciona"] if tem_ia else rnd.choice([
        f"Achei! Olha só: {nome}.", f"Achei sim! Olha isso: {nome}."])
    if len(apresenta.split()) > 18:               # veio comprida: fica só a 1ª frase, se ela for curta
        primeira = re.split(r"(?<=[.!?])\s+", apresenta)[0]
        apresenta = primeira if len(primeira.split()) <= 18 else f"Olha só: {nome}."
    falas = [
        {"secao": "gancho", "quem": "amiga", "fala": pergunta},
        {"secao": "produto", "quem": "lupi", "fala": apresenta},
        {"secao": "preco", "quem": "lupi",
         "fala": f"De {reais_curto(p['preco_cheio'])} por {reais_curto(p['preco'])} na Shopee!"},
    ]
    if p["nota"] >= 1:     # na fala só a nota e as vendas; "enviado do Brasil" fica escrito na tela
        prova = f"Nota {nota}"
        prova += f" e {vendas_texto(p['vendas'])} {METRICA}!" if p["vendas"] >= 100 else " na Shopee!"
        falas.append({"secao": "prova", "quem": "lupi", "fala": prova})
    falas.append({"secao": "cta", "quem": "lupi",
                  "fala": "Link no meu perfil. Confere o preço de hoje, que ele pode mudar!"})
    return falas


def _na_largura(img):
    """A foto (ou o recorte) na largura toda da tela; foto em pé usa só o meio. Devolve (imagem, y do topo)."""
    alt = int(img.height * W / img.width)
    img = img.resize((W, alt), Image.LANCZOS)
    if alt > 1320:
        y = (alt - 1320) // 2
        img = img.crop((0, y, W, y + 1320))
        alt = 1320
    return img, max(220, 820 - alt // 2)


def _borda_suave(tam, margem):
    """Máscara que some suavemente nas bordas (esconde emenda e sujeirinha na beira da foto)."""
    m = Image.new("L", tam, 0)
    ImageDraw.Draw(m).rectangle((margem, margem, tam[0] - 1 - margem, tam[1] - 1 - margem), fill=255)
    return m.filter(ImageFilter.GaussianBlur(margem / 2))


def _tela_cheia(foto):
    """Fundo de um plano: a foto na largura toda. Foto de estúdio (fundo branco): a tela inteira fica
    da cor do fundo dela, como se o produto estivesse solto na tela. Foto de uso: ela mesma desfocada atrás.
    Devolve (imagem, altura do centro da foto)."""
    f = foto.convert("RGB")
    branco = _fundo_branco(f)
    if branco:
        claros = [c for c in _borda(f) if min(c) > 225]
        img = Image.new("RGB", (W, H), tuple(sum(c[i] for c in claros) // len(claros) for i in range(3)))
    else:
        img = fundo_foto(foto).convert("RGB")
    f, y0 = _na_largura(f)
    img.paste(f, (0, y0), _borda_suave(f.size, 26) if branco else None)
    return img, y0 + f.height // 2


def _recortar(foto):
    """Tira o fundo branco de uma foto de estúdio (só o branco que encosta na borda, então o branco
    de dentro do produto fica). Devolve a foto RGBA, ou None quando o recorte não é confiável."""
    from PIL import ImageChops
    f = foto.convert("RGB")
    peq = f.copy()
    peq.thumbnail((540, 540))
    r, g, b = peq.split()
    menor = ImageChops.darker(ImageChops.darker(r, g), b)
    maior = ImageChops.lighter(ImageChops.lighter(r, g), b)
    claro = menor.point(lambda v: 255 if v >= 226 else 0)
    cinza = ImageChops.subtract(maior, menor).point(lambda v: 255 if v <= 24 else 0)
    m = ImageChops.multiply(claro, cinza)
    w, h = m.size
    for i in range(0, w, 6):
        for xy in ((i, 0), (i, h - 1)):
            if m.getpixel(xy) == 255:
                ImageDraw.floodfill(m, xy, 128)
    for j in range(0, h, 6):
        for xy in ((0, j), (w - 1, j)):
            if m.getpixel(xy) == 255:
                ImageDraw.floodfill(m, xy, 128)
    fundo = m.point(lambda v: 255 if v == 128 else 0)
    parte = sum(fundo.histogram()[255:]) / (w * h)
    if not 0.18 <= parte <= 0.88:
        return None
    alfa = ImageChops.invert(fundo).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    alfa = ImageChops.multiply(alfa, _borda_suave(alfa.size, max(4, w // 40)))
    rec = f.convert("RGBA")
    rec.putalpha(alfa.resize(f.size, Image.BILINEAR))
    return rec


def _cenario(recorte, cores):
    """Produto recortado num fundo colorido (degradê suave) com sombrinha embaixo."""
    topo_c, base_c = cores
    faixa = Image.new("RGB", (1, H))
    for y in range(H):
        u = y / (H - 1)
        faixa.putpixel((0, y), tuple(int(topo_c[i] + (base_c[i] - topo_c[i]) * u) for i in range(3)))
    img = faixa.resize((W, H)).convert("RGBA")
    rec, y0 = _na_largura(recorte)
    caixa = rec.getchannel("A").getbbox()
    if caixa:
        x0, _, x1, y1 = caixa
        sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sombra).ellipse((x0 + (x1 - x0) * 0.1, y0 + y1 - 24, x1 - (x1 - x0) * 0.1, y0 + y1 + 30),
                                       fill=(40, 20, 60, 70))
        img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(22)))
    img.alpha_composite(rec, (0, y0))
    return img.convert("RGB"), y0 + rec.height // 2


def _foto_limpa(foto):
    """Nota de 'limpeza' da foto: foto de estúdio que dá pra recortar ganha; montagem cheia de texto perde."""
    g = foto.convert("L")
    g.thumbnail((256, 256))
    bordas = g.filter(ImageFilter.FIND_EDGES)
    poluicao = sum(i * n for i, n in enumerate(bordas.histogram())) / (255 * bordas.width * bordas.height)
    nota = -10 * poluicao
    if _fundo_branco(foto):
        nota += 1 + (1 if _recortar(foto) is not None else 0)
    return nota


def _cenarios(foto, rnd):
    """Os 'cenários' de uma foto: ela mesma e, se for de estúdio e o recorte der certo, 2 fundos coloridos."""
    lista = [_tela_cheia(foto)]
    if _fundo_branco(foto):
        rec = _recortar(foto)
        if rec is not None:
            lista += [_cenario(rec, cores) for cores in rnd.sample(TV_CORES, 2)]
    return lista


def _camera(tipo, u, cy):
    """(zoom, centro x, centro y) do enquadramento no instante u (0 a 1) do plano; cy = centro da foto."""
    if tipo == "abre":                   # começa perto do produto e vai chegando mais
        return 1.10 + 0.16 * u, 540, 960 + (cy - 960) * (0.5 + 0.5 * u)
    if tipo == "detalhe":
        return 1.30 + 0.12 * u, 540, cy
    if tipo == "detalhe2":
        return 1.48 - 0.14 * u, 540, cy + 30
    if tipo == "panorama":
        return 1.32, 455 + 170 * u, cy
    if tipo == "panorama2":
        return 1.32, 625 - 170 * u, cy
    if tipo == "sobe":
        return 1.26, 540, cy + 90 - 180 * u
    return 1.24 - 0.20 * u, 540, cy + (960 - cy) * u     # "fecha": último plano, vai se afastando


def _enquadrar(fundo, z, cx, cy):
    z = max(1.0, z)
    vw, vh = W / z, H / z
    cx = min(max(cx, vw / 2), W - vw / 2)
    cy = min(max(cy, vh / 2), H - vh / 2)
    return fundo.transform((W, H), Image.AFFINE, (1 / z, 0, cx - vw / 2, 0, 1 / z, cy - vh / 2),
                           resample=Image.BILINEAR)


def _pop(img, f, n=5, de=0.7):
    """Entrada com 'pulinho': cresce de 70% até 100% (passando um pouco) em n quadros."""
    if f >= n:
        return img
    u = (max(0, f) + 1) / n
    esc = de + (1 - de) * u + 0.08 * math.sin(math.pi * u)
    return img.resize((max(1, int(img.width * esc)), max(1, int(img.height * esc))), Image.BILINEAR)


def _colar(quadro, img, cx, cy, f=99):
    """Cola a camada centrada em (cx, cy), com o pulinho de entrada nos primeiros quadros."""
    im = _pop(img, f)
    quadro.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def _cartao_pergunta(palavras, ativo):
    """A pergunta da amiga em cima, com a palavra falada em laranja."""
    fnt = forte(64)
    d0 = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    linhas, atual = [], []
    for i, w in enumerate(palavras):
        if atual and d0.textlength(" ".join(palavras[j] for j in atual + [i]), font=fnt) > 840:
            linhas.append(atual)
            atual = []
        atual.append(i)
    if atual:
        linhas.append(atual)
    linhas = linhas[:4]
    alt = 56 + len(linhas) * 78
    img = Image.new("RGBA", (W, alt + 70), (0, 0, 0, 0))
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((70, 40, W - 70, 40 + alt), 40, fill=(0, 0, 0, 120))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((70, 30, W - 70, 30 + alt), 40, fill=(255, 236, 244), outline=PRETO, width=6)
    pilula(img, "AMIGA", 180, 30, media(30), (233, 64, 120), "white", px=18, py=8)
    y = 30 + 30
    for ln in linhas:
        texto = " ".join(palavras[i] for i in ln)
        x = W / 2 - d.textlength(texto, font=fnt) / 2
        for i in ln:
            d.text((x, y), palavras[i], font=fnt, fill=LARANJA if i == ativo else PRETO)
            x += d.textlength(palavras[i] + " ", font=fnt)
        y += 78
    return img


def _cartao_nome(nome):
    img = Image.new("RGBA", (W, 250), (0, 0, 0, 0))
    pilula(img, "ACHADO DO DIA", W / 2, 44, media(34), (233, 64, 120), "white", px=22, py=10)
    d = ImageDraw.Draw(img)
    tam = 72
    while tam > 44 and d.textlength(nome, font=forte(tam)) > 860:
        tam -= 4
    pilula(img, caber(d, nome, forte(tam), 860), W / 2, 150, forte(tam), PRETO, "white", px=40, py=22, angulo=-2)
    return img


def _cartao_preco(p, pct):
    img = Image.new("RGBA", (W, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    t = f"de {reais(p['preco_cheio'])}"
    fnt = media(50)
    pilula(img, t, W / 2, 50, fnt, (0, 0, 0, 175), CINZA, px=28, py=12)
    tw = d.textlength(t, font=fnt)
    d.line((W / 2 - tw / 2 - 6, 54, W / 2 + tw / 2 + 6, 54), fill=VERMELHO, width=8)
    pilula(img, f"por {reais(p['preco'])}", W / 2, 185, forte(108), AMARELO, PRETO, px=46, py=26, angulo=3)
    if pct:
        selo(img, f"-{pct}%", 912, 92, 74)
    pilula(img, f"preço visto em {dt.date.today():%d/%m}", W / 2, 330, media(32), (0, 0, 0, 160),
           (235, 230, 245), px=20, py=9)
    return img


def _cartao_cta():
    img = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    pilula(img, "LINK NO PERFIL  ↗", W / 2, 90, forte(92), AMARELO, PRETO, px=46, py=26, angulo=-2)
    pilula(img, "confere o preço de hoje", W / 2, 228, media(46), PRETO, "white", px=30, py=14)
    return img


def _etiqueta(texto, estilo):
    """Etiqueta arredondada: 'check' (branca com ✓), 'nota' (amarela com estrela), 'verde' ou 'branca'."""
    fnt = media(52)
    tw = ImageDraw.Draw(Image.new("RGB", (8, 8))).textlength(texto, font=fnt)
    icone = 58 if estilo in ("check", "nota") else 0
    w, h = int(tw + 60 + (icone + 10 if icone else 0)), 90
    img = Image.new("RGBA", (w + 24, h + 32), (0, 0, 0, 0))
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((12, 18, 12 + w, 18 + h), h // 2, fill=(0, 0, 0, 120))
    img.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(8)))
    d = ImageDraw.Draw(img)
    fundo, cor = {"check": ("white", PRETO), "nota": (AMARELO, PRETO),
                  "verde": (VERDE, "white"), "branca": ("white", PRETO)}[estilo]
    d.rounded_rectangle((12, 10, 12 + w, 10 + h), h // 2, fill=fundo)
    x = 12 + 26
    if estilo == "check":
        check(d, x - 4, 10 + (h - 58) // 2, 58)
        x += icone + 10
    elif estilo == "nota":
        estrela(d, x + 25, 10 + h / 2, 30, PRETO)
        x += icone + 10
    d.text((x, 10 + h / 2), texto, font=fnt, fill=cor, anchor="lm")
    return img


def _fileiras(imgs, y0, larg=930, gap_x=10, gap_y=4):
    """Centro (x, y) de cada etiqueta, em fileiras centralizadas a partir de y0."""
    fileiras, atual, ocupado = [], [], 0
    for i, im in enumerate(imgs):
        if atual and ocupado + gap_x + im.width > larg:
            fileiras.append(atual)
            atual, ocupado = [], 0
        ocupado += (gap_x if atual else 0) + im.width
        atual.append(i)
    if atual:
        fileiras.append(atual)
    pos, y = [None] * len(imgs), y0
    for fl in fileiras:
        x = (W - sum(imgs[i].width for i in fl) - gap_x * (len(fl) - 1)) / 2
        alt = max(imgs[i].height for i in fl)
        for i in fl:
            pos[i] = (x + imgs[i].width / 2, y + alt / 2)
            x += imgs[i].width + gap_x
        y += alt + gap_y
    return pos


def _momentos(linha, gatilhos):
    """Quando cada gatilho é falado na linha; se não achar a palavra, espalha por igual."""
    toks = [sem_acento(w).lower().strip(".,!?;:…\"'()") for w in linha["palavras"]]
    n, out, j = len(gatilhos), [], 0
    for k, g in enumerate(gatilhos):
        g = sem_acento((g or "").split()[0] if (g or "").split() else "").lower().strip(".,!?;:")
        achou = None
        for i in range(j, len(toks)):
            if g and (toks[i] == g or (len(g) >= 4 and toks[i].startswith(g[:4]))):
                achou = i
                break
        if achou is not None:
            out.append(linha["tempos"][achou][0])
            j = achou + 1
        else:
            out.append(linha["ini"] + (linha["fim"] - linha["ini"]) * (0.1 + 0.75 * k / max(1, n - 1)))
    for k in range(1, n):
        out[k] = max(out[k], out[k - 1] + 0.25)
    return out


def _blocos(palavras):
    """Legenda em blocos de até 3 palavras (máx. 16 letras), igual às legendas do TikTok."""
    blocos, atual = [], []
    for i in range(len(palavras)):
        if atual and (len(atual) >= 3 or len(" ".join(palavras[j] for j in atual + [i])) > 16):
            blocos.append(atual)
            atual = []
        atual.append(i)
    if atual:
        blocos.append(atual)
    return blocos


def _legenda_tv(palavras, bloco, ativo, largura=None):
    fnt = forte(66)
    d0 = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    linhas, atual = [], []
    for i in bloco:
        if atual and d0.textlength(" ".join(palavras[j] for j in atual + [i]), font=fnt) > (largura or TV_LEGENDA_LARG) - 50:
            linhas.append(atual)
            atual = []
        atual.append(i)
    if atual:
        linhas.append(atual)
    larg = max(d0.textlength(" ".join(palavras[j] for j in ln), font=fnt) for ln in linhas)
    img = Image.new("RGBA", (int(larg) + 56, len(linhas) * 82 + 34), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, img.width - 1, img.height - 1), 30, fill=(0, 0, 0, 150))
    y = 17 + 41
    for ln in linhas:
        texto = " ".join(palavras[j] for j in ln)
        x = (img.width - d.textlength(texto, font=fnt)) / 2
        for j in ln:
            d.text((x, y), palavras[j], font=fnt, fill=AMARELO if j == ativo else "white", anchor="lm",
                   stroke_width=4, stroke_fill=PRETO)
            x += d.textlength(palavras[j] + " ", font=fnt)
        y += 82
    return img


class LeitorClipe:
    """Lê o clipe do Flow quadro a quadro, já no tamanho da tela (1080x1920), sem o som.
    Clipe deitado (16:9) fica inteiro no meio, com ele mesmo desfocado atrás."""

    def __init__(self, caminho, fps=30, inicio=0.0):
        """inicio: segundo do clipe onde a leitura começa (o quadro 0 passa a ser esse ponto)."""
        self.dur = duracao(caminho) or 8.0
        info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                               "stream=width,height", "-of", "csv=p=0", str(caminho)],
                              capture_output=True, text=True).stdout.strip().split(",")
        try:
            deitado = int(info[0]) > int(info[1])
        except (ValueError, IndexError):
            deitado = False
        if deitado:
            filtro = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                      f"boxblur=30[f];[b]scale={W}:-2[p];[f][p]overlay=(W-w)/2:(H-h)/2,fps={fps},setsar=1")
        else:
            filtro = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},setsar=1"
        pular = ["-ss", f"{inicio:.3f}"] if inicio > 0 else []
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", *pular, "-i", str(caminho), "-an", "-vf", filtro,
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.lidos, self.atual = 0, Image.new("RGB", (W, H))

    def quadro(self, i):
        """Quadro número i (só anda pra frente; se pedir o mesmo de novo, repete)."""
        while self.lidos <= i:
            buf = self.proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            self.atual = Image.frombytes("RGB", (W, H), buf)
            self.lidos += 1
        return self.atual.copy()

    def fechar(self):
        try:
            self.proc.kill()
        except Exception:
            pass


def _etiqueta_ia():
    img = Image.new("RGBA", (W, 70), (0, 0, 0, 0))
    pilula(img, "cena gerada por IA", 190, 35, media(30), (0, 0, 0, 150), (235, 230, 245), px=18, py=8)
    return img


CLIPE_TRECHO = 2.4          # duração de cada trecho repetido do clipe (segundos)
CLIPE_ZOOM = (1.12, 1.24)   # zoom dos trechos repetidos: começa e termina nesses valores
CLIPE_TRECHOS_DE = [0.45, 0.2, 0.65, 0.3]   # de onde saem os trechos (fração do clipe)
CLIPE_FOTO_FINAL = 2.5      # com clipe: segundos de foto do produto no final (chamada + Lupi apontando)


def montar_video_tela_verde(falas, p, f1, f2, ia, nome, pasta, destino, rnd, clipe=None):
    """clipe: vídeo do Flow (o produto sendo usado). Quando tem, ele é o vídeo quase todo: toca inteiro
    no começo com o preço em cima desde o primeiro quadro; se a fala for mais longa, repete trechos dele
    com zoom; a foto do produto e o Lupi só aparecem na chamada final. Sem clipe: fotos e o Lupi."""
    fps = 30
    pct = round(p["desconto"] * 100)

    # 1) vozes: cada fala começa logo depois da outra (corta o silêncio das pontas)
    linhas, t, anterior = [], 0.15, None
    for k, ln in enumerate(falas):
        audio = pasta / f"tv{k}.mp3"
        voz, tom = (VOZ_LUPI, TOM_LUPI) if ln["quem"] == "lupi" else (VOZ_AMIGA, TOM_AMIGA)
        ok, pals = narrar_tempos(ln["fala"], audio, voz=voz, tom=tom, ritmo=RITMO_TELA_VERDE)
        dur = duracao(audio) if ok else max(1.2, len(ln["fala"]) / 15)
        vol = volume_por_quadro(audio, fps) if ok else []
        ini_fala, fim_fala = 0.0, dur
        ativos = [i for i, v in enumerate(vol) if v > 0.06]
        if ativos:
            ini_fala = max(0.0, ativos[0] / fps - 0.03)
            fim_fala = min(dur, (ativos[-1] + 1) / fps + 0.05)
        if anterior is not None:
            t += 0.22 if anterior != ln["quem"] else 0.08
        toks = [w for w in ln["fala"].split() if _palavra_legenda(w)]
        if len(pals) == len(toks):
            tempos = [(a, b) for a, b, _ in pals]
        else:
            tempos = [(ini_fala + a, ini_fala + b)
                      for a, b, _ in _tempos_estimados(" ".join(toks), fim_fala - ini_fala)]
        comeco = t - ini_fala                     # quando o áudio começa a tocar
        legenda = [_palavra_legenda(w) for w in toks]
        linhas.append({**ln, "audio": audio if ok else None, "comeco": comeco, "ini": t,
                       "fim": t + fim_fala - ini_fala, "vol": vol, "palavras": toks, "legenda": legenda,
                       "tempos": [(comeco + a, comeco + b) for a, b in tempos], "blocos": _blocos(legenda)})
        t += fim_fala - ini_fala
        anterior = ln["quem"]
    total = t + 0.8

    # 2) seções (o que aparece em cima) e planos (enquadramentos de ~2,4 s, cortando junto com a fala)
    secoes = []
    for ln in linhas:
        if secoes and secoes[-1]["secao"] == ln["secao"]:
            secoes[-1]["linhas"].append(ln)
        else:
            secoes.append({"secao": ln["secao"], "linhas": [ln], "ini": ln["ini"] - 0.06})
    secoes[0]["ini"] = 0.0
    for a, b in zip(secoes, secoes[1:]):
        a["fim"] = b["ini"]
    secoes[-1]["fim"] = total

    # clipe do Flow: vai do começo até os últimos CLIPE_FOTO_FINAL segundos (ou até a chamada, se ela
    # for curta). Toca inteiro em velocidade normal; se a fala for mais longa, o resto é preenchido
    # com trechos do meio dele, com zoom (repeticoes).
    leitor, fim_clipe, ritmo_clipe, repeticoes = None, 0.0, 1.0, []
    if clipe:
        leitor = LeitorClipe(clipe, fps)
        ini_cta = next((s["ini"] for s in secoes if s["secao"] == "cta"), total)
        fim_clipe = min(total, max(ini_cta, total - CLIPE_FOTO_FINAL))
        sobra = fim_clipe - leitor.dur
        if 0 < sobra < 0.8:
            ritmo_clipe = leitor.dur / fim_clipe          # falta pouco: o clipe toca um tiquinho mais devagar
        elif sobra >= 0.8:
            n = max(1, math.ceil(sobra / CLIPE_TRECHO))
            parte = sobra / n
            for k in range(n):
                de = leitor.dur * CLIPE_TRECHOS_DE[k % len(CLIPE_TRECHOS_DE)]
                repeticoes.append({"ini": leitor.dur + k * parte, "fim": leitor.dur + (k + 1) * parte,
                                   "de": max(0.0, min(de, leitor.dur - parte)), "leitor": None})
        preco_clipe, etiqueta_ia = _cartao_preco(p, pct), _etiqueta_ia()

    # cenários: foto 1, foto 2 e as versões em fundo colorido, intercalados (cada corte muda o visual)
    c1 = _cenarios(f1, rnd)
    c2 = _cenarios(f2, rnd) if f2 is not f1 else []
    canvases = [c1[0]] + [c for par in zip(c2 + [None] * 3, c1[1:] + [None] * 3) for c in par if c]
    movs = list(TV_MOVIMENTOS)
    rnd.shuffle(movs)
    planos = []
    for s in secoes:
        n = max(1, int(round((s["fim"] - s["ini"]) / TV_PLANO)))
        for k in range(n):
            planos.append({"ini": s["ini"] + (s["fim"] - s["ini"]) * k / n,
                           "fim": s["ini"] + (s["fim"] - s["ini"]) * (k + 1) / n, "secao": s["secao"]})
    outros = list(range(1, len(canvases))) or [0]
    # capa (1º plano): o produto recortado num fundo colorido, se deu; senão a foto principal
    capa = next((i for i, c in enumerate(canvases) if len(c1) > 1 and c is c1[1]), 0)
    for i, pl in enumerate(planos):
        if i == 0:
            pl["foto"], pl["mov"] = capa, "abre"
        elif i == len(planos) - 1:
            pl["foto"], pl["mov"] = 0, "fecha"
        elif pl["secao"] in ("preco", "cta"):        # fundo da foto original: o amarelo aparece bem
            pl["foto"], pl["mov"] = 0, "detalhe"
        else:
            pl["foto"], pl["mov"] = outros[i % len(outros)], movs[i % len(movs)]
        if i and pl["foto"] == planos[i - 1]["foto"] and pl["mov"] == planos[i - 1]["mov"]:
            pl["mov"] = movs[(i + 1) % len(movs)]

    # 3) camadas de cada seção: (imagem, centro x, centro y, a partir de quando)
    camadas_secao, sons = {}, []
    for si, s in enumerate(secoes):
        tipo, ln0, cam = s["secao"], s["linhas"][0], []
        if tipo == "produto":
            img = _cartao_nome(nome)
            cam.append((img, W / 2, TV_TEXTO_Y + img.height / 2, s["ini"] + 0.05))
        elif tipo == "preco":
            img = _cartao_preco(p, pct)
            cam.append((img, W / 2, TV_TEXTO_Y + img.height / 2, s["ini"] + 0.05))
            sons.append((s["ini"] + 0.3, "plim", 0.45))
        elif tipo in ("usos", "beneficios", "prova"):
            if tipo == "usos":
                itens = [(u, "check") for u in ia.get("usos", [])]
                gat = [u for u, _ in itens]
            elif tipo == "beneficios":
                itens = [(b, "check") for b in ia.get("beneficios", [])[:3]]
                gat = [""] * len(itens)
            else:
                itens = [(f"{p['nota']:.1f}".replace(".", ",") + " na Shopee", "nota"),
                         (f"{vendas_texto(p['vendas'])} {METRICA}", "branca")]
                gat = ["nota", "com"]
                if p.get("nacional", True):
                    itens.append(("enviado do Brasil", "verde"))
                    gat.append("enviado")
            imgs = [_etiqueta(txt, est) for txt, est in itens]
            pos = _fileiras(imgs, TV_TEXTO_Y + 10)
            for img, (x, y), quando in zip(imgs, pos, _momentos(ln0, gat)):
                cam.append((img, x, y, quando))
                sons.append((quando, "pop", 0.4))
        elif tipo == "cta":
            img = _cartao_cta()
            cam.append((img, W / 2, TV_TEXTO_Y + img.height / 2, s["ini"] + 0.05))
        camadas_secao[si] = cam
        if si > 0 and s["ini"] > fim_clipe:
            sons.append((s["ini"] - 0.1, "whoosh", 0.3))
    if leitor:
        sons.append((fim_clipe - 0.1, "whoosh", 0.35))       # passagem do clipe pra foto da chamada
        for r in repeticoes:
            sons.append((r["ini"] - 0.08, "whoosh", 0.22))   # corte pra cada trecho repetido
    topo_img = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
    pilula(topo_img, "link no perfil  ↗", W / 2, 60, media(40), (0, 0, 0, 150), "white", px=30, py=14)

    # 4) áudio: falas no tempo certo + efeitos
    efeitos = gerar_efeitos(pasta)
    entradas, filtros, mix = [], [], []
    for ln in linhas:
        if ln["audio"]:
            entradas.append(ln["audio"])
            ms = int(max(0.0, ln["comeco"]) * 1000)
            filtros.append(f"[{len(entradas) - 1}:a]adelay={ms}|{ms}[a{len(entradas) - 1}]")
            mix.append(f"[a{len(entradas) - 1}]")
    for quando, nome_som, vol in sons:
        entradas.append(efeitos[nome_som])
        k = len(entradas) - 1
        ms = int(max(0.0, quando) * 1000)
        filtros.append(f"[{k}:a]adelay={ms}|{ms},volume={vol}[a{k}]")
        mix.append(f"[a{k}]")
    n_quadros = int(math.ceil(total * fps))
    audio_final = pasta / "audio.wav"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for e in entradas:
        cmd += ["-i", str(e)]
    if not entradas:
        cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filtros, mix = ["[0:a]anull[a0]"], ["[a0]"]
    filtros.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0,"
                   "loudnorm=I=-15:TP=-1.5:LRA=11,apad[out]")      # volume no padrão das redes
    cmd += ["-filter_complex", ";".join(filtros), "-map", "[out]", "-t", f"{n_quadros / fps:.3f}",
            "-ar", "44100", "-ac", "2", str(audio_final)]
    subprocess.run(cmd, check=True)

    # 5) quadro a quadro: enquadramento da foto + textos de cima + Lupi + legenda
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(fps), "-i", "-", "-i", str(audio_final), "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(Path(destino).resolve())],
        stdin=subprocess.PIPE)
    sprites, cache = {}, {}

    def lupi(boca, olhos, pose):
        if (boca, olhos, pose) not in sprites:
            sprites[(boca, olhos, pose)] = desenhar_lupi(TV_LUPI_ALTURA, boca, olhos, pose)
        return sprites[(boca, olhos, pose)]

    trecho_atual = None
    for q in range(n_quadros):
        tt = q / fps
        no_clipe = leitor is not None and tt < fim_clipe
        rep = next((r for r in repeticoes if r["ini"] <= tt < r["fim"]), None) if no_clipe else None
        if rep:
            if rep is not trecho_atual:              # trecho novo: lê o clipe a partir do ponto escolhido
                if trecho_atual:
                    trecho_atual["leitor"].fechar()
                rep["leitor"], trecho_atual = LeitorClipe(clipe, fps, inicio=rep["de"]), rep
            u = (tt - rep["ini"]) / max(0.05, rep["fim"] - rep["ini"])
            quadro = rep["leitor"].quadro(int((tt - rep["ini"]) * fps))
            quadro = _enquadrar(quadro, CLIPE_ZOOM[0] + (CLIPE_ZOOM[1] - CLIPE_ZOOM[0]) * u, W / 2, H / 2)
        elif no_clipe:
            quadro = leitor.quadro(int(tt * ritmo_clipe * fps))
        else:
            pl = next((x for x in planos if x["ini"] <= tt < x["fim"]), planos[-1])
            u = min(1.0, (tt - pl["ini"]) / max(0.05, pl["fim"] - pl["ini"]))
            fundo, cy = canvases[pl["foto"]]
            z, cx, cy2 = _camera(pl["mov"], u, cy)
            z *= 1 + 0.05 * max(0.0, 1 - (tt - pl["ini"]) * fps / 5)       # pulinho a cada corte
            quadro = _enquadrar(fundo, z, cx, cy2)

        si = next((i for i, s in enumerate(secoes) if s["ini"] <= tt < s["fim"]), len(secoes) - 1)
        s = secoes[si]
        selos = s["secao"] in ("usos", "beneficios", "prova", "cta")
        if no_clipe:
            # o produto em uso + o preço desde o 1º quadro (é o que segura a pessoa) + aviso de IA;
            # na nota e na chamada, os selos (nota, vendas...) ou o "link no perfil" entram no lugar do preço
            if not selos:
                quadro.paste(preco_clipe, (0, TV_TEXTO_Y - 30), preco_clipe)
            quadro.paste(etiqueta_ia, (0, 200), etiqueta_ia)
        elif s["secao"] not in ("gancho", "cta"):
            quadro.paste(topo_img, (0, 262 - 60), topo_img)
        if no_clipe:
            pass
        elif s["secao"] == "gancho":
            ln = s["linhas"][0]
            ativo = -1
            if ln["ini"] - 0.05 <= tt <= ln["fim"]:
                ativo = max([k for k, (a, b) in enumerate(ln["tempos"]) if tt >= a] or [0])
            chave = ("pergunta", ativo)
            if chave not in cache:
                cache[chave] = _cartao_pergunta(ln["palavras"], ativo)
            img = cache[chave]
            _colar(quadro, img, W / 2, TV_TEXTO_Y - 30 + img.height / 2, int((tt - 0.0) * fps))
        for img, x, y, quando in (camadas_secao[si] if selos or not no_clipe else []):
            if tt >= quando:
                _colar(quadro, img, x, y, int((tt - (quando if no_clipe else max(quando, fim_clipe))) * fps))

        # fala de agora (pra boca do Lupi e a legenda)
        atual = next((ln for ln in linhas if ln["ini"] - 0.05 <= tt <= ln["fim"] + 0.12), None)
        falando = atual is not None and atual["quem"] == "lupi"
        boca = "sorriso"
        if falando and atual["vol"]:
            i = int((tt - atual["comeco"]) * fps)
            v = atual["vol"][i] if 0 <= i < len(atual["vol"]) else 0
            boca = "aberta" if v > 0.55 else ("meia" if v > 0.22 else "sorriso")
        olhos = "fechados" if ((q + 50) % 96) in (0, 1, 2, 3) else "abertos"   # 1º quadro (capa) de olho aberto
        pose = "aponta" if s["secao"] == "cta" else "normal"
        pulo = abs(math.sin(tt * 7)) * 10 if falando else 3 * math.sin(tt * 2)
        if not no_clipe:          # no clipe o produto é o destaque: o Lupi só entra depois
            sp = lupi(boca, olhos, pose)
            quadro.paste(sp, (-20, int(TV_LUPI_PE - sp.height - pulo)), sp)

        # legenda: ao lado do Lupi; durante o clipe, no meio e pra todo mundo que fala
        if atual is not None and atual["legenda"] and (falando or no_clipe):
            k_ativo = max([k for k, (a, b) in enumerate(atual["tempos"]) if tt >= a] or [0])
            bi = next(i for i, b in enumerate(atual["blocos"]) if k_ativo in b)
            chave = (id(atual), bi, k_ativo, no_clipe)
            if chave not in cache:
                if len(cache) > 40:
                    cache.clear()
                cache[chave] = _legenda_tv(atual["legenda"], atual["blocos"][bi], k_ativo,
                                           largura=860 if no_clipe else None)
            inicio_bloco = atual["tempos"][atual["blocos"][bi][0]][0]
            img = cache[chave]
            lx, ly = (W / 2, LEGENDA_Y + 40) if no_clipe else TV_LEGENDA
            _colar(quadro, img, lx, ly, max(0, int((tt - inicio_bloco) * fps)))
        proc.stdin.write(quadro.tobytes())
    proc.stdin.close()
    if leitor:
        leitor.fechar()
    for r in repeticoes:
        if r["leitor"]:
            r["leitor"].fechar()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg falhou ao montar o vídeo tela verde")


def _slug(palavra):
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(palavra).lower()).strip("-")


def produzir_video(item, pasta_dia, rnd, clipe=None):
    """Monta o vídeo de um produto já escolhido. item: produto, ia, link, palavra, titulo, fotos_ref.
    clipe: vídeo do Flow (opcional), usado até a chamada final."""
    p, ia, link, palavra, nome = item["produto"], item["ia"], item["link"], item["palavra"], item["titulo"]
    pct = round(p["desconto"] * 100)
    slug = _slug(palavra)
    pasta = pasta_dia / slug
    pasta.mkdir(parents=True, exist_ok=True)
    fotos = []
    for k, url in enumerate((item.get("fotos_ref") or [p["imagem"]])[:2]):
        try:
            fotos.append(baixar_foto(url, pasta / f"foto{k + 1}.jpg"))
        except Exception as e:
            print(f"  (não baixei a foto {k + 1}: {e})")
    if not fotos:
        fotos = [baixar_foto(p["imagem"], pasta / "foto1.jpg")]
    f1, f2 = fotos[0], fotos[-1]
    if not item.get("ficha") and f2 is not f1 and _foto_limpa(f2) > _foto_limpa(f1) + 0.15:
        f1, f2 = f2, f1          # a foto mais limpa vira a principal (preço, chamada e capa)
    falas = roteiro_tela_verde(p, ia, palavra, rnd)
    video = pasta_dia / f"{slug}.mp4"
    montar_video_tela_verde(falas, p, f1, f2, ia, nome, pasta, video, rnd, clipe=clipe)
    dialogo = "\n".join(f"{'Lupi' if x['quem'] == 'lupi' else 'Amiga'}: {x['fala']}" for x in falas)
    resumo = (f"🎬 {nome} — pronto pra postar" + (" (com o clipe do Flow)" if clipe else "") + "\n"
              f"De {reais(p['preco_cheio'])} por {reais(p['preco'])} (-{pct}%)\n"
              + aviso_link(link, bool(FEED_URLS)) + f"\n{dialogo}")
    return {"titulo": nome, "video": video, "resumo": resumo,
            "legenda": legenda_promo(p, ia, palavra, ia_video=bool(clipe)), "ia": bool(ia),
            "canal": canal_promo(p, ia, palavra, link),
            "whatsapp": whatsapp_promo(p, ia, palavra, link),
            "foto_canal": p["imagem"], "ids": [p["id"]],
            "registro": oferta_registro_promo(p, ia, palavra, link)}


def fazer_tela_verde(produtos, palavra, hist, pasta_dia, rnd, usar_feed, sub):
    p = escolher_promo(produtos, hist)
    if not p:
        return None
    link = obter_link(p, usar_feed, sub)
    ia = roteiro_ia(p)
    print(f"  produto: {p['nome'][:70]} | IA: {'sim' if ia else 'não (texto padrão)'}")
    item = {"produto": p, "ia": ia, "link": link, "palavra": palavra, "titulo": nome_promo(p, ia, palavra),
            "fotos_ref": [p["imagem"]] + ([p["imagem2"]] if p.get("imagem2") else [])}
    return produzir_video(item, pasta_dia, rnd)


# ------------------------------------------------------------
# Google Flow: de manhã o robô manda no Telegram as fotos e o texto pronto de cada produto;
# você gera o clipe no Flow e manda de volta. Nos horários de postagem o robô pega o clipe,
# confere se o produto saiu igual às fotos e monta o vídeo com ele.
# ------------------------------------------------------------
IA_FLOW_SISTEMA = (
    "Você prepara pedidos para uma IA que gera vídeos curtos (Google Flow) de anúncios de produtos. "
    "Você recebe o título, a descrição e as fotos reais do produto. O vídeo vai mostrar uma pessoa usando "
    "o produto, e o produto precisa sair IGUAL ao das fotos. Regras: descreva só o que dá pra ver nas fotos; "
    "a cena tem que mostrar com clareza, em close, as partes que definem o produto; prefira uma ação simples "
    "e contínua com as mãos; o rosto da pessoa nunca aparece; nada de texto na tela; nada perigoso, sensual "
    "ou com crianças. Responda apenas com um objeto JSON."
)
FICHA_PADRAO = {
    "tipo": "", "detalhes": ["same shape, colors and details as the reference photos"], "detalhes_pt": [],
    "cenario": "in a bright, cozy home",
    "acao": "A person's hands pick up this exact product and show it being used, turning it slowly so every side is visible",
    "enquadramento": "Close-up on the hands, face not visible", "fotos": [],
}


def _ponto(t):
    t = (t or "").strip()
    return t if t.endswith((".", "!", "?")) else t + "."


def _validar_ficha(d, n_fotos):
    if not isinstance(d, dict):
        return {}

    def lista(chave, limite):
        v = d.get(chave) if isinstance(d.get(chave), list) else []
        return [x for x in (limpar_texto(i, limite) for i in v if isinstance(i, str)) if len(x) >= 4][:4]

    out = {"tipo": limpar_texto(d.get("tipo"), 40), "detalhes": lista("detalhes", 170),
           "detalhes_pt": lista("detalhes_pt", 70), "cenario": limpar_texto(d.get("cenario"), 90),
           "acao": limpar_texto(d.get("acao"), 330), "enquadramento": limpar_texto(d.get("enquadramento"), 120)}
    if not (out["detalhes"] and len(out["acao"]) >= 20 and len(out["cenario"]) >= 4):
        return {}
    if not re.match(r"(in|on|at|inside|outdoors)\b", out["cenario"], re.I):
        out["cenario"] = "in " + out["cenario"]
    if "face" not in out["enquadramento"].lower():
        out["enquadramento"] = _ponto(out["enquadramento"] or "Close-up on the hands") + " Face not visible"
    fotos = []
    for i in d.get("fotos") if isinstance(d.get("fotos"), list) else []:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if 0 <= i < n_fotos and i not in fotos:
            fotos.append(i)
    out["fotos"] = fotos[:2]
    return out


def ficha_flow(p, fotos):
    """A IA olha as fotos e diz o que não pode mudar no produto e qual cena mostra isso."""
    pedido = (
        f"Produto: {p['nome']}\nDescrição do vendedor (pode estar bagunçada): {p.get('descricao', '')[:800]}\n"
        f"São {len(fotos)} fotos, numeradas de 0 a {len(fotos) - 1}, na ordem em que vieram.\n\n"
        "Devolva JSON com estas chaves:\n"
        '"tipo": nome simples do produto em português, até 4 palavras;\n'
        '"detalhes": lista em inglês com 2 a 4 detalhes visuais que definem este produto e que o vídeo não pode '
        'mudar (formato, peças características, cores, visor etc.), ex.: "each earbud has a large curved ear hook '
        'that wraps over the top of the ear";\n'
        '"detalhes_pt": a mesma lista em português, bem curta (ex.: "gancho curvo atrás da orelha");\n'
        '"cenario": em inglês, onde a cena acontece, começando com "in" ou "on" (ex.: "in a park at sunrise");\n'
        '"acao": em inglês, uma ação simples e contínua de 8 segundos com as mãos de uma pessoa usando o produto, '
        'que mostre os detalhes acima em close; escreva "this exact" antes do nome do produto; até 45 palavras;\n'
        '"enquadramento": em inglês, como a câmera mostra a cena, sempre com o rosto fora da imagem '
        '(ex.: "Close-up on the hands, face not visible.");\n'
        '"fotos": lista com os números das 2 fotos que mostram melhor o produto de verdade, de preferência '
        "sem texto, montagem ou marca d'água, a melhor primeiro."
    )
    texto = chamar_ia([{"role": "system", "content": IA_FLOW_SISTEMA},
                       {"role": "user", "content": pedido}], imagens=fotos)
    m = re.search(r"\{.*\}", texto or "", re.S)
    try:
        return _validar_ficha(json.loads(m.group(0)), len(fotos)) if m else {}
    except Exception:
        return {}


def pedido_flow(ficha):
    """Texto pronto pra colar no Flow (o mesmo formato que funcionou no teste do fone)."""
    det = "; ".join(ficha["detalhes"])
    prompt = (f"Vertical smartphone video {ficha['cenario']}. {_ponto(ficha['acao'])} "
              f"Key product details that must match the reference: {det}, and they must be clearly visible "
              f"in close-up. {_ponto(ficha['enquadramento'])} Natural light, slight handheld movement, realistic. "
              "No on-screen text or captions.")
    return (f"Gere 1 vídeo com o {MODELO_FLOW} (não use outro modelo), vertical 9:16, 8 segundos, "
            f"usando as fotos anexadas como referência do produto. Prompt:\n\n{prompt}")


def ler_fila():
    try:
        return json.loads(FILA.read_text())
    except Exception:
        return {}


def salvar_fila(fila):
    FILA.write_text(json.dumps(fila, ensure_ascii=False, indent=1))


def _jpeg_bytes(img):
    buf = io.BytesIO()
    f = img.convert("RGB")
    f.thumbnail((1600, 1600))
    f.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def enviar_kit(fila, item, fotos):
    """Manda no Telegram as fotos de referência e o texto pronto pro Flow. Guarda o número das mensagens
    (se você responder uma delas com o vídeo, o robô sabe de qual produto é)."""
    e = html.escape
    p, ficha = item["produto"], item["ficha"]
    ids = []
    if fotos:
        arquivos = {f"f{k}": (f"foto{k + 1}.jpg", _jpeg_bytes(f), "image/jpeg") for k, f in enumerate(fotos)}
        if len(fotos) > 1:
            media = [{"type": "photo", "media": f"attach://f{k}"} for k in range(len(fotos))]
            res = telegram("sendMediaGroup", {"chat_id": TG_CHAT, "media": json.dumps(media)}, arquivos)
            ids += [m["message_id"] for m in res or []]
        else:
            res = telegram("sendPhoto", {"chat_id": TG_CHAT}, {"photo": arquivos["f0"]})
            ids += [res["message_id"]] if res else []
    n, total = item["numero"], len(fila["itens"])
    hora = HORARIOS_POSTAGEM[n - 1] if n <= len(HORARIOS_POSTAGEM) else ""
    confere = "; ".join(ficha.get("detalhes_pt") or [])
    texto = (f"🎬 <b>Vídeo {n} de {total} · {e(item['titulo'])}</b>" + (f" (sai às {hora})" if hora else "")
             + f"\nDe {reais(p['preco_cheio'])} por {reais(p['preco'])}\n\n"
             "1. Salve as fotos acima.\n"
             f"2. No Flow: anexe as fotos, cole o texto abaixo e aprove ({CREDITOS_FLOW} créditos).\n"
             + (f"3. Antes de mandar, confira se aparece: <b>{e(confere)}</b>.\n" if confere
                else "3. Antes de mandar, confira se o produto saiu igual ao das fotos.\n")
             + "4. <b>Responda esta mensagem</b> com o vídeo (ou só mande os vídeos na ordem).\n\n"
             f"<pre>{e(item['pedido'])}</pre>")
    res = telegram("sendMessage", {"chat_id": TG_CHAT, "text": texto, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"})
    if res:
        ids.append(res["message_id"])
    item["msg_ids"] = ids


def _baixar_fotos(urls, pasta, prefixo="ref"):
    pasta.mkdir(parents=True, exist_ok=True)
    ok, fotos = [], []
    for k, url in enumerate(urls[:5]):
        try:
            fotos.append(baixar_foto(url, pasta / f"{prefixo}{k}.jpg"))
            ok.append(url)
        except Exception as e:
            print(f"  (não baixei a foto {k}: {e})")
    return ok, fotos


def rodar_kit():
    hoje = dt.date.today()
    fila = ler_fila()
    pasta_dia = SAIDA / hoje.isoformat()
    pasta_dia.mkdir(parents=True, exist_ok=True)

    if fila.get("data") == hoje.isoformat() and fila.get("itens"):
        print("O kit de hoje já existe: mandando de novo o que ainda espera clipe.")
        for item in fila["itens"]:
            if item["status"] == "aguardando" and not item.get("clipe"):
                _, fotos = _baixar_fotos(item["fotos_ref"], pasta_dia / f"kit{item['numero']}")
                enviar_kit(fila, item, fotos)
        salvar_fila(fila)
        return

    usar_feed, palavras, produtos_de = preparar_busca()
    hist = ler_historico()
    itens = []
    for palavra in palavras:
        if len(itens) >= VIDEOS_POR_DIA:
            break
        print(f"> {palavra}")
        try:
            p = escolher_promo(produtos_de(palavra), hist)
            if not p:
                print("  nada bom pra essa palavra hoje")
                continue
            numero = len(itens) + 1
            link = obter_link(p, usar_feed, ["robo", hoje.strftime("%Y%m%d"), str(numero)])
            ia = roteiro_ia(p)
            pasta = pasta_dia / f"kit{numero}"
            pasta.mkdir(exist_ok=True)
            urls, fotos = _baixar_fotos(p.get("imagens") or [p["imagem"]], pasta)
            if not fotos:
                continue
            ficha = ficha_flow(p, fotos) if USAR_FLOW else {}
            print(f"  produto: {p['nome'][:70]} | roteiro IA: {'sim' if ia else 'não'} | "
                  f"ficha IA: {'sim' if ficha else 'não (texto padrão)'}")
            ordem = ficha.get("fotos") or sorted(range(len(fotos)), key=lambda i: -_foto_limpa(fotos[i]))
            ordem = ordem[:2]
            ficha = ficha or dict(FICHA_PADRAO)
            item = {"numero": numero, "palavra": palavra, "titulo": nome_promo(p, ia, palavra),
                    "produto": p, "ia": ia, "link": link, "ficha": ficha, "pedido": pedido_flow(ficha),
                    "fotos_ref": [urls[i] for i in ordem], "status": "aguardando", "clipe": None,
                    "msg_ids": []}
            item["_fotos"] = [fotos[i] for i in ordem]
            itens.append(item)
            hist[p["id"]] = hoje.isoformat()
        except Exception as e:
            print(f"  erro em '{palavra}': {e}")

    fila = {"data": hoje.isoformat(), "metrica": METRICA, "kit_ts": int(time.time()),
            "offset": fila.get("offset", 0), "itens": itens}
    if not itens:
        avisar("Robô: hoje não achei produto bom pro kit. Tente outras palavras em PALAVRAS "
               "ou baixe DESCONTO_MINIMO / CURTIDAS_MINIMAS / aumente PRECO_MAXIMO.")
    elif USAR_FLOW and (TG_CHAT or MODO_TESTE):
        avisar(f"☀️ Kit de hoje ({hoje:%d/%m}): {len(itens)} vídeo(s). Gere os clipes juntos no Flow "
               f"({len(itens) * CREDITOS_FLOW} créditos). Se não der tempo, sem problema: o robô posta com as fotos.")
        for item in itens:
            enviar_kit(fila, item, item["_fotos"])
    for item in itens:
        item.pop("_fotos", None)
    salvar_fila(fila)
    salvar_historico(hist)
    print(f"Kit pronto: {len(itens)} produto(s).")


def receber_clipes(fila):
    """Pega no Telegram os vídeos que você mandou (só do seu chat) e liga cada um ao produto certo:
    pela mensagem que você respondeu, pelo número na legenda ("1", "2") ou pela ordem."""
    updates = []
    if MODO_TESTE:      # CLIPE_TESTE="1=/caminho/clipe.mp4;2=/outro.mp4"
        for k, parte in enumerate(x for x in os.environ.get("CLIPE_TESTE", "").split(";") if "=" in x):
            n, caminho = parte.split("=", 1)
            updates.append({"update_id": fila.get("offset", 0) + k, "message": {
                "chat": {"id": TG_CHAT}, "date": int(time.time()), "caption": n.strip(),
                "video": {"file_id": "local:" + caminho.strip(), "file_size": 1}}})
    elif TG_TOKEN:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", timeout=60,
                             params={"offset": fila.get("offset", 0), "timeout": 0,
                                     "allowed_updates": json.dumps(["message"])})
            updates = r.json().get("result", []) if r.ok else []
            if not r.ok:
                print(f"Telegram (getUpdates) erro: {r.text[:200]}")
        except Exception as e:
            print(f"Telegram (getUpdates) erro: {e}")
    for u in updates:
        fila["offset"] = max(fila.get("offset", 0), u.get("update_id", 0) + 1)
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != str(TG_CHAT):
            continue                                   # só aceita vídeo do seu chat
        if m.get("date", 0) < fila.get("kit_ts", 0) - 60:
            continue                                   # vídeo de antes do kit de hoje
        doc = m.get("document") or {}
        # vídeo sem som o Telegram costuma transformar em "animação" (GIF): aceita também
        arq = (m.get("video") or m.get("animation")
               or (doc if str(doc.get("mime_type", "")).startswith("video/") else None))
        if not arq:
            continue
        legenda = sem_acento((m.get("caption") or "").lower())
        alvo = None
        resp = (m.get("reply_to_message") or {}).get("message_id")
        if resp:
            alvo = next((it for it in fila["itens"] if resp in it.get("msg_ids", [])), None)
        num = re.search(r"\b(\d)\b", legenda)
        if alvo is None and num:
            alvo = next((it for it in fila["itens"] if it["numero"] == int(num.group(1))), None)
        if alvo is None:
            alvo = next((it for it in fila["itens"] if it["status"] == "aguardando" and not it.get("clipe")), None)
        if alvo is None:
            avisar("Recebi um vídeo, mas nenhum produto de hoje está esperando clipe.")
            continue
        if alvo["status"] != "aguardando":
            avisar(f"Recebi um clipe pro vídeo {alvo['numero']}, mas ele já foi postado.")
            continue
        alvo["clipe"] = {"file_id": arq["file_id"], "tamanho": arq.get("file_size", 0),
                         "forcar": "forcar" in legenda, "conferido": None, "motivo": ""}
        print(f"  clipe recebido pro vídeo {alvo['numero']}")


def baixar_clipe(clipe, destino):
    fid = clipe["file_id"]
    if fid.startswith("local:"):
        import shutil
        shutil.copy(fid[len("local:"):], destino)
        return
    if clipe.get("tamanho", 0) > 20_000_000:
        raise RuntimeError("o vídeo passou de 20 MB, o limite do Telegram pra robôs "
                           "(mande como vídeo, não como arquivo)")
    info = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getFile",
                        params={"file_id": fid}, timeout=60).json()
    if not info.get("ok"):
        raise RuntimeError(info.get("description", "o Telegram não entregou o arquivo"))
    r = requests.get(f"https://api.telegram.org/file/bot{TG_TOKEN}/{info['result']['file_path']}", timeout=180)
    r.raise_for_status()
    destino.write_bytes(r.content)


def quadros_do_clipe(caminho, fracoes=(0.2, 0.5, 0.85)):
    dur = duracao(caminho)
    quadros = []
    for fr in fracoes:
        png = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{dur * fr:.2f}", "-i", str(caminho),
                              "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                             capture_output=True).stdout
        if png:
            quadros.append(Image.open(io.BytesIO(png)).convert("RGB"))
    return quadros


def conferir_produto(caminho, item, pasta):
    """A IA compara os quadros do clipe com as fotos reais. Devolve (aprovado, motivo).
    Se a IA não responder, aprova (você já conferiu antes de mandar)."""
    if MODO_TESTE or not USAR_IA:
        return True, "conferência da IA pulada (modo teste)"
    _, refs = _baixar_fotos(item["fotos_ref"], pasta, f"conf{item['numero']}_")
    quadros = quadros_do_clipe(caminho)
    if not refs or not quadros:
        return True, "não deu pra comparar com as fotos"
    detalhes = item["ficha"].get("detalhes_pt") or item["ficha"].get("detalhes") or []
    pedido = (f"As {len(refs)} primeiras imagens são fotos reais do produto \"{item['titulo']}\". "
              f"As {len(quadros)} seguintes são quadros de um vídeo gerado por IA.\n"
              f"Detalhes que não podem mudar: {'; '.join(detalhes) or 'formato, cores e peças do produto'}.\n\n"
              "O produto do vídeo é o mesmo das fotos? Reprove só se ele estiver claramente diferente: outro "
              "formato, faltando uma peça característica ou de outra cor. Ignore cenário, pessoa, luz, ângulo e "
              "letras ou logos pequenos.\n"
              'Devolva JSON: {"aprovado": true ou false, "motivo": "frase curta em português"}')
    texto = chamar_ia([{"role": "system", "content": "Você confere se um vídeo gerado por IA mostra o mesmo "
                                                     "produto das fotos reais de um anúncio. Responda apenas "
                                                     "com um objeto JSON."},
                       {"role": "user", "content": pedido}], imagens=refs + quadros)
    m = re.search(r"\{.*\}", texto or "", re.S)
    try:
        d = json.loads(m.group(0))
    except Exception:
        return True, "a IA não respondeu, então não deu pra conferir"
    ok = d.get("aprovado") is True or str(d.get("aprovado")).lower() == "true"
    motivo = limpar_texto(d.get("motivo"), 160) or ("o produto saiu igual às fotos" if ok
                                                    else "o produto saiu diferente das fotos")
    return ok, motivo


def conferir_clipes(fila, pasta_dia):
    """Baixa os clipes que chegaram e confere cada um (só uma vez). Devolve {número: arquivo} dos aprovados."""
    prontos = {}
    for it in fila["itens"]:
        c = it.get("clipe")
        if not c or it["status"] != "aguardando":
            continue
        n = it["numero"]
        destino = pasta_dia / f"clipe{n}.mp4"
        try:
            baixar_clipe(c, destino)
        except Exception as e:
            if c.get("conferido") is None:
                avisar(f"❌ Não consegui baixar o clipe do vídeo {n} ({e}). Ele vai sair com as fotos.")
            c["conferido"], c["motivo"] = False, f"não consegui baixar o clipe ({e})"
            continue
        if c.get("conferido") is None:
            ok, motivo = conferir_produto(destino, it, pasta_dia)
            if not ok and c.get("forcar"):
                ok, motivo = True, f"a IA achou diferente ({motivo}), mas você pediu pra usar"
            c["conferido"], c["motivo"] = ok, motivo
            if ok:
                avisar(f"✅ Clipe do vídeo {n} ({it['titulo']}) conferido: {motivo}.")
            else:
                avisar(f"❌ O clipe do vídeo {n} ({it['titulo']}) não passou: {motivo}. Ele vai sair com as "
                       "fotos. Se você achar que o produto está certo, responda o kit com o mesmo vídeo e a "
                       "legenda \"forçar\" antes do horário dele.")
        if c["conferido"]:
            prontos[n] = destino
    return prontos


def rodar_postar():
    """Monta e entrega o próximo vídeo do dia (primeiro o que já tem clipe aprovado)."""
    global METRICA
    hoje = dt.date.today()
    fila = ler_fila()
    if fila.get("data") != hoje.isoformat() or not fila.get("itens"):
        print("Não tem kit de hoje: fazendo 1 vídeo do jeito antigo.")
        return rodar_completo(maximo=1)
    METRICA = fila.get("metrica", METRICA)
    pasta_dia = SAIDA / hoje.isoformat()
    pasta_dia.mkdir(parents=True, exist_ok=True)
    receber_clipes(fila)
    prontos = conferir_clipes(fila, pasta_dia) if USAR_FLOW else {}
    salvar_fila(fila)                     # guarda os clipes recebidos mesmo se a montagem falhar
    pendentes = [it for it in fila["itens"] if it["status"] == "aguardando"]
    if not pendentes:
        print("Os vídeos de hoje já saíram.")
        return
    item = next((it for it in pendentes if it["numero"] in prontos), pendentes[0])
    clipe = prontos.get(item["numero"])
    rnd = random.Random(hoje.toordinal() * 10 + item["numero"])
    print(f"> vídeo {item['numero']}: {item['titulo']} ({'com clipe do Flow' if clipe else 'só com fotos'})")
    try:
        r = produzir_video(item, pasta_dia, rnd, clipe)
    except Exception as e:
        if not clipe:
            raise
        print(f"  erro montando com o clipe ({e}); tentando só com as fotos")
        clipe = None
        r = produzir_video(item, pasta_dia, rnd)
    entregar_telegram(r)
    if USAR_FLOW and not clipe:
        motivo = (item.get("clipe") or {}).get("motivo") or "o clipe do Flow não chegou a tempo"
        avisar(f"(O vídeo {item['numero']} saiu só com as fotos: {motivo}.)")
    item["status"], item["postado_em"] = "postado", dt.datetime.now().strftime("%H:%M")
    ofertas = ler_ofertas()
    ofertas.insert(0, r["registro"])
    salvar_ofertas(ofertas)
    publicar_pagina(ofertas)
    texto = r["whatsapp"] + "\n\n_Link de afiliado · preço de hoje, pode mudar_"
    if PAGINA_URL:
        texto += f"\n\nTodas as ofertas: {PAGINA_URL}"
    publicar_painel([{"palavra": r["titulo"], "video": r["video"], "legenda": r["legenda"],
                      "ia": r.get("ia")}], texto)
    avisar("Pro WhatsApp (copie tudo abaixo e cole no seu canal):")
    avisar(texto)
    salvar_fila(fila)
    print(f"Pronto: vídeo {item['numero']} entregue.")


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
    """Cada cena é uma imagem (ou uma lista de imagens que se dividem o tempo da fala)."""
    partes = []
    for i, (cena, fala) in enumerate(zip(cenas, falas)):
        imagens = cena if isinstance(cena, list) else [cena]
        pngs = []
        for j, img in enumerate(imagens):
            png = pasta / f"cena{i}_{j}.png"
            img.save(png)
            pngs.append(png)
        audio = pasta / f"fala{i}.mp3"
        tem_audio = narrar(fala, audio)
        seg = (duracao(audio) + 0.35) if tem_audio else max(2.5, len(fala) / 14)
        quadros = max(1, int(seg * 30 / len(pngs)))
        parte = pasta / f"parte{i}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for png in pngs:
            cmd += ["-i", str(png)]
        if tem_audio:
            cmd += ["-i", str(audio)]
        else:
            cmd += ["-f", "lavfi", "-t", f"{seg:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        filtros = [f"[{j}:v]scale=2160:3840,zoompan=z='min(zoom+0.0008,1.08)':d={quadros}"
                   f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps=30,setsar=1[v{j}]"
                   for j in range(len(pngs))]
        filtros.append("".join(f"[v{j}]" for j in range(len(pngs)))
                       + f"concat=n={len(pngs)}:v=1:a=0[v]")
        cmd += ["-filter_complex", ";".join(filtros), "-map", "[v]", "-map", f"{len(pngs)}:a",
                "-t", f"{seg:.2f}", "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2",
                "-af", "apad", str(parte)]
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
_TG_FALSO = [1000]     # números de mensagem de mentira no modo teste


def telegram(metodo, dados, arquivos=None):
    """Chama a API do Telegram e devolve o 'result' (ou None se deu erro)."""
    if MODO_TESTE or not TG_TOKEN:
        print(f"[telegram:{metodo}] {dados.get('caption') or dados.get('text', '')}"[:300])
        _TG_FALSO[0] += 1
        if metodo == "sendMediaGroup":
            n = len(json.loads(dados.get("media", "[]")))
            _TG_FALSO[0] += n
            return [{"message_id": _TG_FALSO[0] - k} for k in range(n, 0, -1)]
        return {"message_id": _TG_FALSO[0]}
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{metodo}",
                          data=dados, files=arquivos, timeout=120)
    except Exception as e:
        print(f"Telegram erro: {e}")
        return None
    if not r.ok:
        print(f"Telegram erro: {r.text[:300]}")
        return None
    return r.json().get("result")


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


def oferta_registro_promo(p, ia, palavra, link):
    return {"tipo": "promo", "data": dt.date.today().isoformat(), "palavra": palavra,
            "metrica": METRICA,
            "produto": {"nome": nome_curto(p["nome"], 90), "nome_curto": nome_promo(p, ia, palavra),
                        "preco": p["preco"], "preco_cheio": p["preco_cheio"],
                        "desconto": p["desconto"], "imagem": p["imagem"], "link": link,
                        "nota": p["nota"], "pop": p["vendas"],
                        "beneficios": ia.get("beneficios", [])}}


def cartao_promo(o):
    e = html.escape
    x = o["produto"]
    d = dt.date.fromisoformat(o["data"]).strftime("%d/%m")
    pct = round(x["desconto"] * 100)
    busca = sem_acento(f"{o['palavra']} {x['nome']}".lower())
    msg = (f"Olha esse achadinho: {x['nome_curto']} de {reais(x['preco_cheio'])} por "
           f"{reais(x['preco'])} na Shopee {x['link']}")
    zap = "https://wa.me/?text=" + urllib.parse.quote(msg)
    return (
        f'<article class="card" data-busca="{e(busca, quote=True)}">'
        f'<img src="{e(x["imagem"], quote=True)}" alt="{e(x["nome"], quote=True)}" loading="lazy">'
        f'<div class="info"><div class="data">{e(o["palavra"])} · {d}</div>'
        f'<div class="nome">{e(x["nome"])}</div>'
        f'<div class="preco">{reais(x["preco"])}</div>'
        f'<div class="antes">de <s>{reais(x["preco_cheio"])}</s> · {pct}% de desconto</div>'
        f'<div class="botoes"><a class="btn" href="{e(x["link"], quote=True)}" rel="sponsored noopener">Ver na Shopee</a>'
        f'<a class="btn wa" href="{e(zap, quote=True)}">Enviar no WhatsApp</a></div>'
        f'</div></article>')


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
    cartoes, vistos = [], set()
    for o in ofertas[:OFERTAS_NA_PAGINA]:
        chave = (o.get("produto") or o.get("barato") or {}).get("nome", "")
        if chave in vistos:          # o mesmo produto não aparece duas vezes
            continue
        vistos.add(chave)
        if o.get("tipo") == "promo":
            cartoes.append(cartao_promo(o))
            continue
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
<meta name="description" content="{e(SUBTITULO)}">
<style>{PAGINA_CSS}</style></head>
<body><header><h1>{e(NOME_PAGINA)}</h1>
<p>{e(SUBTITULO)}</p>{botao_tg}</header>
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


def gerar_painel(entregas, texto_whatsapp_dia):
    """Página só sua (não tem link na página pública): vídeos do dia + textos com botão de copiar."""
    e = html.escape
    hoje = dt.date.today().strftime("%d/%m")
    blocos = []
    sem_ia = [x for x in entregas if x.get("ia") is False]
    if sem_ia:
        blocos.append(f'<section class="card aviso"><b>⚠️ A IA não escreveu o roteiro de {len(sem_ia)} '
                      f'vídeo(s) hoje</b>, então eles saíram com o texto padrão.<br>'
                      f'Motivo: {e(IA_INFO.get("erro") or "não identificado")}</section>')
    elif any(x.get("ia") for x in entregas):
        blocos.append(f'<p class="ok">✅ Roteiros escritos pela IA ({e(IA_INFO.get("modelo") or "Gemini")}).</p>')
    for i, x in enumerate(entregas):
        selo_ia = {True: " <small>roteiro da IA</small>", False: " <small>texto padrão</small>"}.get(x.get("ia"), "")
        blocos.append(
            f'<section class="card"><h2>{e(x["palavra"].capitalize())}{selo_ia}</h2>'
            f'<video src="videos/{e(x["arquivo"], quote=True)}" controls playsinline preload="metadata"></video>'
            f'<a class="btn" href="videos/{e(x["arquivo"], quote=True)}" download>Baixar vídeo</a>'
            f'<h3>Legenda (TikTok, Reels, Shopee Vídeo)</h3><textarea id="l{i}" readonly>{e(x["legenda"])}</textarea>'
            f'<button class="btn sec" data-copiar="l{i}">Copiar legenda</button></section>')
    zap = ""
    if texto_whatsapp_dia:
        zap = (f'<section class="card"><h2>Texto do canal do WhatsApp</h2>'
               f'<textarea id="zap" readonly class="alto">{e(texto_whatsapp_dia)}</textarea>'
               f'<button class="btn" data-copiar="zap">Copiar texto do WhatsApp</button>'
               + (f'<a class="btn sec" href="{e(CANAL_WHATSAPP, quote=True)}">Abrir meu canal</a>' if CANAL_WHATSAPP else "")
               + '</section>')
    corpo = "".join(blocos) + zap or '<p class="vazio">Hoje o robô não montou vídeos.</p>'
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Painel do robô</title>
<style>{PAGINA_CSS}
.card{{display:block}}.card h2{{margin:0 0 10px;font-size:20px}}.card h3{{margin:14px 0 6px;font-size:14px;color:var(--sub)}}
video{{width:100%;max-height:70vh;border-radius:12px;background:#000;display:block;margin-bottom:10px}}
textarea{{width:100%;min-height:120px;border-radius:10px;border:1px solid var(--borda);background:var(--bg);color:var(--txt);padding:10px;font-size:14px;line-height:1.4;font-family:inherit}}
textarea.alto{{min-height:220px}}
.card .btn{{margin:8px 8px 0 0;border:0;font-family:inherit;cursor:pointer}}.btn.sec{{background:var(--chip);color:var(--txt)}}
.card h2 small{{font-size:13px;font-weight:600;color:var(--sub);margin-left:6px}}
.aviso{{background:#fff4d6;color:#4a3b00;border:1px solid #f0d27a;line-height:1.5}}
.ok{{margin:0 0 12px;font-size:14px;color:var(--sub)}}
</style></head>
<body><header><h1>Painel do robô</h1><p>Vídeos e textos de {hoje}. Esta página não aparece pro público.</p></header>
<main>{corpo}</main>
<script>
document.querySelectorAll('[data-copiar]').forEach(b=>b.addEventListener('click',async()=>{{
const t=document.getElementById(b.dataset.copiar);
try{{await navigator.clipboard.writeText(t.value);}}catch(e){{t.select();document.execCommand('copy');}}
const o=b.textContent;b.textContent='Copiado ✓';setTimeout(()=>b.textContent=o,1500);}}));
</script></body></html>"""


def publicar_painel(entregas, texto_whatsapp_dia):
    import shutil
    pasta = SITE / "videos"
    pasta.mkdir(parents=True, exist_ok=True)
    for x in entregas:
        x["arquivo"] = f"{dt.date.today():%Y%m%d}-{Path(x['video']).name}"
        shutil.copy(x["video"], pasta / x["arquivo"])
    (SITE / NOME_PAINEL).write_text(gerar_painel(entregas, texto_whatsapp_dia), encoding="utf-8")


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
            "descricao": "Produto de teste. Fácil de limpar, compacto e com ótimo acabamento.",
            "imagem2": "", "imagens": [f"{palavra}-{i}", f"{palavra}-{i}-b"], "nacional": True,
        })
        lista[-1]["preco_cheio"] = round(lista[-1]["preco"] * rnd.uniform(1.1, 2.2), 2)
        lista[-1]["desconto"] = 1 - lista[-1]["preco"] / lista[-1]["preco_cheio"]
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


def com_afiliado(link, sub):
    """O link 'an_redir' do feed só conta a venda pra você se levar o seu affiliate_id.
    O sub_id diz no painel da Shopee de qual vídeo veio o clique."""
    if not AFILIADO_ID or "an_redir" not in link or "affiliate_id=" in link:
        return link
    extra = urllib.parse.urlencode({"affiliate_id": AFILIADO_ID, "sub_id": "-".join(sub)})
    return link + ("&" if "?" in link else "?") + extra


def obter_link(p, usar_feed, sub):
    if MODO_TESTE or usar_feed:
        return com_afiliado(p["oferta"], sub)
    try:
        return link_curto(p["url"], sub)
    except Exception as e:
        print(f"  (link curto falhou, usando link de oferta: {e})")
        return p["oferta"]


def aviso_link(link, usar_feed):
    if usar_feed and "an_redir" in link and "affiliate_id=" not in link:
        return ("Atenção: o link não tem o seu ID de afiliado, então a venda pode não contar pra você. "
                "Crie o segredo SHOPEE_AFFILIATE_ID no GitHub.\n")
    if usar_feed and "an_redir" not in link and "affiliate" not in link:
        return "Atenção: o link não parece ser de afiliado. Me avise.\n"
    return ""


def fazer_promo(produtos, palavra, hist, pasta_dia, rnd, usar_feed, sub):
    p = escolher_promo(produtos, hist)
    if not p:
        return None
    link = obter_link(p, usar_feed, sub)
    ia = roteiro_ia(p)
    print(f"  produto: {p['nome'][:70]} | IA: {'sim' if ia else 'não (texto padrão)'}")
    nome = nome_promo(p, ia, palavra)
    pct = round(p["desconto"] * 100)

    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento(palavra).lower()).strip("-")
    pasta = pasta_dia / slug
    pasta.mkdir(exist_ok=True)
    f1 = baixar_foto(p["imagem"], pasta / "foto1.jpg")
    f2 = f1
    if p.get("imagem2"):
        try:
            f2 = baixar_foto(p["imagem2"], pasta / "foto2.jpg")
        except Exception:
            f2 = f1

    falas, cenas, tipos = [], [], []
    for tipo, fala, tela in roteiro_promo(p, ia, rnd):
        falas.append(fala)
        tipos.append(tipo)
        if tipo == "gancho":
            cenas.append(cena_gancho(p, f1, pct))
        elif tipo == "preco":
            cenas.append(cena_preco(p, f1, pct))
        elif tipo == "beneficios":
            itens = ia["beneficios"]
            cenas.append([cena_beneficios(f1, f2, itens, n) for n in range(1, len(itens) + 1)])
        elif tipo == "prova":
            cenas.append(cena_prova(p, f1))
        else:
            cenas.append(cena_cta(f1))
    video = pasta_dia / f"{slug}.mp4"
    montar_video_v2(cenas, falas, tipos, pasta, video)

    resumo = (f"🎬 {nome} — pronto pra postar\n"
              f"De {reais(p['preco_cheio'])} por {reais(p['preco'])} (-{pct}%)\n"
              + aviso_link(link, usar_feed)
              + f"\nNarração: {' '.join(falas)}")
    return {"titulo": nome, "video": video, "resumo": resumo,
            "legenda": legenda_promo(p, ia, palavra), "ia": bool(ia),
            "canal": canal_promo(p, ia, palavra, link),
            "whatsapp": whatsapp_promo(p, ia, palavra, link),
            "foto_canal": p["imagem"], "ids": [p["id"]],
            "registro": oferta_registro_promo(p, ia, palavra, link)}


def fazer_comparativo(produtos, palavra, hist, pasta_dia, rnd, usar_feed, sub):
    par = escolher_par(produtos, palavra, hist)
    if not par:
        return None
    famoso, barato = par
    link_f = obter_link(famoso, usar_feed, sub)
    link_b = obter_link(barato, usar_feed, sub)

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

    resumo = f"🎬 {palavra} — pronto pra postar\n"
    comissao = barato["comissao"] or barato["preco"] * barato["taxa"]
    if comissao:
        resumo += (f"Comissão estimada na opção barata: {reais(comissao)} "
                   f"({barato['taxa'] * 100:.0f}%)\n")
    resumo += aviso_link(link_b, usar_feed) + f"\nNarração: {' '.join(falas)}"
    return {"titulo": palavra.capitalize(), "video": video, "resumo": resumo,
            "legenda": legenda_social(famoso, barato, palavra),
            "canal": post_canal(famoso, barato, palavra, link_f, link_b),
            "whatsapp": texto_whatsapp(famoso, barato, palavra, link_f, link_b),
            "foto_canal": barato["imagem"], "ids": [famoso["id"], barato["id"]],
            "registro": oferta_registro(famoso, barato, palavra, link_f, link_b)}


def entregar_telegram(r):
    if TG_CHAT:
        with open(r["video"], "rb") as fv:
            telegram("sendVideo", {"chat_id": TG_CHAT, "caption": r["resumo"][:1000],
                                   "supports_streaming": "true"}, {"video": fv})
        avisar("Legenda pra copiar:\n\n" + r["legenda"])
        telegram("sendMessage", {"chat_id": TG_CHAT, "text": "Links:\n\n" + r["canal"],
                                 "parse_mode": "HTML", "disable_web_page_preview": "true"})
    else:
        print(r["resumo"] + "\n\n" + r["legenda"] + "\n\n" + r["canal"])
    if TG_CANAL:
        telegram("sendPhoto", {"chat_id": TG_CANAL, "photo": r["foto_canal"],
                               "caption": r["canal"], "parse_mode": "HTML"})


def preparar_busca():
    """Lê o feed (ou prepara a API). Devolve (usar_feed, palavras de hoje, função palavra -> produtos)."""
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

    def produtos_de(palavra):
        if usar_feed:
            return filtrar_feed(achados.get(palavra, []), palavra)
        if MODO_TESTE:
            return produtos_teste(palavra)
        vistos = {}
        for ordem in (2, 1):          # mais vendidos + relevância
            for p in buscar(palavra, ordem):
                vistos[p["id"]] = p
        return list(vistos.values())

    return usar_feed, palavras, produtos_de


def main():
    if MODO == "kit":
        rodar_kit()
    elif MODO == "postar":
        rodar_postar()
    else:
        rodar_completo()


def rodar_completo(maximo=None):
    """O jeito antigo: escolhe, monta e entrega todos os vídeos de uma vez (sem Flow)."""
    usar_feed, palavras, produtos_de = preparar_busca()
    maximo = maximo or VIDEOS_POR_DIA
    hoje = dt.date.today()
    rnd = random.Random(hoje.toordinal())
    pasta_dia = SAIDA / hoje.isoformat()
    pasta_dia.mkdir(parents=True, exist_ok=True)
    hist = ler_historico()
    ofertas = ler_ofertas()
    blocos_whatsapp, entregas = [], []
    feitos = 0
    sub = ["robo", hoje.strftime("%Y%m%d")]
    fazer = {"telaverde": fazer_tela_verde, "conversa": fazer_conversa,
             "promo": fazer_promo}.get(FORMATO, fazer_comparativo)

    for palavra in palavras:
        if feitos >= maximo:
            break
        print(f"> {palavra}")
        try:
            produtos = produtos_de(palavra)
            r = fazer(produtos, palavra, hist, pasta_dia, rnd, usar_feed, sub)
            if not r:
                print("  nada bom pra essa palavra hoje")
                continue
            entregar_telegram(r)
            blocos_whatsapp.append(r["whatsapp"])
            entregas.append({"palavra": r["titulo"], "video": r["video"], "legenda": r["legenda"],
                             "ia": r.get("ia")})
            for i in r["ids"]:
                hist[i] = hoje.isoformat()
            ofertas.insert(0, r["registro"])
            feitos += 1
        except Exception as e:
            print(f"  erro em '{palavra}': {e}")
            if "Shopee respondeu erro" in str(e) and feitos == 0:
                avisar(f"Robô parou: {e}\nConfira o App ID e o Secret da Shopee nos segredos do GitHub.")
                break

    salvar_historico(hist)
    salvar_ofertas(ofertas)
    texto = ""
    if blocos_whatsapp:
        # um texto só por dia, com todas as ofertas, pra colar no canal do WhatsApp
        texto = (f"*Achadinhos de hoje* ({hoje:%d/%m})\n\n" + "\n\n— — —\n\n".join(blocos_whatsapp)
                 + "\n\n_Links de afiliado · preços de hoje, podem mudar_")
        if PAGINA_URL:
            texto += f"\n\nTodas as ofertas: {PAGINA_URL}"
    publicar_pagina(ofertas)
    publicar_painel(entregas, texto)
    if texto:
        avisar("Pro WhatsApp (copie tudo abaixo e cole no seu canal):")
        avisar(texto)
    if feitos == 0:
        if FORMATO in ("promo", "conversa", "telaverde"):
            avisar("Robô: hoje não achei produto com desconto bom. Tente outras palavras em PALAVRAS "
                   "ou baixe DESCONTO_MINIMO / CURTIDAS_MINIMAS.")
        else:
            avisar("Robô: hoje não achei nenhum par bom. Tente outras palavras em PALAVRAS "
                   "ou baixe ECONOMIA_MINIMA / CURTIDAS_MINIMAS.")
    print(f"Pronto: {feitos} vídeo(s).")


if __name__ == "__main__":
    main()
