# Robô de Achadinhos Shopee

Automação para selecionar ofertas do feed de afiliados Shopee, gerar vídeos verticais com narração, publicar a página de ofertas e distribuir conteúdo nos canais configurados.

## Fluxo automático

1. Lê o feed configurado em `SHOPEE_FEED_URL` (ou usa a API oficial quando configurada).
2. Filtra ofertas, evita repetir produtos recentes e cria links de afiliado.
3. Gera vídeos 9:16 com imagens, textos e narração em português.
4. Envia o vídeo e a legenda para o chat privado do Telegram.
5. Atualiza a página de ofertas no GitHub Pages.
6. Se o Instagram estiver configurado **e a publicação estiver explicitamente ativada**, publica o vídeo como Reel pela API oficial da Meta.

**Google Flow está desativado por padrão.** O vídeo é montado automaticamente pelo próprio robô; não é necessário gerar ou devolver clipes manualmente.

## Geração de vídeos sem custo de clipe

O agendamento monta os vídeos a partir das fotos do anúncio, com narração, preço e chamada. O workflow fixa `VIDEO_IA_MAX_POR_DIA` em `0` para manter desativada a geração de clipes pela API paga do Gemini.

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

### Links automáticos de afiliado da Shopee

Quando `SHOPEE_APP_ID` e `SHOPEE_SECRET` estiverem configurados como **Secrets** do GitHub, o bot gera automaticamente links curtos rastreáveis com `generateShortLink`, **mesmo que os produtos venham de `SHOPEE_FEED_URL`**. O vídeo, o registro da oferta, o Telegram e o comentário do Instagram passam a usar o mesmo link gerado. A chamada inclui `subIds` de campanha para rastreamento (o mesmo link também pode ser usado no site e no Telegram).

Se a API recusar a criação de um link, o bot não substitui silenciosamente por URL sem tracking. As credenciais precisam ser liberadas pela Shopee para uso da Open API. Para manter a operação atual do feed enquanto configura a API, os segredos podem permanecer ausentes; nesse caso a geração antiga permanece, mas um link sem atribuição verificada **não é usado nos comentários automáticos**.

**Não use** `SHOPEE_AFFILIATE_ID` como substituto de `SHOPEE_APP_ID` e `SHOPEE_SECRET`: são conceitos diferentes. Nunca coloque seu segredo no README ou no código.

### Instagram — novo Unified Login (SUAT)

A publicação exige conta profissional, app Meta e token com as permissões `instagram_basic` e `instagram_content_publish` para a conta de Instagram conectada.

1. Na Meta, configure o login unificado e gere o token no seu próprio app. **Nunca envie esse token em mensagens ou screenshots.**
2. Em **GitHub → Settings → Secrets and variables → Actions → Secrets**, crie `INSTAGRAM_TOKEN` com o valor do token. Se já existir, atualize. Confirme se ele deve ser um segredo do repositório ou do ambiente `github-pages` (este tem precedência se o job usa esse ambiente).
3. Na aba **Variables**, crie `INSTAGRAM_AUTH_MODE` = `unified` e `INSTAGRAM_USER_ID` com o ID numérico da conta profissional exibido no painel da Meta (não é o App ID).
4. Deixe `INSTAGRAM_PUBLICAR` **ausente** ou igual a `nao`. Assim o robô **não posta** enquanto você valida a autenticação.
5. Em **Actions → Homologar integrações (sem publicar)** execute o workflow. Ele testa a leitura do perfil com `graph.facebook.com/v27.0`, sem enviar Reels nem mensagens.
6. Somente após validação e autorização para publicar, altere a variável `INSTAGRAM_PUBLICAR` para `sim`. Não ative antes da aprovação da alteração de código.

**Token SUAT:** usa a Graph API do Facebook (`graph.facebook.com`) e não usa `ig_refresh_token`. O robô **não tenta renovar automaticamente** o token Unified Login, pois seu ciclo de vida difere do token legado; acompanhe a situação no painel da Meta.

**Token legado:** mantenha `INSTAGRAM_AUTH_MODE=instagram` para utilizar `graph.instagram.com`; a renovação de 60 dias continua aplicável somente a esse modo.

A verificação de leitura do perfil não comprova as permissões de publicação. A primeira publicação real ainda precisa de validação controlada.

#### Comentário automático apenas com o link de afiliado

Após publicar um Reel, o robô poderá criar **um comentário contendo somente a URL de afiliado do produto daquele vídeo** (sem introduções, emojis ou hashtags), desde que:

- `INSTAGRAM_PUBLICAR=sim` e `INSTAGRAM_COMENTAR_LINK=sim` estejam configuradas no workflow e a API da Meta aceite a permissão `instagram_manage_comments` para o login unificado;
- exista uma URL HTTPS válida da Shopee associada à oferta. O código usa `produto.link` em vídeos individuais e `barato.link` nos comparativos. Não inventa links nem publica `shope.ee/an_redir` sem `affiliate_id`;
- a verificação de comentários existentes seja concluída, para impedir duplicações. Caso a resposta seja incerta, **o robô não repete automaticamente** a operação.

O opt-in `INSTAGRAM_COMENTAR_LINK` permanece desligado até confirmar a permissão e a criação do comentário em um Reel de teste. O recurso **não foi ativado na produção**. Comentários do Instagram geralmente não tornam a URL clicável, mas ela poderá ser copiada.

## Agendamento

O workflow `.github/workflows/robo.yml` executa o robô nos horários definidos em UTC, correspondentes aos horários de Brasília comentados no arquivo. Também pode ser iniciado manualmente em **Actions → Robô de achadinhos → Run workflow**.

O robô está configurado para tentar publicar 3 vídeos por dia, às 11:47, 15:47 e 19:47 (horário de Brasília). Cada horário tem uma execução de reserva uma hora depois. O contador diário impede que as reservas gerem vídeos extras.

## Testes

O workflow `.github/workflows/ci.yml` executa verificações de sintaxe Python, integridade dos arquivos JSON e configuração padrão sem Google Flow em pushes e pull requests. Esses testes não publicam conteúdo nem validam credenciais externas da Shopee, Telegram ou Meta.

## Plataformas e publicação automática

- **Instagram:** publicação de Reels implementada; depende de conta profissional, permissões da Meta, `INSTAGRAM_TOKEN` válido e ativação explícita por `INSTAGRAM_PUBLICAR=sim`.
- **Telegram:** envio do vídeo ao chat e publicação de imagem/texto no canal implementados; depende de `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` e permissões de administrador em `TELEGRAM_CANAL`.
- **TikTok:** a publicação direta exige Content Posting API, escopo `video.publish`, OAuth e auditoria para sair do modo privado. As diretrizes exigem que a aplicação mostre as opções atuais de privacidade/interação e recolha consentimento antes de publicar; um job headless do GitHub Actions não cumpre esse fluxo sem uma interface de confirmação. Por isso, não será ativada publicação silenciosa que viole as regras da plataforma.
- **YouTube Shorts:** upload resumable e publicação pública implementados. Configure `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` e `YOUTUBE_REFRESH_TOKEN` (OAuth com escopo `youtube.upload` e acesso offline). Projetos não auditados podem ter uploads limitados à visualização privada; a auditoria do Google é necessária para liberar publicação pública. Para OAuth, não deixe a tela de consentimento externa em **Testing** para operação contínua: tokens de atualização emitidos nesse modo expiram em 7 dias. Publique/configure o app para produção e conclua as verificações exigidas pelo Google.
- **WhatsApp:** hoje o robô prepara o texto com links; não publica no canal. A API WhatsApp Business Cloud não equivale à publicação em Canais do WhatsApp e não oferece uma operação genérica para postar em um canal. Não será usado envio não oficial/automação de navegador.

A configuração de três vídeos por dia controla a produção e as tentativas agendadas; não garante três publicações em todas as redes quando faltarem credenciais, permissões, produtos elegíveis ou quando uma API externa recusar o conteúdo.
- A publicação no Telegram privado e no canal depende dos segredos e das permissões do bot.
- A publicação no Instagram depende do token e da configuração da Meta.
