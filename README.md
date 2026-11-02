# 🚀 TeXFlow: Geração Dinâmica de Documentos LaTeX

**TeXFlow** é uma ferramenta de linha de comando que transforma um arquivo JSON de dados em um documento $\LaTeX$ compilado em PDF, usando templates Jinja2. Você escreve um template `.tex` com placeholders, aponta o TeXFlow para ele e para o seu JSON de dados, e ele renderiza e compila o PDF automaticamente via `latexmk`/`xelatex`/`biber` — ou via [Tectonic](https://tectonic-typesetting.github.io), sem precisar de TeX Live instalado.

---

## ✨ Recursos Principais

* **Template Engine Jinja2:** lógica condicional (`<<% if %>> ... %>>`), loops (`<<% for %>> ... %>>`) e variáveis (`<< variavel >>`) dentro dos seus arquivos `.tex`, com delimitadores customizados para não conflitar com a sintaxe do LaTeX (`\` e `{}`).
* **Pipeline de build orientado a tarefas:** renderização do template, cópia de imagens/gráficos e demais arquivos de suporte, e compilação, todos executados como tarefas com dependências (`src/classes/task.py`), com barra de progresso no terminal.
* **Dois engines de compilação:** `latexmk -xelatex` (padrão, que aciona `xelatex`/`biber` conforme necessário) ou **Tectonic** (`--engine tectonic`), autocontido e que baixa os pacotes sob demanda. Nos dois casos há detecção e resumo amigável de erros de compilação (erros com `arquivo:linha`, citações/referências não resolvidas, caracteres ausentes, placeholders não renderizados, biber incompatível, etc.).
* **Modo watch:** `--watch` refaz o build a cada mudança no JSON, no template ou nos assets, em segundos.
* **Binário standalone:** script `install.sh` que empacota o TeXFlow com PyInstaller, sem exigir Python instalado na máquina de destino — opcionalmente com o Tectonic embutido.
* **Integração com VS Code:** `texflow --init` configura o LaTeX Workshop (preview, SyncTeX, painel de erros) e o rebuild automático.

---

## 🛠 Tecnologias Utilizadas

* **Python 3.12+** — linguagem base.
* **Jinja2** — motor de template.
* **prompt-toolkit** / **yaspin** — interface de terminal (spinners, texto formatado).
* **latexmk**, **XeLaTeX** e **biber** — toolchain de compilação LaTeX padrão (não incluídos, precisam estar instalados no sistema).
* **Tectonic** — engine alternativo (opcional; pode vir embutido no binário).
* **watchfiles** — observação de arquivos do modo `--watch`.
* **matplotlib** e **pandas** — disponíveis como dependências para uso nos *seus* scripts de preparação de dados (geração do JSON de entrada); o TeXFlow em si não os utiliza internamente.

---

## ⚙️ Instalação

### Pré-requisitos

* Para o engine padrão: uma distribuição $\LaTeX$ com `latexmk`, `xelatex` e `biber` acessíveis no PATH (ex.: **TeX Live** ou **MiKTeX**).
* **Ou**, para `--engine tectonic`: só o [Tectonic](https://tectonic-typesetting.github.io/book/latest/installation/) (ou um binário do TeXFlow com o Tectonic embutido, ver Opção 2). Documentos com `biblatex` ainda precisam de um `biber` compatível — ver [o aviso sobre o biber](#aviso-biber-com-tectonic).
* Para rodar a partir do código-fonte: **Python 3.12+** e [**uv**](https://docs.astral.sh/uv/).
* Para gerar o binário standalone: apenas `uv` (o Python é empacotado junto pelo PyInstaller).

### Opção 1 — Baixar o binário pronto (Linux x86_64)

Baixa o executável da [última release](https://github.com/felipevale23/texflow/releases/latest) diretamente, sem precisar clonar o repositório nem instalar Python:

```bash
curl -L https://github.com/felipevale23/texflow/releases/latest/download/texflow-linux-x86_64 -o texflow
chmod +x texflow
sudo mv texflow /usr/local/bin/   # ou mova para qualquer pasta do seu PATH
```

> No momento só há binário para Linux x86_64. Para outras plataformas, use a Opção 2 ou 3.

### Opção 2 — Compilar o binário localmente (`install.sh`)

```bash
git clone https://github.com/felipevale23/texflow.git
cd texflow
./install.sh
```

O script:

1. Sincroniza as dependências e compila um binário único com PyInstaller (`dist/texflow`).
2. Instala esse binário em `~/.local/bin/texflow` (ajustável via a variável `TEXFLOW_INSTALL_DIR`).
3. Avisa se `~/.local/bin` não estiver no seu `PATH`.

Para embutir o Tectonic no binário (e compilar com `--engine tectonic` numa máquina sem TeX Live):

```bash
TEXFLOW_BUNDLE_TECTONIC=1 ./install.sh
```

Isso baixa a última release do Tectonic para Linux x86_64 (build estático musl) direto do GitHub e a inclui no executável — que fica bem maior (~100 MB). Nesse modo o aviso de `xelatex`/`latexmk` ausentes não aparece.

Depois disso, `texflow` fica disponível diretamente no terminal, sem precisar de `uv` ou de um ambiente Python.

### Opção 3 — Rodar a partir do código-fonte

```bash
git clone https://github.com/felipevale23/texflow.git
cd texflow
uv sync
uv run texflow --build --input <dados.json> --template <pasta_do_template>
```

-----

## 📖 Como Usar

### 1\. Crie a pasta do seu template

Uma pasta de template precisa conter pelo menos um `main.tex` — o restante dos arquivos (`.sty`, `.bib`, etc.) é copiado como está para o diretório de build. Use os delimitadores customizados do Jinja2 em vez da sintaxe padrão (`{{ }}`/`{% %}`):

```tex
\documentclass{article}
\title{Relatório Dinâmico de << nome_projeto >>}
\begin{document}
\maketitle

<<% if mostrar_media %>>
O valor médio calculado é: $<< media | round(2) >>$.
<<% endif %>>

\end{document}
```

> Arquivos `.tex` diferentes de `main.tex` são ignorados na cópia por padrão — exceto `abstract.tex`, `glossaries.tex` e `conclusions.tex`, que sempre são copiados.

Veja `assets/templates/journal/` no repositório para um exemplo completo.

### 2\. Prepare seu JSON de dados

As variáveis do template ficam dentro da chave `"payload"`:

```json
{
    "payload": {
        "nome_projeto": "Análise Estatística",
        "mostrar_media": true,
        "media": 10.95
    }
}
```

### 3\. Rode o build

```bash
texflow --build --input dados.json --template caminho/para/pasta_do_template
```

| Flag | Obrigatória | Descrição |
|---|---|---|
| `-b`, `--build` | sim | Executa o build. |
| `-i`, `--input` | sim | Caminho para o JSON de dados (`{"payload": {...}}`). |
| `-t`, `--template` | não (padrão: `journal`) | Caminho para a pasta do template (deve conter `main.tex`). |
| `--engine` | não (padrão: `latexmk`) | Engine de compilação: `latexmk` ou `tectonic`. Também pode vir da variável `TEXFLOW_ENGINE`; a flag tem prioridade. |
| `-w`, `--watch` | não | Com `--build`: depois do primeiro build, refaz o build a cada mudança (ver abaixo). Com `--init`: gera a task de watch do VS Code em vez do RunOnSave. |
| `--debug` | não | Ativa logs verbosos (equivalente a `TEXFLOW_DEBUG=1`): `-verbose` no latexmk, `--print` no Tectonic. |
| `--init` | não | Cria `.vscode/settings.json` e `.vscode/extensions.json` no diretório atual, com a receita do LaTeX Workshop e o rebuild automático já configurados pro TexFlow (aceita `--engine` e `--watch`). |
| `--update` | não | Verifica a última release no GitHub e, se houver uma versão mais nova, baixa e instala no lugar do binário atual. |
| `--uninstall` | não | Remove o binário instalado do sistema. |
| `-y`, `--yes` | não | Pula a confirmação interativa de `--update`/`--uninstall`/`--init`. |
| `-v`, `--version` | não | Mostra a versão instalada e sai. |

Variáveis de ambiente:

| Variável | Descrição |
|---|---|
| `TEXFLOW_ENGINE` | Engine padrão (`latexmk` ou `tectonic`) quando `--engine` não é passado. |
| `TEXFLOW_TECTONIC` | Caminho explícito pro binário do Tectonic. |
| `TEXFLOW_DEBUG` | Igual a `--debug`. |
| `TEXFLOW_INSTALL_DIR` | (`install.sh`) pasta onde o binário é instalado. |
| `TEXFLOW_BUNDLE_TECTONIC` | (`install.sh`) `1` embute o Tectonic no binário. |

`--update` e `--uninstall` só têm efeito no **binário standalone** (baixado da release ou gerado por `install.sh`) — rodando a partir do código-fonte (`uv run texflow`), eles apenas indicam o comando equivalente (`git pull && uv sync`).

#### Engine: latexmk ou Tectonic

```bash
texflow --build --engine tectonic --input dados.json --template pasta_do_template
# ou, pra valer em toda a sessão:
export TEXFLOW_ENGINE=tectonic
```

O Tectonic é procurado nesta ordem: `TEXFLOW_TECTONIC` → binário embutido no TeXFlow (`install.sh` com `TEXFLOW_BUNDLE_TECTONIC=1`) → `tectonic` no `PATH`. Ele gera os mesmos `build/main.pdf`, `build/main.log` e `build/main.synctex.gz` que o latexmk.

> **Primeira execução:** o Tectonic baixa da internet os pacotes e fontes que o documento usa (pode levar alguns minutos num template grande). Depois disso tudo fica em cache (`~/.cache/Tectonic`) e os builds seguintes funcionam offline.

<a id="aviso-biber-com-tectonic"></a>

> **Aviso — biber com Tectonic:** o Tectonic traz um `biblatex` fixo no bundle dele, mas chama o `biber` **do sistema**, e os dois precisam ser de versões compatíveis. Com o bundle atual (biblatex 3.17) o biber precisa ser o **2.17**; um biber mais novo (ex.: o 2.22 do TeX Live 2026) falha com `Found biblatex control file version 3.8, expected version 3.11`. O TeXFlow detecta esse erro e mostra a dica. Saídas: instalar o biber 2.17 (binário avulso [no SourceForge](https://sourceforge.net/projects/biblatex-biber/files/biblatex-biber/2.17/binaries/)) à frente no `PATH`, ou usar `--engine latexmk` em templates com `biblatex` (como o `journal` de exemplo). Templates sem bibliografia via biber não são afetados.

#### Modo watch

```bash
texflow --build --watch --input dados.json --template pasta_do_template
```

Faz um build e fica observando a pasta do template (`main.tex`, parciais, `.sty`, `.bib`...), o JSON de dados e os assets de imagens/plots; a cada mudança refaz o build (agrupando rajadas de eventos com ~300 ms de debounce). Como arquivos que não mudaram mantêm o mtime em `build/`, o latexmk só reprocessa o necessário, e o rebuild leva segundos. Um build com erro mostra o resumo do erro e o watcher continua rodando; `Ctrl+C` encerra.

### 4\. (opcional) Integre com o VS Code + LaTeX Workshop

```bash
cd caminho/para/pasta_do_template
texflow --init [--engine tectonic] [--watch]
```

Isso cria (ou atualiza) na pasta `.vscode/`:

* `settings.json` — receitas do LaTeX Workshop `TexFlow Build` (latexmk) e `TexFlow Build (Tectonic)`; a padrão (`Ctrl+Alt+B`) é a do `--engine` escolhido. Sem `--watch`, também um bloco `emeraldwalk.runonsave` que roda `texflow --build` ao salvar qualquer `.tex`, `.json`, `.sty`, `.cls` ou `.bib`.
* `extensions.json` — recomenda [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=James-Yu.latex-workshop) e, sem `--watch`, [RunOnSave](https://marketplace.visualstudio.com/items?itemName=emeraldwalk.RunOnSave).
* `tasks.json` (só com `--watch`) — task em segundo plano **TexFlow Watch**, que roda `texflow --build --watch` e inicia sozinha ao abrir a pasta (na primeira vez o VS Code pergunta se pode rodar tasks automáticas; dá pra iniciar à mão em *Tasks: Run Task*).

**RunOnSave ou watch?** Os dois rebuildam ao salvar o `input.json` ou qualquer parcial. O RunOnSave roda um processo novo a cada `Ctrl+S`; a task de watch deixa um processo só rodando (rebuild mais rápido, pega também mudanças feitas fora do editor e não precisa de extensão extra) e joga os erros no painel **Problems**: o resumo de erros do TeXFlow sai no formato `arquivo:linha: mensagem`, que o `problemMatcher` da task reconhece, apontando pro `build/main.tex` renderizado.

Nos dois casos o preview do PDF recarrega quando o `build/main.pdf` muda, o SyncTeX (forward/inverse search) usa o `build/main.synctex.gz` e o painel de erros do LaTeX Workshop lê o `build/main.log` — com qualquer um dos engines (`latex-workshop.latex.outDir` é `%DIR%/build/`). Inverse search leva pro `build/main.tex` renderizado, não pro template, já que é ele que o LaTeX compila.

Se os arquivos já existirem, o `--init` **não os sobrescreve**: ele pergunta e atualiza só a parte do TeXFlow (chaves `latex-workshop.*` e `emeraldwalk.runonsave` no `settings.json`, as recomendações no `extensions.json`, a task `TexFlow Watch` no `tasks.json`), preservando suas outras configurações e comentários. Só se o arquivo não for um JSON(C) válido ele oferece sobrescrever, como antes. Rodar de novo com outro `--engine`/`--watch` troca a configuração.

> O rebuild via RunOnSave/watch é necessário porque o `main.tex` inclui os parciais via Jinja (`<<% include %>>`), não por `\input` — então o build-on-save nativo do LaTeX Workshop (desligado no `settings.json` gerado) só enxergaria o próprio `main.tex`.
>
> Convém rodar `--init` na mesma pasta que contém `input.json` e `main.tex`, e abrir essa pasta como pasta do VS Code — a receita assume `--input %DIR%/input.json --template %DIR%` e o RunOnSave/a task rodam `--input input.json --template .` na raiz do workspace.

O PDF final é gerado em `<pasta_do_template>/build/main.pdf`. Imagens e gráficos vêm do pacote (`assets/images` e `assets/plots`) e também são copiados para `build/images` e `build/plots`.

-----

## 🧪 Desenvolvimento

Com o repositório clonado e `uv` instalado:

```bash
uv sync              # instala dependências (inclui ruff/pytest)
uv run test          # roda a suíte de testes (pytest)
uv run lint          # verifica lint (ruff check)
uv run lint-fix      # corrige lint automaticamente
uv run format        # formata o código (ruff format)
uv run format-check  # verifica formatação sem alterar arquivos
uv run check         # lint + format-check + test
uv run clean         # remove dist/, build/ e caches
uv run build-dist    # gera wheel/sdist com `uv build`
```

-----

## 🤝 Contribuições

Contribuições são sempre bem-vindas\! Sinta-se à vontade para abrir uma *issue* para relatar bugs ou sugerir novos recursos.

1.  Faça o *fork* do projeto.
2.  Crie uma *branch* de recurso (`git checkout -b feature/cool-stuff`).
3.  Faça o *commit* das suas alterações (`git commit -m 'Adiciona um IncrívelRecurso'`).
4.  Faça o *push* para a *branch* (`git push origin feature/cool-stuff`).
5.  Abra um *Pull Request*.

-----

## 📄 Licença

Distribuído sob a Licença MIT. 
Veja `LICENSE` para mais informações.

-----

## 📧 Contato \[[felipevale23](https://www.google.com/search?q=https://github.com/felipevale23)]

Email do Projeto: `felipevale@pm.me`
