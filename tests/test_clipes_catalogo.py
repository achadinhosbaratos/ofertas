import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from clipes_catalogo import obter_clipe


class CatalogoClipesTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.catalogo = Path(self.pasta.name) / "catalogo.json"
        self.destino = Path(self.pasta.name) / "clipe.mp4"
        self.vendedor = "https://example.com/vendedor.mp4"
        self.heygen = "https://example.com/heygen.mp4"
        self.catalogo.write_text(json.dumps({"123": {"vendedor": self.vendedor, "heygen": self.heygen}}))

    @patch("clipes_catalogo._baixar_clipe")
    def test_vendedor_tem_prioridade(self, baixar):
        self.assertEqual(obter_clipe(self.catalogo, 123, self.destino), (self.destino, "vendedor"))
        baixar.assert_called_once_with(self.vendedor, self.destino)

    @patch("clipes_catalogo._baixar_clipe", side_effect=[ValueError("arquivo indisponível"), None])
    def test_usa_exportado_do_heygen_quando_vendedor_falha(self, baixar):
        self.assertEqual(obter_clipe(self.catalogo, 123, self.destino), (self.destino, "heygen"))
        self.assertEqual([call.args[0] for call in baixar.call_args_list], [self.vendedor, self.heygen])

    @patch("clipes_catalogo._baixar_clipe")
    def test_produto_sem_clipe_fica_com_fotos(self, baixar):
        self.assertEqual(obter_clipe(self.catalogo, 456, self.destino), (None, None))
        baixar.assert_not_called()
