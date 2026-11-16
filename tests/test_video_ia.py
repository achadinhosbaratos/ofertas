"""Regressões de geração automática sem chamadas ao Gemini ou ao Telegram."""

import base64
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import bot
import video_ia


class VideoIATests(unittest.TestCase):
    def test_limite_e_produto_repetido(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = Path(tmp) / "video_ia.json"
            self.assertTrue(video_ia.reservar_geracao(arquivo, "um", 2))
            self.assertFalse(video_ia.reservar_geracao(arquivo, "um", 2))
            self.assertTrue(video_ia.reservar_geracao(arquivo, "dois", 2))
            self.assertFalse(video_ia.reservar_geracao(arquivo, "tres", 2))
            arquivo.write_text('{"data":"2000-01-01","produtos":["um","dois"]}', encoding="utf-8")
            self.assertTrue(video_ia.reservar_geracao(arquivo, "um", 2))

    @patch("video_ia.requests.post")
    def test_manda_foto_real_e_le_video_inline(self, post):
        dados = b"mp4 simulado"
        post.return_value.json.return_value = {
            "status": "completed",
            "steps": [{"type": "model_output", "content": [
                {"type": "video", "mime_type": "video/mp4",
                 "data": base64.b64encode(dados).decode()},
            ]}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "clipe.mp4"
            video_ia.gerar_clipe_omni("chave-teste", "Mostre o produto em uso", ["Zm90bw=="], destino)
            self.assertEqual(destino.read_bytes(), dados)
        corpo = post.call_args.kwargs["json"]
        self.assertEqual(corpo["input"][0], {"type": "image", "data": "Zm90bw==", "mime_type": "image/jpeg"})
        self.assertEqual(corpo["response_format"]["aspect_ratio"], "9:16")
        self.assertEqual(corpo["response_format"]["duration"], "5s")
        self.assertEqual(post.call_count, 1)

    @patch("video_ia.requests.get")
    @patch("video_ia.requests.post")
    def test_baixa_video_quando_api_devolve_uri(self, post, get):
        post.return_value.json.return_value = {
            "status": "completed",
            "steps": [{"type": "model_output", "content": [
                {"type": "video", "mime_type": "video/mp4",
                 "uri": "https://generativelanguage.googleapis.com/v1beta/files/abc-123:download?alt=media"},
            ]}],
        }
        get.side_effect = [Mock(**{"json.return_value": {"state": "ACTIVE"}}), Mock(content=b"mp4 simulado")]
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "clipe.mp4"
            video_ia.gerar_clipe_omni("chave-teste", "Mostre o produto em uso", ["Zm90bw=="], destino)
            self.assertEqual(destino.read_bytes(), b"mp4 simulado")
        self.assertTrue(get.call_args_list[0].args[0].endswith("/files/abc-123"))
        self.assertTrue(get.call_args_list[1].args[0].endswith("/files/abc-123:download"))

    @patch("bot.USAR_IA", True)
    @patch("bot.MODO_TESTE", False)
    @patch("bot.quadros_do_clipe", return_value=[Mock(), Mock(), Mock()])
    @patch("bot.chamar_ia", return_value="")
    def test_conferencia_inconclusiva_recusa_clipe_automatico(self, chamar, quadros):
        foto = Mock()
        aprovado, _ = bot.conferir_produto(Path("clipe.mp4"), {"titulo": "Fatiador", "ficha": {}, "produto": {}},
                                           Path("."), refs=[foto])
        self.assertFalse(aprovado)
        self.assertEqual(chamar.call_args.kwargs["imagens"][0], foto)

    @patch("bot.montar_video_tela_verde", side_effect=[RuntimeError("ffmpeg"), None])
    @patch("bot.baixar_foto", return_value=Image.new("RGB", (50, 50)))
    @patch("bot._clipe_automatico", return_value=Path("clipe.mp4"))
    def test_uma_falha_na_montagem_utiliza_fotos(self, gerar, baixar, montar):
        produto = {"id": "um", "nome": "Fatiador", "desconto": 0.5, "preco": 25,
                   "preco_cheio": 50, "imagem": "foto.jpg", "nota": 4.8, "vendas": 200}
        item = {"produto": produto, "ia": {}, "link": "https://shopee.com.br/item",
                "palavra": "fatiador", "titulo": "Fatiador"}
        with tempfile.TemporaryDirectory() as tmp:
            entrega = bot.produzir_video(item, Path(tmp), random.Random(1))
        self.assertEqual(montar.call_args_list[0].kwargs, {"clipe": Path("clipe.mp4"), "repetir_clipe": False})
        self.assertFalse(montar.call_args_list[1].kwargs)
        self.assertNotIn("geradas por IA", entrega["legenda"])


if __name__ == "__main__":
    unittest.main()
