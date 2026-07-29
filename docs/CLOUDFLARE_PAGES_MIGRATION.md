# Migração para Cloudflare Pages — Sowads Orbit

## Objetivo

Separar a hospedagem por cliente sem desligar o Firebase antes de cada site estar validado.
Um projeto Cloudflare Pages contém somente um cliente e seus previews; não existe deploy global.

## Projetos planejados

| Cliente | Projeto Pages | Primeira entrega |
| --- | --- | --- |
| Accesstage | `sowads-accesstage` | `lote3-echo` |
| OMT | `sowads-omt` | preview ativo atual |
| Preçolandia | `sowads-precolandia` | `blog_lote2` e `blog_lote3` |
| SimulaDinheiro | `sowads-simuladinheiro` | preview ativo atual |

## Guardrails

1. Criar e validar um projeto de cada vez.
2. Não trocar domínio, URL divulgada ou Firebase antes da validação da nova URL.
3. Um projeto recebe somente o diretório estático daquele cliente.
4. ZIP/DOCX grandes devem migrar para R2 se chegarem perto do limite de asset do Pages.
5. Previews devem usar `noindex,nofollow`; quando necessário, restringir acesso com Cloudflare
   Access.
6. O Firebase continua como rollback até a aprovação explícita da migração de cada cliente.

## Estado do repositório

Os previews atuais são criados em `output/`, que é ignorado pelo Git. Portanto, a integração
GitHub nativa do Cloudflare não deve apontar diretamente para essa pasta. Antes de automatizar,
o deploy deve receber um artefato estático exclusivo do cliente por CI ou uma pasta de entrega
versionada. Nunca apontar Pages para a raiz deste repositório.

## Sequência por cliente

1. Criar o projeto Pages com o nome definido.
2. Fazer o primeiro upload manual do diretório estático do cliente para criar e testar a URL
   `pages.dev` sem afetar produção.
3. Validar HTTP, imagens, downloads, links internos e `noindex`.
4. Registrar URL, data e resultado neste documento e no marco do cliente.
5. Definir o modo definitivo: integração GitHub com artefato CI ou deploy direto autenticado.
6. Se houver domínio próprio, configurar e validar DNS/SSL.
7. Só após aprovação, redirecionar ou trocar a URL divulgada; manter Firebase como rollback.

## Primeira migração: Accesstage / Echo

Diretório de origem: `output/preview/accesstage/lote3-echo/`.

Validações mínimas:

- `index.html` carrega e há 12 pares artigo + LinkedIn.
- `assets/celso-sato.jpg` abre localmente.
- 12 fichas HTML, imagens, DOCX e JSON estão acessíveis.
- A página não é indexável.
- O pacote ZIP contém os mesmos arquivos de aprovação.

## Próxima ação externa

A conta Cloudflare deve ser confirmada por e-mail antes da criação do primeiro projeto Pages.
Após a confirmação, criar `sowads-accesstage`, fazer o upload da primeira prévia, validar a URL e
registrar a migração. Nenhum site atual será desligado nesta etapa.
