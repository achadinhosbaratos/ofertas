"""Testes de regressão para estados de publicação e entrega.

Executar com: python -m unittest discover -s tests -v
"""
import unittest
from unittest import mock

import bot


class TelegramReliabilityTests(unittest.TestCase):
    def test_missing_token_never_simulates_success_in_production(self):
        with mock.patch.object(bot, "MODO_TESTE", False), \
             mock.patch.object(bot, "TG_TOKEN", ""), \
             mock.patch.object(bot.requests, "post") as post:
            self.assertIsNone(bot.telegram("sendMessage", {"text": "oi"}))
            post.assert_not_called()

    def test_explicit_test_mode_simulates_without_network(self):
        with mock.patch.object(bot, "MODO_TESTE", True), \
             mock.patch.object(bot, "TG_TOKEN", ""), \
             mock.patch.object(bot.requests, "post") as post:
            result = bot.telegram("sendMessage", {"text": "teste"})
            self.assertIn("message_id", result)
            post.assert_not_called()

    def test_delivery_requires_credentials_in_production(self):
        with mock.patch.object(bot, "MODO_TESTE", False), \
             mock.patch.object(bot, "TG_TOKEN", ""), \
             mock.patch.object(bot, "TG_CHAT", ""), \
             mock.patch.object(bot, "telegram") as send:
            self.assertFalse(bot.entregar_telegram({"video": "/arquivo-inexistente.mp4"}))
            send.assert_not_called()

    def test_main_stops_before_generating_without_telegram(self):
        with mock.patch.object(bot, "MODO_TESTE", False), \
             mock.patch.object(bot, "MODO", "postar"), \
             mock.patch.object(bot, "TG_TOKEN", ""), \
             mock.patch.object(bot, "TG_CHAT", ""), \
             mock.patch.object(bot, "rodar_postar") as run:
            with self.assertRaises(SystemExit) as exc:
                bot.main()
            self.assertEqual(exc.exception.code, 1)
            run.assert_not_called()


class NetworkQueueTests(unittest.TestCase):
    def test_same_video_is_not_enqueued_twice(self):
        estado = {"posts": []}
        with mock.patch.object(bot, "POSTAR_INSTAGRAM", True), \
             mock.patch.object(bot, "IG_TOKEN", "token-de-teste"), \
             mock.patch.object(bot, "ler_redes", return_value=estado), \
             mock.patch.object(bot, "salvar_redes") as save:
            bot.agendar_redes("Oferta", "teste.mp4", "legenda")
            self.assertEqual(save.call_count, 1)
            bot.agendar_redes("Oferta", "teste.mp4", "legenda")
            self.assertEqual(save.call_count, 1)
            self.assertEqual(len(estado["posts"]), 1)


if __name__ == "__main__":
    unittest.main()
