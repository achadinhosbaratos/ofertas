# Robô de Achadinhos Shopee

Automação para selecionar ofertas do feed de afiliados Shopee, gerar vídeos verticais com narração, publicar a página de ofertas e distribuir conteúdo nos canais configurados.

## Fluxo automático

1. Lê o feed configurado em `SHOPEE_FEED_URL` (ou usa a API oficial quando configurada).
2. Filtra ofertas, evita repetir produtos recentes e cria links de afiliado.
3. Gera vídeos 9:16 com imagens, textos e narração em português.
4. Envia o vídeo e a legenda para o chat privado do Telegram.
5. Atualiza a página de ofertas no GitHub Pages.
6. Se o Instagram estiver configurado, publica o vídeo como Reel pela API oficial da Meta.

**Google Flow está desativado por padrão.** O vídeo é montado automaticamente pelo próprio robô; não é necessário gerar ou devolver clipes manualmente.

## Segredos do GitHub

Em **Settings → Secrets and variables → Actions**, configure os segredos aplicáveis:

| Segredo | Para que serve |
|---|---|
| `SHOPEE_FEED_URL` | URL do feed de produtos do painel de afiliados Shopee |
| `SHOPEE_AFFILIATE_ID` | ID de afiliado, quando o link do feed exige esse parâmetro |
| `SHOPEE_APP_ID` e `SHOPEE_SECRET` | Alternativa de busca pela Open API da Shopee |
| `TELEGRAM_TOKEN` | Token do bot do Telegram |
| `TELEGRAM_CHAT_ID` | ID do chat privado para receber vídeos e alertas |
| `TELEGRAM_CANAL` | Opcional: @username ou ID do canal público |
| `GEMINI_API_KEY` | Opcional: roteiros com Gemini |
| `INSTAGRAM_TOKEN` | Opcional: publicação automática de Reels |
| `YOUTUBE_CLIENT_ID` | OAuth do Google para upload automático de Shorts |
| `YOUTUBE_CLIENT_SECRET` | Segredo OAuth do Google |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token OAuth com escopo `youtube.upload` e acesso offline |
| `GH_PAT_SEGREDOS` | Opcional: atualizar o segredo do Instagram após renovação |

Nunca coloque tokens ou chaves diretamente no código, issues ou logs.

### Telegram

O bot precisa estar iniciado e ter acesso ao chat privado indicado em `TELEGRAM_CHAT_ID`. Para publicar em um canal, adicione o bot como administrador com permissão de publicar mensagens. Um erro 403 no canal não é resolvido alterando o código: é preciso corrigir a associação/permissão do bot no próprio Telegram.

### Instagram

A publicação exige conta profissional compatível, aplicativo Meta configurado e token válido com as permissões necessárias. Sem `INSTAGRAM_TOKEN`, o robô mantém a geração de vídeos e a página, mas não publica Reels. A configuração do token é externa ao repositório.

## Agendamento

O workflow `.github/workflows/robo.yml` executa o robô nos horários definidos em UTC, correspondentes aos horários de Brasília comentados no arquivo. Também pode ser iniciado manualmente em **Actions → Robô de achadinhos → Run workflow**.

O robô está configurado para tentar publicar 3 vídeos por dia, às 11:47, 15:47 e 19:47 (horário de Brasília). Cada horário tem uma execução de reserva uma hora depois. O contador diário impede que as reservas gerem vídeos extras.

## Testes

O workflow `.github/workflows/ci.yml` executa verificações de sintaxe Python, integridade dos arquivos JSON e configuração padrão sem Google Flow em pushes e pull requests. Esses testes não publicam conteúdo nem validam credenciais externas da Shopee, Telegram ou Meta.

## Plataformas e publicação automática

- **Instagram:** publicação de Reels implementada; depende de conta profissional, permissões da Meta e `INSTAGRAM_TOKEN` válido.
- **Telegram:** envio do vídeo ao chat e publicação de imagem/texto no canal implementados; depende de `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` e permissões de administrador em `TELEGRAM_CANAL`.
- **TikTok:** a publicação direta exige Content Posting API, escopo `video.publish`, OAuth e auditoria para sair do modo privado. As diretrizes exigem que a aplicação mostre as opções atuais de privacidade/interação e recolha consentimento antes de publicar; um job headless do GitHub Actions não cumpre esse fluxo sem uma interface de confirmação. Por isso, não será ativada publicação silenciosa que viole as regras da plataforma.
- **YouTube Shorts:** upload resumable e publicação pública implementados. Configure `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` e `YOUTUBE_REFRESH_TOKEN` (OAuth com escopo `youtube.upload` e acesso offline). Projetos não auditados podem ter uploads limitados à visualização privada; a auditoria do Google é necessária para liberar publicação pública. Para OAuth, não deixe a tela de consentimento externa em **Testing** para operação contínua: tokens de atualização emitidos nesse modo expiram em 7 dias. Publique/configure o app para produção e conclua as verificações exigidas pelo Google.
- **WhatsApp:** hoje o robô prepara o texto com links; não publica no canal. A API WhatsApp Business Cloud não equivale à publicação em Canais do WhatsApp e não oferece uma operação genérica para postar em um canal. Não será usado envio não oficial/automação de navegador.

A configuração de três vídeos por dia controla a produção e as tentativas agendadas; não garante três publicações em todas as redes quando faltarem credenciais, permissões, produtos elegíveis ou quando uma API externa recusar o conteúdo.
- A publicação no Telegram privado e no canal depende dos segredos e das permissões do bot.
- A publicação no Instagram depende do token e da configuração da Meta.
