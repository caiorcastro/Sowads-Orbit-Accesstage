# Sowads Echo — especificação e processo operacional

## 1. O que é

Sowads Echo é a camada do Sowads Orbit que transforma um artigo aprovado em uma copy autoral
para LinkedIn, escrita na voz de uma liderança da empresa. Não é resumo, anúncio genérico nem
texto automático: é uma reação editorial que cria interesse pelo tema e leva ao artigo original.

No caso atual, a persona é **Celso Sato, CEO da Accesstage**. Cada artigo do Lote 3 recebeu uma
copy própria, um registro auditável em JSON, uma página no DOCX e uma visualização de aprovação.

## 2. Resultado entregue por artigo

1. Uma copy de LinkedIn na primeira pessoa, pronta para copiar.
2. Um link para a ficha/artigo correspondente.
3. Exatamente cinco hashtags: marca, tema e intenção, sem repetição.
4. Um item no DOCX, um item no JSON e um par visual no preview.

O pacote do Lote 3 contém 12 artigos e 12 posts. A prévia é
`https://sowads-orbit.web.app/accesstage/lote3-echo/`.

## 3. Persona e tom

- Persona configurada em `client/personas/celso_sato.md`.
- Nome exibido: **Celso Sato**.
- Cargo exibido: **CEO do Grupo Accesstage**.
- Foto oficial local: `client/personas/celso_sato.jpg`; ela é copiada ao preview para que a
  aprovação e o ZIP não dependam de arquivo externo.
- Voz: executiva, clara, humana, com opinião e utilidade prática.
- Perspectiva: primeira pessoa, sem tentar atribuir uma fala real não documentada ao Celso.

## 4. Regras de conteúdo

- Nunca inventar clientes, cenas, números, pesquisas, resultados ou declarações.
- Só usar fatos verificáveis presentes no artigo-fonte.
- Não usar travessão, ponto e vírgula ou cacoetes de IA.
- Não usar emoji por padrão. `--emoji_mode subtle` aceita no máximo um, somente se fizer sentido;
  em conteúdo técnico, continua preferível usar zero.
- Não deixar o modelo criar hashtags livremente. O sistema remove hashtags da resposta e aplica
  cinco hashtags deduplicadas e relacionadas ao tema.
- Não repetir a abertura e a estrutura do post dentro do mesmo lote.

## 5. Variação editorial

O Echo tem 20 ângulos de abertura rotacionados, incluindo tese, erro caro, sinal fraco, decisão
de conselho, contraste, pergunta, mudança de perspectiva e opinião firme. O objetivo é evitar
que 12 posts pareçam a mesma peça com palavras diferentes.

O post deve cumprir esta sequência, sem uma fórmula rígida visível:

1. Abrir com uma ideia, tensão ou decisão relevante.
2. Desenvolver uma leitura executiva baseada no artigo.
3. Traduzir o tema técnico em impacto de negócio ou gestão.
4. Fechar com convite natural ao artigo e, quando couber, uma pergunta.
5. Inserir as cinco hashtags ao final.

## 6. Processo de geração

Primeiro, gerar e aprovar uma amostra. Nunca gerar o lote inteiro sem o OK do cliente.

```bash
python3 tools/echo.py \
  --csv output/articles/<lote>.csv \
  --url_dir output/accesstage-site/<lote> \
  --url_base https://<preview>/<cliente>/<subpagina> \
  --out output/celso/sowads_echo_<lote>.docx \
  --json_out output/celso/sowads_echo_<lote>.json \
  --limit 2 \
  --emoji_mode none
```

Depois da aprovação da amostra, repetir sem `--limit`. O modelo padrão é
`anthropic/claude-opus-4.7`; o Orbit usa OpenRouter, nunca API direta do modelo.

## 7. Artefatos

| Artefato | Finalidade |
| --- | --- |
| `sowads_echo_<lote>.docx` | Entrega para leitura, aprovação e cópia manual; um post por página. |
| `sowads_echo_<lote>.json` | Auditoria: fonte, copy, hashtags e dados estruturados. |
| Preview HTML | Aprovação visual e cópia de cada post. |
| ZIP | Pacote único com artigos, imagens, preview, DOCX e JSON. |

Os artefatos de saída ficam em `output/` e são intencionalmente ignorados pelo Git. O código,
persona, foto, processo e documentação são versionados.

## 8. Preview de aprovação

`tools/generate_echo_preview.py` recebe o CSV dos artigos, JSON do Echo, arquivos HTML de origem
e DOCX. Ele monta uma subpágina isolada e copia a foto de Celso como asset local.

Em telas largas, a grade possui dois pares por linha. Cada par contém:

- **Esquerda:** imagem, QA, título, resumo e link da ficha do artigo.
- **Direita:** card com aparência de LinkedIn, foto, nome/cargo, copy, ação de copiar e link do
  artigo correspondente.

No mobile, cada par vira uma coluna. A página tem `noindex,nofollow` e é uma simulação para
aprovação: não representa posts publicados.

```bash
python3 tools/generate_echo_preview.py \
  --csv output/articles/<lote>.csv \
  --echo_json output/celso/sowads_echo_<lote>.json \
  --source_dir output/accesstage-site/<lote> \
  --out_dir output/preview/accesstage/<subpagina> \
  --docx output/celso/sowads_echo_<lote>.docx
```

## 9. Checklist de aprovação

- Título, imagem e resumo correspondem ao artigo correto.
- A copy não inventa fatos e não repete o ângulo de outro post do lote.
- O tom parece o de Celso, sem exagero de emojis ou hashtags genéricas.
- Há cinco hashtags, com aderência ao artigo.
- O botão de cópia preserva o texto e as quebras de linha.
- Foto, DOCX, JSON e links funcionam também dentro do ZIP.
- O preview possui URL nova; preview anterior não é substituído.

## 10. Publicação e proteção atual

No Firebase, o hub é compartilhado entre clientes. Por isso, a única publicação permitida é:

```bash
python3 tools/safe_deploy.py accesstage
```

O processo compara os arquivos locais com a versão ativa e bloqueia qualquer deploy que apagaria
conteúdo de outro cliente. Nunca usar `firebase deploy` direto, `--allow-removals` ou deploy sem
target. O procedimento completo está em `docs/DEPLOY_SAFETY.md`.

## 11. Evolução para Cloudflare Pages

Cada cliente passará a ter um projeto Pages próprio. O Echo da Accesstage será publicado somente
no projeto `sowads-accesstage`; OMT, Preçolandia e SimulaDinheiro terão projetos distintos. Essa
separação elimina a dependência de paridade global do hub para novos deploys.

A mudança é feita por cliente, com validação da nova URL antes de qualquer troca de domínio ou
desativação do Firebase. O Firebase fica como rollback até a migração estar aceita.

## 12. Manutenção obrigatória

Ao mudar o Echo, atualizar `README.md`, `CLAUDE.md`, `ORBIT_MASTER.md` e este documento quando
aplicável. Em toda sessão com alteração: validar, atualizar o cache de deploy quando necessário,
fazer commit e push. Marcos anteriores nunca são removidos.
