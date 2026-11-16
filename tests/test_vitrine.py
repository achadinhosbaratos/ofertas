"""Testes de regressão para a vitrine; nenhuma publicação real."""
import unittest

from vitrine import category_for, prepare_offers, product_identity, render_site, safe_shopee


class VitrineTests(unittest.TestCase):
    def setUp(self):
        self.offer = {
            "tipo": "promo",
            "data": "2026-11-15",
            "palavra": "mini processador",
            "produto": {
                "nome": "Mini processador elétrico <Onistek> & Cia",
                "preco": 31.98, "preco_cheio": 89,
                "imagem": "https://cf.shopee.com.br/file/example",
                "link": "https://s.shopee.com.br/5fqN0uKYWz",
            },
        }
        self.comparison = {
            "data": "2026-11-10", "palavra": "fone bluetooth",
            "barato": {
                "nome": "Fone Bluetooth",
                "preco": 45,
                "imagem": "https://cf.shopee.com.br/file/other",
                "link": "https://shope.ee/an_redir?origin_link=https%3A%2F%2Fshopee.com.br%2Fitem",
            },
            "famoso": {"nome": "Referência", "preco": 120},
        }

    def test_render_has_filter_and_search(self):
        page = render_site([self.offer, self.comparison])
        for el in ('id="busca"', 'id="preco-max"', 'id="desconto-min"',
                   'id="ordenar"', 'data-category="Cozinha"',
                   'data-category="Eletrônicos"', 'id="cards"',
                   'id="results-count"', 'data-share-site', 'class="share-item"',
                   'id="favorites-filter"'):
            self.assertIn(el, page)

    def test_escapes_product_names_and_allows_verified_host(self):
        page = render_site([self.offer])
        self.assertIn("Mini processador elétrico &lt;Onistek&gt; &amp; Cia", page)
        self.assertNotIn("<Onistek>", page)
        self.assertIn('href="https://s.shopee.com.br/5fqN0uKYWz"', page)
        self.assertIn('rel="sponsored noopener noreferrer"', page)

    def test_avoids_unsafe_shopee_link(self):
        unsafe = dict(self.offer)
        unsafe["produto"] = dict(self.offer["produto"], link="javascript:alert(1)")
        self.assertEqual(prepare_offers([unsafe]), [])
        self.assertNotIn("javascript:alert(1)", render_site([unsafe]))

    def test_categories_and_promo_discount(self):
        data = prepare_offers([self.offer, self.comparison])
        self.assertEqual([r["category"] for r in data], ["Cozinha", "Eletrônicos"])
        self.assertEqual(data[0]["discount"], 64)
        self.assertEqual(data[1]["discount"], 0)
        self.assertTrue(data[1]["comparison"])
        self.assertEqual(category_for("mop giratório"), "Casa")

    def test_max_offers_and_deduplication(self):
        self.assertEqual(len(prepare_offers([self.offer, self.offer])), 1)
        self.assertEqual(len(prepare_offers([self.offer, self.comparison], max_offers=1)), 1)

    def test_sharing_logic_and_accessibility(self):
        page = render_site([self.offer])
        for marker in ("navigator.share", "navigator.clipboard.writeText",
                       'role="status"', "aria-label", "aria-pressed",
                       "id=\"empty-state\"", "localStorage"):
            self.assertIn(marker, page)
        self.assertIn("Preço de 15/11/2026", page)
        self.assertIn("podem mudar sem aviso", page)

    def test_favorites_and_categories_can_be_combined(self):
        """Fav é filtro adicional e não deve apagar categoria ou controles."""
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] / "vitrine.js").read_text(encoding="utf-8")
        page = render_site([self.offer, self.comparison])
        self.assertIn('onlyFavorites = !onlyFavorites;', script)
        self.assertIn('category = button.dataset.category;', script)
        self.assertIn('(!onlyFavorites || favorites.has(card.id))', script)
        self.assertIn('category === "Todas" || card.dataset.category === category', script)
        self.assertNotIn('const activating = !onlyFavorites;', script)
        self.assertNotIn('onlyFavorites = false;\n    apply();\n  }));', script)
        self.assertIn('id="active-filters"', page)
        self.assertIn('id="all-favorites"', page)
        self.assertIn('Você ainda não salvou favoritos.', script)
        self.assertIn('Nenhum favorito corresponde aos filtros.', script)

    def test_stable_product_identity_survives_affiliate_link_change(self):
        original = "https://shopee.com.br/product/1655406395/58272181410"
        redirect = ("https://shope.ee/an_redir?origin_link="
                    "https%3A%2F%2Fshopee.com.br%2Fproduct%2F1655406395%2F58272181410")
        product = {"nome": "Processador", "url": original, "id": "58272181410"}
        self.assertEqual(product_identity(product, redirect), "shopee-1655406395-58272181410")
        self.assertEqual(product_identity(product, "https://s.shopee.com.br/nova-url"),
                         "shopee-1655406395-58272181410")
        self.assertEqual(product_identity({"nome": "Processador"}, redirect),
                         "shopee-1655406395-58272181410")

    def test_fallback_identity_uses_item_id_or_name_not_affiliate_link(self):
        product = {"nome": "Produto teste", "id": "58272181410"}
        self.assertEqual(product_identity(product, "https://s.shopee.com.br/old"),
                         product_identity(product, "https://s.shopee.com.br/new"))
        product = {"nome": "Produto teste"}
        self.assertEqual(product_identity(product, "https://s.shopee.com.br/old"),
                         product_identity(product, "https://s.shopee.com.br/new"))

    def test_legacy_favorites_and_direct_sharing(self):
        from pathlib import Path
        page = render_site([self.offer])
        script = (Path(__file__).resolve().parents[1] / "vitrine.js").read_text(encoding="utf-8")
        self.assertIn("data-legacy-id=", page)
        self.assertIn("card.dataset.legacyId", script)
        self.assertIn("favorites.add(card.id)", script)
        self.assertIn('class="share-menu"', page)
        self.assertIn('class="share-whatsapp"', page)
        self.assertIn('class="share-copy"', page)
        self.assertIn("encodeURIComponent(message)", script)
        self.assertIn('card.querySelector(".shop-link").href', script)

    def test_removable_filter_chips_and_simple_card(self):
        page = render_site([self.offer])
        self.assertIn('id="active-filters"', page)
        self.assertIn("summary.replaceChildren()", page)
        self.assertIn('className = "filter-tag"', page)
        self.assertIn("Remover filtro ", page)
        self.assertIn("Confira na Shopee", page)
        self.assertNotIn("Referência:", page)

    def test_shopee_url_whitelist(self):
        self.assertEqual(safe_shopee("http://shopee.com.br/a"), "")
        self.assertEqual(safe_shopee("https://not-shopee.com.br/a"), "")
        self.assertEqual(safe_shopee("https://shopee.com.br.evil.test/a"), "")
        self.assertEqual(safe_shopee("https://s.shopee.com.br/a"), "https://s.shopee.com.br/a")


if __name__ == "__main__":
    unittest.main()
