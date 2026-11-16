# Visão geral do projeto

**Achadinhos Baratos** é um projeto de afiliados da Shopee que automatiza a seleção de produtos, a criação de vídeos curtos e a divulgação de ofertas. O repositório principal é [achadinhosbaratos/ofertas](https://github.com/achadinhosbaratos/ofertas).

Este documento descreve o funcionamento do código e das configurações encontrados no repositório em novembro de 2026. Segredos e tokens são configurados no GitHub Actions e não devem ser adicionados ao código.

## O que o projeto faz

- Lê produtos do feed CSV de afiliados da Shopee ou consulta a Open API quando as credenciais estão disponíveis.
- Filtra produtos por categoria, preço, nota, popularidade, desconto, envio nacional e histórico de publicação.
- Cria um vídeo vertical com fotos do produto, narração em português, legendas e identidade visual do projeto.
- Envia o vídeo, a legenda e os links ao chat privado do Telegram.
- Atualiza a página pública de ofertas no GitHub Pages e mantém um painel de vídeos.
- Prepara conteúdo para divulgação no canal do WhatsApp.
- Pode publicar Reels no Instagram e Shorts no YouTube quando as integrações e credenciais necessárias estão configuradas.
- Mantém dados de ofertas, histórico de produtos e estados da fila de redes em arquivos JSON versionados.

## Fluxo de execução

1. O workflow agendado inicia o robô nos horários definidos em .github/workflows/robo.yml. O objetivo é produzir até três vídeos por dia, com tentativas de reserva uma hora depois dos horários principais.
2. bot.py obtém produtos do feed ou da API e seleciona ofertas conforme os critérios configurados no próprio arquivo.
3. O robô gera roteiro, narração, imagens e vídeo. Gemini pode auxiliar na escrita dos roteiros. Se não estiver disponível, o robô usa textos alternativos.
4. O vídeo é enviado ao chat privado do Telegram. A oferta só é registrada como entregue após o envio do vídeo ao chat ser confirmado.
5. O robô grava a oferta em ofertas.json, atualiza historico.json, gera a página e o painel e coloca o vídeo na fila das redes quando elas estão ativas.
6. Rotinas separadas tentam publicar itens pendentes no Instagram e no YouTube. Os vídeos pendentes podem ser preservados como artefatos do GitHub Actions e recuperados em execuções posteriores.

## Componentes principais

| Arquivo ou diretório | Responsabilidade |
|---|---|
| bot.py | Busca e seleção de produtos, links, roteiros, montagem dos vídeos, integração com Telegram, Instagram e YouTube, histórico e geração das páginas. |
| vitrine.py | Converte os registros de ofertas.json em uma página HTML estática. |
| vitrine.js e vitrine.css | Interações, filtros, favoritos, compartilhamento e apresentação visual da vitrine. São incorporados à página gerada. |
| ofertas.json | Ofertas que alimentam a vitrine. |
| historico.json | IDs de produtos usados recentemente, para reduzir repetições. |
| fila.json | Fila de produtos e estados do fluxo de produção diária. |
| redes.json | Estado dos vídeos pendentes ou publicados nas redes, quando o arquivo existe no repositório ou é gravado por uma execução. |
| .github/workflows/robo.yml | Agendamento e execução principal, implantação do Pages, publicação nas redes, recuperação de vídeos e persistência de JSONs. |
| .github/workflows/ci.yml | Verificações de sintaxe, testes automatizados, integridade dos JSONs e algumas configurações esperadas. |
| .github/workflows/publicar-vitrine.yml | Publica uma atualização da vitrine sem executar a rotina de produção do robô. |
| .github/workflows/teste-instagram-controlado.yml | Valida a integração do Instagram e permite um teste controlado de um Reel com confirmação explícita. |
| tests/ | Testes de regressão para vitrine, links, filas, integrações e comportamento de publicação. |

## Seleção e formatos de vídeo

A configuração padrão do código usa o formato telaverde, com o produto em destaque, cenas compostas a partir das imagens disponíveis, o mascote Lupi, narração e chamada final para o link no perfil. Também existem formatos para promoção, comparativo e conversa.

Entre os critérios padrão encontrados em bot.py estão preço máximo de R$ 150, nota mínima 4,5, desconto entre 20% e 75%, pelo menos 30 curtidas no modo feed ou 100 vendas no modo API e preferência por envio nacional. O histórico evita repetir o produto por 30 dias. Esses valores podem ser alterados no código.

O Google Flow está desligado por padrão. A produção normal monta os vídeos automaticamente com imagens do produto e não exige clipes manuais.

## Integrações e limites atuais

- **Shopee:** o feed pode fornecer produtos e links. Com SHOPEE_APP_ID e SHOPEE_SECRET, o robô pode gerar links curtos pela Open API. A disponibilidade e as permissões da API dependem da Shopee.
- **Telegram:** TELEGRAM_TOKEN e TELEGRAM_CHAT_ID são necessários para entregar vídeos no chat privado. Para publicar no canal, o bot precisa ter permissão adequada e TELEGRAM_CANAL configurado.
- **Instagram:** a publicação depende de conta profissional, token, modo de autenticação e permissões da Meta. O workflow principal define INSTAGRAM_PUBLICAR como nao, portanto a configuração de token, sozinha, não habilita a publicação por essa rotina. Comentários com link têm um opt-in separado.
- **YouTube Shorts:** o upload depende de YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET e YOUTUBE_REFRESH_TOKEN. Projetos Google sem auditoria podem limitar vídeos à visualização privada.
- **WhatsApp:** o robô prepara texto e links para copiar e publicar no canal. Não publica diretamente em Canais do WhatsApp.
- **TikTok:** não há publicação automática implementada no fluxo. A publicação oficial requer consentimento e opções de privacidade apresentados ao usuário.
- **GitHub Pages e GA4:** a página é estática. O GA4 é opcional e a implementação solicita consentimento antes de carregar as métricas. A configuração do workflow de publicação também valida o formato do ID de medição.
- **Preços e disponibilidade:** os dados gravados refletem a coleta da oferta. Uma oferta no histórico ou na página não significa que seu preço e estoque foram revalidados em tempo real.

Os nomes dos segredos e variáveis necessários estão descritos no README. Cadastre os valores em **Settings → Secrets and variables → Actions**. Nunca coloque tokens no código, em commits, em issues ou em capturas de tela.

## Melhorias futuras

### Prioridade alta

1. **Validar a atribuição dos links de afiliado.** Após a liberação da Open API, gerar um link de teste e conferir no painel da Shopee se o clique e a venda são atribuídos à conta correta.
2. **Atualizar os links das ofertas já salvas.** Depois de validar a geração oficial, migrar os links antigos de ofertas.json, mantendo identificadores de produto estáveis para preservar favoritos e compartilhamentos.
3. **Controlar a idade das ofertas.** Mostrar claramente a data de coleta, reduzir o destaque de registros antigos e, quando houver API disponível, revalidar preço, estoque e link antes de manter uma oferta ativa.
4. **Separar estado de produção e estado de cada canal.** Registrar o vídeo e a oferta quando a produção terminar e controlar Telegram, Instagram e YouTube independentemente. Isso permite recuperar uma falha em um canal sem refazer o trabalho já concluído nos demais.
5. **Conferir o consentimento do GA4.** No fluxo atual, aceitar métricas depois de uma recusa na mesma página habilita o rastreamento local, mas a rotina não envia explicitamente o estado granted ao Google. Ajustar e testar a transição entre recusar, aceitar e revogar.

### Próximas melhorias

6. **Acompanhar resultados.** Usar os eventos do GA4 e os identificadores de campanha dos links para entender visualizações, cliques e conversões sem expor dados pessoais.
7. **Melhorar a recuperação de falhas.** Tornar cada etapa idempotente, registrar tentativas e erros por oferta e evitar duplicar uma publicação quando uma API responde de forma ambígua.
8. **Reduzir a dependência de estado em arquivos JSON.** Se o volume crescer, avaliar armazenamento com operações atômicas e histórico consultável, preservando uma migração simples dos JSONs existentes.
9. **Reforçar a publicação do Pages.** Manter o site anterior se a geração nova falhar e documentar a recuperação quando o artefato anterior não estiver disponível.
10. **Manter os testes alinhados ao comportamento real.** Cobrir migrações de links, estados de consentimento, retentativas, duplicação e revalidação de ofertas. Os testes existentes verificam partes importantes, mas não substituem testes com credenciais e respostas reais dos serviços externos.
11. **Revisar a exposição do painel.** O painel usa uma instrução noindex, mas, estando no GitHub Pages, pode ser acessado por quem conhece o endereço. Evitar armazenar ali informações que precisem de autenticação.

## Como rodar e validar

O caminho normal de produção é o workflow Robô de achadinhos na aba Actions. Ele também pode ser executado manualmente conforme os modos descritos no próprio workflow. Antes de uma publicação real, confira as variáveis e os segredos exigidos pelo canal desejado.

O workflow de CI executa testes e verificações do código em pushes e pull requests conforme os gatilhos definidos em .github/workflows/ci.yml. A CI não confirma credenciais, permissões, comissões ou o resultado de chamadas reais à Shopee, Telegram, Meta ou Google.
