# 🚀 TeXFlow: Geração Dinâmica de Documentos LaTeX

**TeXFlow** é uma ferramenta de linha de comando que transforma um arquivo JSON de dados em um documento $\LaTeX$ compilado em PDF, usando templates Jinja2. Você escreve um template `.tex` com placeholders, aponta o TeXFlow para ele e para o seu JSON de dados, e ele renderiza e compila o PDF automaticamente via `latexmk`/`xelatex`/`biber`.

---

## ✨ Recursos Principais

* **Template Engine Jinja2:** lógica condicional (`<<% if %>> ... %>>`), loops (`<<% for %>> ... %>>`) e variáveis (`<< variavel >>`) dentro dos seus arquivos `.tex`, com delimitadores customizados para não conflitar com a sintaxe do LaTeX (`\` e `{}`).
* **Pipeline de build orientado a tarefas:** renderização do template, cópia de imagens/gráficos e demais arquivos de suporte, e compilação, todos executados como tarefas com dependências (`src/classes/task.py`), com barra de progresso no terminal.
* **Compilação via `latexmk`:** roda `latexmk -xelatex` (que por sua vez aciona `xelatex`/`biber` conforme necessário), com detecção e resumo amigável de erros de compilação (citações/referências não resolvidas, caracteres ausentes, placeholders não renderizados, etc.).
* **Binário standalone:** script `install.sh` que empacota o TeXFlow com PyInstaller, sem exigir Python instalado na máquina de destino.

---

## 🛠 Tecnologias Utilizadas

* **Python 3.12+** — linguagem base.
* **Jinja2** — motor de template.
* **prompt-toolkit** / **yaspin** — interface de terminal (spinners, texto formatado).
* **latexmk**, **XeLaTeX** e **biber** — toolchain de compilação LaTeX (não incluídos, precisam estar instalados no sistema).
* **matplotlib** e **pandas** — disponíveis como dependências para uso nos *seus* scripts de preparação de dados (geração do JSON de entrada); o TeXFlow em si não os utiliza internamente.

---

## ⚙️ Instalação

### Pré-requisitos

* Uma distribuição $\LaTeX$ com `latexmk`, `xelatex` e `biber` acessíveis no PATH (ex.: **TeX Live** ou **MiKTeX**).
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
| `--debug` | não | Ativa logs verbosos (equivalente a `TEXFLOW_DEBUG=1`). |
| `--update` | não | Verifica a última release no GitHub e, se houver uma versão mais nova, baixa e instala no lugar do binário atual. |
| `--uninstall` | não | Remove o binário instalado do sistema. |
| `-y`, `--yes` | não | Pula a confirmação interativa de `--update`/`--uninstall`. |

`--update` e `--uninstall` só têm efeito no **binário standalone** (baixado da release ou gerado por `install.sh`) — rodando a partir do código-fonte (`uv run texflow`), eles apenas indicam o comando equivalente (`git pull && uv sync`).

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
