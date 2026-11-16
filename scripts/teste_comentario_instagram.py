"""Teste controlado: um comentário no Reel existente, somente com a URL.

O modo padrão apenas consulta perfil, comentários e valida a URL.
A publicação exige duas confirmações internas, e não repete após erro ambíguo.
"""
import os
import sys
import urllib.parse

import requests

GRAPH = "https://graph.facebook.com/v27.0"
MEDIA_ID = "18159644740522144"
USER_ID = "17841475470734841"
USER_NAME = "achadinhos.baratos68"
COMMENT = "https://s.shopee.com.br/5fqN0uKYWz"
PRODUCT_ID = "1655406395"
ITEM_ID = "58272181410"


class ControlledFailure(Exception):
    pass


def fail(reason):
    raise ControlledFailure(reason)


def graph(method, endpoint, token, **fields):
    data = dict(fields, access_token=token)
    try:
        if method == "GET":
            r = requests.get(f"{GRAPH}/{endpoint}", params=data, timeout=40)
        else:
            r = requests.post(f"{GRAPH}/{endpoint}", data=data, timeout=60)
        data = r.json()
    except (ValueError, requests.RequestException):
        fail(f"API Meta: falha de rede ou resposta inválida em {method} {endpoint}")
    if not isinstance(data, dict) or not r.ok or data.get("error"):
        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code", "?") if isinstance(error, dict) else "?"
        subcode = error.get("error_subcode", "?") if isinstance(error, dict) else "?"
        fail(f"API Meta: {method} {endpoint} recusado, HTTP {r.status_code}, código {code}, subcódigo {subcode}")
    return data


def validar_destino():
    """Recusa publicar se não for possível confirmar o mesmo item do Reel."""
    try:
        with requests.get(COMMENT, timeout=(10, 25), allow_redirects=True, stream=True,
                          headers={"User-Agent": "Mozilla/5.0"}) as r:
            final = r.url
            status = r.status_code
            hops = [h.url for h in r.history] + [final]
    except requests.RequestException:
        fail("Link da Shopee não acessível para confirmar qual produto aponta")
    if status >= 400:
        fail(f"Link da Shopee retornou HTTP {status}; produto não confirmado")
    endpoints = "\n".join(hops)
    if PRODUCT_ID not in endpoints or ITEM_ID not in endpoints:
        fail("Link da Shopee não confirmou o produto Onistek esperado (IDs diferentes ou redirecionamento bloqueado)")
    print("DESTINO SHOPEE: produto e item esperados confirmados")
    print("LINK DO COMENTARIO: corresponde exatamente à URL fornecida pelo proprietário")


def listar_comentarios(token):
    next_path = f"{MEDIA_ID}/comments"
    params = {"fields": "id,text,username", "limit": 100}
    for page in range(5):
        dados = graph("GET", next_path, token, **params)
        comments = dados.get("data")
        if not isinstance(comments, list):
            fail("Resposta de comentários inválida; não escrever")
        for c in comments:
            if (c.get("text") or "").strip() == COMMENT:
                print("COMENTARIO JA EXISTE, não enviar duplicado")
                print("ID COMENTARIO:", c.get("id", "desconhecido"))
                return True
        paging = dados.get("paging") or {}
        next_url = paging.get("next", "")
        if not next_url:
            print("COMENTARIOS: nenhuma URL igual encontrada")
            return False
        # Só seguir cursor da nossa mídia, nunca seguir uma URL externa.
        cursor = (paging.get("cursors") or {}).get("after")
        if not cursor:
            fail("Paginação de comentários sem cursor; não escrever")
        next_path = f"{MEDIA_ID}/comments"
        params = {"fields": "id,text,username", "limit": 100, "after": cursor}
    fail("Muitos comentários para validar duplicação; não escrever")


def main():
    token = os.getenv("INSTAGRAM_TOKEN", "").strip()
    if not token or os.getenv("INSTAGRAM_AUTH_MODE", "").strip().lower() != "unified":
        fail("Token ou modo Unified Login não configurado")
    if os.getenv("INSTAGRAM_USER_ID", "").strip() != USER_ID:
        fail("ID Instagram não coincide com a conta do teste")
    if os.getenv("INSTAGRAM_PUBLICAR", "").strip().lower() == "sim":
        fail("Publicação automática não deve estar ativa neste teste")
    perfil = graph("GET", USER_ID, token, fields="id,username")
    if str(perfil.get("id")) != USER_ID or perfil.get("username", "").lower() != USER_NAME:
        fail("Conta Instagram errada")
    print("CONTA: OK")
    reel = graph("GET", MEDIA_ID, token, fields="id,permalink,caption")
    if str(reel.get("id")) != MEDIA_ID or reel.get("permalink") != "https://www.instagram.com/reel/Dfznst3lMED/":
        fail("Reel alvo não confirmado")
    print("REEL: OK")
    validar_destino()
    if listar_comentarios(token):
        return
    publishing = os.getenv("TESTE_COMENTAR", "false").lower() == "true"
    if not publishing:
        print("PRE-VALIDACAO: OK. Nenhum comentario criado")
        return
    if os.getenv("TESTE_CONFIRMACAO", "") != "COMENTAR 1 LINK":
        fail("Confirmação de envio ausente")
    print("Enviando somente a URL em um único POST...")
    try:
        result = graph("POST", f"{MEDIA_ID}/comments", token, message=COMMENT)
    except ControlledFailure:
        print("RESULTADO INDETERMINADO: verificar manualmente antes de qualquer repetição")
        raise
    cid = str(result.get("id") or "")
    if not cid.isdecimal():
        fail("Resposta do envio sem ID numérico; não repetir")
    print("COMENTARIO PUBLICADO: Meta retornou ID", cid)
    print("TEXTO: somente a URL indicada pelo proprietário")
    print("REEL:", reel.get("permalink"))


if __name__ == "__main__":
    try:
        main()
    except ControlledFailure as error:
        print("ERRO CONTROLADO:", error, file=sys.stderr)
        sys.exit(1)
