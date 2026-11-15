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


class VideoRetentionTests(unittest.TestCase):
    def test_keep_pending_mp4_and_remove_completed_from_local_cache(self):
        import tempfile
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            videos = site / "videos"
            videos.mkdir(parents=True)
            (videos / "aguardando.mp4").write_bytes(b"pendente")
            (videos / "concluido.mp4").write_bytes(b"concluido")
            redes = Path(tmp) / "redes.json"
            redes.write_text(json.dumps({"posts": [
                {"arquivo": "aguardando.mp4", "instagram": "erro", "youtube": "postado"},
                {"arquivo": "concluido.mp4", "instagram": "postado", "youtube": "postado"},
            ]}), encoding="utf-8")
            with mock.patch.object(bot, "SITE", site), mock.patch.object(bot, "REDES", redes):
                bot.limpar_videos_para_arquivo()
            self.assertTrue((videos / "aguardando.mp4").exists())
            self.assertFalse((videos / "concluido.mp4").exists())

    def test_corrupted_queue_does_not_delete_pending_videos(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            videos = site / "videos"
            videos.mkdir(parents=True)
            arquivo = videos / "aguardando.mp4"
            arquivo.write_bytes(b"pendente")
            redes = Path(tmp) / "redes.json"
            redes.write_text("{inválido", encoding="utf-8")
            with mock.patch.object(bot, "SITE", site), mock.patch.object(bot, "REDES", redes):
                with self.assertRaises(ValueError):
                    bot.limpar_videos_para_arquivo()
            self.assertTrue(arquivo.exists())

    def test_restore_mp4_from_pages_when_artifact_unavailable(self):
        import tempfile
        from pathlib import Path

        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.ok = True
        response.headers = {"Content-Type": "video/mp4"}
        response.iter_content.return_value = [b"mp4-test"]
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "site" / "videos" / "teste.mp4"
            with mock.patch.object(bot, "PAGINA_URL", "https://example.org/ofertas/"), \
                 mock.patch.object(bot.requests, "get", return_value=response) as get:
                self.assertTrue(bot.recuperar_video_publicado("teste.mp4", dest))
                self.assertFalse(bot.recuperar_video_publicado("../secreto.mp4", dest))
            self.assertEqual(dest.read_bytes(), b"mp4-test")
            self.assertEqual(get.call_count, 1)

    def test_youtube_can_retry_a_video_from_yesterday(self):
        import datetime as dt
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "site"
            video = site / "videos" / "teste.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"mp4-test")
            registro = {"data": (dt.date.today() - dt.timedelta(days=1)).isoformat(),
                        "arquivo": "teste.mp4", "titulo": "Produto",
                        "legenda": "legenda", "youtube": "erro", "instagram": "postado"}
            estado = {"posts": [registro]}
            with mock.patch.object(bot, "SITE", site), \
                 mock.patch.object(bot, "YT_CLIENT_ID", "client"), \
                 mock.patch.object(bot, "YT_CLIENT_SECRET", "secret"), \
                 mock.patch.object(bot, "YT_REFRESH_TOKEN", "refresh"), \
                 mock.patch.object(bot, "ler_redes", return_value=estado), \
                 mock.patch.object(bot, "salvar_redes") as save, \
                 mock.patch.object(bot, "avisar"), \
                 mock.patch.object(bot, "enviar_short_youtube", return_value=("abc", "https://youtube.test/abc")) as send:
                bot.rodar_youtube()
            send.assert_called_once()
            save.assert_called_once()
            self.assertEqual(registro["youtube"], "postado")
            self.assertEqual(registro["youtube_tentativas"], 1)

    def test_expired_instagram_post_is_not_attempted(self):
        import datetime as dt

        registro = {"data": (dt.date.today() - dt.timedelta(days=3)).isoformat(),
                    "arquivo": "antigo.mp4", "titulo": "Produto",
                    "legenda": "texto", "instagram": "erro", "tentativas": 0}
        estado = {"posts": [registro]}
        with mock.patch.object(bot, "POSTAR_INSTAGRAM", True), \
             mock.patch.object(bot, "IG_TOKEN", "ig-token"), \
             mock.patch.object(bot, "ler_redes", return_value=estado), \
             mock.patch.object(bot, "salvar_redes") as save, \
             mock.patch.object(bot, "cuidar_da_chave_ig"), \
             mock.patch.object(bot, "problema"), \
             mock.patch.object(bot, "video_no_ar") as check:
            bot.rodar_instagram()
        check.assert_not_called()
        save.assert_called_once()
        self.assertEqual(registro["instagram"], "desistiu")

    def test_queue_trimming_keeps_pending_entries(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "redes.json"
            estado = {"posts": [
                {"arquivo": "pendente.mp4", "instagram": "erro", "youtube": "postado"},
                *[{"arquivo": f"{i}.mp4", "instagram": "postado", "youtube": "postado"}
                  for i in range(61)]
            ]}
            with mock.patch.object(bot, "REDES", file):
                bot.salvar_redes(estado)
            saved = json.loads(file.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["posts"]), 61)
            self.assertEqual(saved["posts"][0]["arquivo"], "pendente.mp4")


if __name__ == "__main__":
    unittest.main()
