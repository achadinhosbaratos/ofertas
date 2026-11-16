"""Regressões do vídeo de oferta compacto."""

import unittest
from unittest.mock import patch

import bot


class VideoOfertaTests(unittest.TestCase):
    def setUp(self):
        self.produto = {"preco": 25.90}
        self.ia = {
            "nome_curto": "Fatiador",
            "pergunta_amiga": "Lupi, como faz?",
            "como_funciona": "O fatiador corta legumes em rodelas.",
        }

    def test_roteiro_de_fotos_abre_com_produto_e_preco(self):
        falas = bot.roteiro_tela_verde(self.produto, self.ia, "fatiador")
        self.assertEqual([fala["secao"] for fala in falas], ["abertura", "cta"])
        self.assertTrue(falas[0]["fala"].startswith("Fatiador por "))
        self.assertIn(bot.reais_curto(self.produto["preco"]), falas[0]["fala"])
        self.assertTrue(all(fala["quem"] == "lupi" for fala in falas))

    def test_roteiro_com_clipe_ressalta_o_uso_e_vai_para_a_oferta(self):
        falas = bot.roteiro_tela_verde(self.produto, self.ia, "fatiador", com_clipe=True)
        self.assertEqual([fala["fala"] for fala in falas], [
            self.ia["como_funciona"], "Confira a oferta no link do perfil.",
        ])

    def test_roteiro_sem_descricao_usa_o_preco(self):
        falas = bot.roteiro_tela_verde(self.produto, {}, "fatiador", com_clipe=True)
        self.assertTrue(falas[0]["fala"].startswith("Fatiador por "))
        self.assertIn(bot.reais_curto(self.produto["preco"]), falas[0]["fala"])

    @patch("bot.pilula", wraps=bot.pilula)
    def test_cartao_de_abertura_exibe_nome_e_preco(self, pilula):
        cartao = bot._cartao_abertura("Fatiador", self.produto["preco"])
        textos = [chamada.args[1] for chamada in pilula.call_args_list]
        self.assertEqual(textos, ["Fatiador", "R$\u00a025,90"])
        self.assertIsNotNone(cartao.getbbox())
