"""Geração opcional de um clipe curto de produto pela API Gemini."""

import base64
import datetime as dt
import json
import re
import time
from urllib.parse import urlsplit

import requests


GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
MODELO_VIDEO = "gemini-omni-1.2-flash"
DURACAO_CLIPE = 5


def reservar_geracao(arquivo, produto_id, limite):
    """Registra a tentativa antes do POST para não cobrar novamente pelo mesmo produto."""
    hoje = dt.date.today().isoformat()
    try:
        estado = json.loads(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        estado = {"data": hoje, "produtos": []}

    if not isinstance(estado, dict) or not isinstance(estado.get("produtos"), list):
        raise ValueError("controle diário de vídeo inválido")
    produtos = estado["produtos"] if estado.get("data") == hoje else []
    if len(produtos) >= limite or str(produto_id) in produtos:
        return False

    novo_estado = {"data": hoje, "produtos": produtos + [str(produto_id)]}
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps(novo_estado, indent=2) + "\n", encoding="utf-8")
    temporario.replace(arquivo)
    return True


def _baixar_video(uri, headers, chave):
    # A resposta é externa. Use só o ID e reconstrua a URL no host conhecido.
    caminho = urlsplit(uri).path
    arquivo = re.fullmatch(r"/?(?:v1beta/)?(files/[A-Za-z0-9_-]+)(?::download)?", caminho)
    if not arquivo:
        raise ValueError("referência do vídeo inválida")
    url = f"{GEMINI_API}/{arquivo[1]}"
    prazo = time.monotonic() + 45
    while time.monotonic() < prazo:
        resposta = requests.get(url, headers=headers, timeout=(5, 12), allow_redirects=False)
        resposta.raise_for_status()
        arquivo_info = resposta.json()
        estado = arquivo_info.get("state") if isinstance(arquivo_info, dict) else None
        if estado == "ACTIVE":
            # A transferência pode redirecionar para uma URL do Google Storage.
            # A chave fica na requisição original e não no cabeçalho de redirecionamento.
            video = requests.get(f"{url}:download", params={"alt": "media", "key": chave},
                                 timeout=(5, 45))
            video.raise_for_status()
            return video.content
        if estado == "FAILED":
            raise RuntimeError("processamento do clipe falhou")
        time.sleep(3)
    raise TimeoutError("arquivo do clipe não ficou pronto a tempo")


def gerar_clipe_omni(chave, prompt, imagens_b64, destino):
    """Solicita um clipe de cinco segundos e salva o MP4 retornado pela API."""
    imagens = [{"type": "image", "data": foto, "mime_type": "image/jpeg"}
               for foto in imagens_b64]
    if not imagens:
        raise ValueError("faltam as fotos de referência")

    corpo = {
        "model": MODELO_VIDEO,
        "input": imagens + [{"type": "text", "text": prompt}],
        "response_format": {
            "type": "video", "aspect_ratio": "9:16", "resolution": "720p",
            "duration": f"{DURACAO_CLIPE}s", "delivery": "uri",
        },
    }
    headers = {"x-goog-api-key": chave}
    resposta = requests.post(f"{GEMINI_API}/interactions", headers=headers, json=corpo,
                              timeout=(10, 180), allow_redirects=False)
    resposta.raise_for_status()
    interacao = resposta.json()
    if not isinstance(interacao, dict) or interacao.get("status") != "completed":
        raise RuntimeError("geração do clipe não concluída")

    video = next((parte for etapa in interacao.get("steps", [])
                  if isinstance(etapa, dict) and etapa.get("type") == "model_output"
                  for parte in etapa.get("content", [])
                  if isinstance(parte, dict) and parte.get("type") == "video"
                  and parte.get("mime_type") == "video/mp4"), {})
    if video.get("data"):
        dados = base64.b64decode(video["data"], validate=True)
    elif video.get("uri"):
        dados = _baixar_video(video["uri"], headers, chave)
    else:
        raise ValueError("Gemini não retornou um vídeo")

    if not dados:
        raise ValueError("Gemini retornou um vídeo vazio")
    destino.write_bytes(dados)
    return destino
