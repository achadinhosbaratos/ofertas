"""Clipes de produto cadastrados para reutilização no gerador."""

import json
import subprocess
from urllib.parse import urlsplit

import requests


MAX_BYTES = 20_000_000


def obter_clipe(arquivo, produto_id, destino):
    """Tenta o vídeo do vendedor e depois o clipe HeyGen já cadastrado para o mesmo item."""
    try:
        catalogo = json.loads(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError):
        print("  catálogo de clipes indisponível. Usando a montagem padrão.")
        return None, None

    item = catalogo.get(str(produto_id)) if isinstance(catalogo, dict) else None
    if not isinstance(item, dict):
        return None, None

    for origem in ("vendedor", "heygen"):
        url = item.get(origem)
        if not isinstance(url, str) or not url:
            continue
        try:
            _baixar_clipe(url, destino)
            return destino, origem
        except (requests.RequestException, OSError, ValueError, subprocess.SubprocessError):
            destino.unlink(missing_ok=True)
            print(f"  clipe de {origem} indisponível ou inválido.")
    return None, None


def _baixar_clipe(url, destino):
    endereco = urlsplit(url)
    if endereco.scheme != "https" or not endereco.hostname or endereco.username or endereco.password:
        raise ValueError("URL direta HTTPS esperada")
    with requests.get(url, stream=True, timeout=(5, 12), allow_redirects=False) as resposta:
        resposta.raise_for_status()
        if resposta.status_code != 200:
            raise ValueError("URL não entregou o arquivo diretamente")
        tamanho = 0
        with destino.open("wb") as saida:
            for bloco in resposta.iter_content(chunk_size=65536):
                tamanho += len(bloco)
                if tamanho > MAX_BYTES:
                    raise ValueError("clipe maior que 20 MB")
                saida.write(bloco)

    resultado = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "json", str(destino)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    dados = json.loads(resultado.stdout)
    video = dados.get("streams") or []
    if not video or not video[0].get("width") or not video[0].get("height"):
        raise ValueError("arquivo sem imagem de vídeo")
    duracao = float(dados.get("format", {}).get("duration") or 0)
    if not 1 <= duracao:
        raise ValueError("clipe muito curto")
