"""Um único teste controlado do Instagram via Unified Login.

Sem argumentos de publicação faz SOMENTE leitura e validação.
Nunca usa o agendamento normal nem modifica fila/histórico.
"""
import os
import sys
import time

import requests

API = "https://graph.facebook.com/v27.0"
EXPECTED_IG_USER_ID = "17841475470734841"
EXPECTED_USERNAME = "achadinhos.baratos68"
VIDEO_URL = "https://achadinhosbaratos.github.io/ofertas/videos/20261115-mini-processador.mp4"
MARCADOR = "TesteIntegracaoAB20261116"
LEGENDA = (
    "🧪 Teste controlado da integração do Achadinhos Baratos com o Instagram. "
    "Vídeo de demonstração; não é uma oferta atual. "
    f"#{MARCADOR}"
)


class ErroSeguro(RuntimeError):
    """Falha com mensagem que nunca contém token nem resposta integral da API."""


def falhar(mensagem):
    raise ErroSeguro(mensagem)


def requisicao_graph(metodo, caminho, token, **dados):
    """Graph API com tratamento sanitizado de erros e nenhuma impressão do token."""
    dados["access_token"] = token
    url = f"{API}/{caminho.lstrip('/')}"
    try:
        if metodo == "GET":
            r = requests.get(url, params=dados, timeout=(10, 40))
        elif metodo == "POST":
            r = requests.post(url, data=dados, timeout=(10, 90))
        else:
            falhar("Método HTTP inválido")
        try:
            resposta = r.json()
        except ValueError:
            falhar(f"Resposta não JSON de Graph API (HTTP {r.status_code})")
    except requests.RequestException:
        falhar(f"Falha de conexão com Graph API em {metodo} (sem detalhes sensíveis)")
    if not isinstance(resposta, dict):
        falhar(f"Resposta inesperada de Graph API (HTTP {r.status_code})")
    erro = resposta.get("error")
    if not r.ok or erro:
        codigo = erro.get("code", "?") if isinstance(erro, dict) else "?"
        subcodigo = erro.get("error_subcode", "?") if isinstance(erro, dict) else "?"
        falhar(f"Graph API recusou {metodo} (HTTP {r.status_code}, código {codigo}, subcódigo {subcodigo})")
    return resposta


def validar_video():
    """Confere que a Meta poderá baixar um MP4 sem autenticação."""
    try:
        with requests.get(
            VIDEO_URL,
            headers={"Range": "bytes=0-2047"},
            stream=True,
            timeout=(10, 40),
            allow_redirects=True,
        ) as resposta:
            if not resposta.ok:
                falhar(f"Vídeo não disponível publicamente (HTTP {resposta.status_code})")
            tipo = resposta.headers.get("Content-Type", "").split(";")[0].lower()
            if tipo not in {"video/mp4", "application/octet-stream", "binary/octet-stream"}:
                falhar(f"Tipo de conteúdo não é MP4: {tipo or 'desconhecido'}")
            primeiro = next(resposta.iter_content(chunk_size=2048), b"")
            if b"ftyp" not in primeiro[:32]:
                falhar("Arquivo remoto não tem assinatura MP4 válida")
    except requests.RequestException:
        falhar("Vídeo não está acessível publicamente pelo GitHub Pages")
    print("MP4 público: OK")


def listar_reels(token, usuario_id):
    """Falha se não conseguir verificar duplicatas antes da publicação."""
    lista = requisicao_graph(
        "GET", f"{usuario_id}/media", token,
        fields="id,caption,permalink", limit=100
    )
    posts = lista.get("data")
    if not isinstance(posts, list):
        falhar("Não consegui consultar posts existentes para verificar duplicações")
    for post in posts:
        if MARCADOR in (post.get("caption") or ""):
            print("PUBLICAÇÃO JÁ EXISTE: não será criado outro Reel.")
            if post.get("permalink"):
                print("Reel:", post["permalink"])
            return True
    return False


def verificar_conta(token, usuario_id):
    if usuario_id != EXPECTED_IG_USER_ID:
        falhar("ID do Instagram é diferente da conta autorizada para este teste")
    perfil = requisicao_graph("GET", usuario_id, token, fields="id,username")
    if (str(perfil.get("id")) != EXPECTED_IG_USER_ID or
            (perfil.get("username") or "").lower() != EXPECTED_USERNAME):
        falhar("Token não confirmou a conta @achadinhos.baratos68")
    print("Conta Instagram correta: OK")


def publicar_uma_vez(token, usuario_id):
    """Faz criação de container e uma única chamada de publicação, sem retry."""
    novo = requisicao_graph(
        "POST", f"{usuario_id}/media", token,
        media_type="REELS", video_url=VIDEO_URL, caption=LEGENDA,
        share_to_feed="false",
    )
    container_id = str(novo.get("id", ""))
    if not container_id.isdecimal():
        falhar("Meta não devolveu ID de container válido")
    print("Container criado; aguardando processamento...")
    for _ in range(40):
        time.sleep(8)
        st = requisicao_graph("GET", container_id, token, fields="status_code,status")
        codigo = st.get("status_code")
        if codigo == "FINISHED":
            break
        if codigo in ("ERROR", "EXPIRED"):
            falhar(f"Meta não processou o vídeo (estado {codigo})")
    else:
        falhar("Processamento não terminou; não executar novamente sem conferir")
    print("Vídeo processado. Enviando solicitação única de publicação...")
    try:
        publicado = requisicao_graph("POST", f"{usuario_id}/media_publish", token, creation_id=container_id)
    except ErroSeguro:
        print("RESULTADO INCERTO: verificar primeiro o Instagram. NÃO repetir este teste automaticamente.")
        raise
    id_midia = str(publicado.get("id") or "")
    if not id_midia.isdecimal():
        falhar("Resposta de publicação sem ID de mídia; verificar o Instagram antes de repetir")
    print("PUBLICADO: Instagram confirmou media ID", id_midia)
    try:
        link = requisicao_graph("GET", id_midia, token, fields="permalink").get("permalink")
        if link:
            print("LINK DO REEL:", link)
    except ErroSeguro:
        print("Publicação confirmada; link não disponível agora. Verifique o perfil manualmente.")


def main():
    publicar = os.getenv("TESTE_PUBLICAR", "false").strip().lower() == "true"
    confirmacao = os.getenv("TESTE_CONFIRMACAO", "")
    if publicar and confirmacao != "PUBLICAR 1 REEL":
        falhar("Confirmação ausente. Para publicação pública, digite PUBLICAR 1 REEL")
    if os.getenv("INSTAGRAM_AUTH_MODE", "").lower() != "unified":
        falhar("INSTAGRAM_AUTH_MODE deve ser unified")
    if os.getenv("INSTAGRAM_PUBLICAR", "").strip().lower() == "sim":
        falhar("Desative INSTAGRAM_PUBLICAR; o teste deve ser separado da automação")
    token = os.getenv("INSTAGRAM_TOKEN", "").strip()
    usuario_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
    if not token:
        falhar("INSTAGRAM_TOKEN não configurado")
    if not usuario_id:
        falhar("INSTAGRAM_USER_ID não configurado")
    verificar_conta(token, usuario_id)
    validar_video()
    existe = listar_reels(token, usuario_id)
    if existe:
        return
    if not publicar:
        print("PRÉ-VALIDAÇÃO APROVADA; nenhuma publicação foi realizada.")
        print("O próximo passo é usar o formulário manual de teste, se desejar.")
        return
    print("CONFIRMADO: tentativa única de Reel PÚBLICO na conta @achadinhos.baratos68")
    publicar_uma_vez(token, usuario_id)


if __name__ == "__main__":
    try:
        main()
    except ErroSeguro as e:
        print("ERRO CONTROLADO:", e, file=sys.stderr)
        sys.exit(1)
