# 🚀 TeXFlow: Geração Dinâmica de Documentos LaTeX

**TeXFlow** é um framework Python robusto e minimalista, projetado para transformar dados complexos (de NumPy, Matplotlib, etc.) em documentos $\LaTeX$ formatados profissionalmente. Ele utiliza o poder do **Jinja2** para criar templates dinâmicos, garantindo que a geração de seus relatórios, artigos e teses seja rápida, repetível e livre de erros.

---

## ✨ Recursos Principais

* **Template Engine Avançado:** Utiliza **Jinja2** para lógica condicional (`{% if %}`), loops (`{% for %}`), e herança de templates dentro de seus arquivos `.tex`.
* **Integração Científica:** Projetado para integrar facilmente dados numéricos de **NumPy** e visualizações gráficas de **Matplotlib** diretamente nos templates.
* **Compilação Confiável:** Automatiza a compilação de templates `.tex` usando **XeLaTeX**, garantindo suporte moderno para fontes e Unicode.
* **Solução de Conflito de Sintaxe:** O framework configura o Jinja2 com delimitadores personalizados para **evitar conflitos** com a sintaxe padrão do $\LaTeX$ (`\` e `{}`).

---

## 🛠 Tecnologias Utilizadas

TeXFlow é construído sobre as seguintes tecnologias:

* **Python:** A linguagem base do framework.
* **Jinja2:** Para a camada de template e lógica de renderização.
* **NumPy:** Para manipulação de dados numéricos (tabelas, cálculos).
* **Matplotlib:** Para gerar gráficos e figuras que são incluídos no $\LaTeX$.
* **XeLaTeX:** O motor de compilação $\LaTeX$ recomendado para o resultado final em PDF.
* **biber:** O motor de compilação $\BibLaTex$ recomendado para o resultado final em PDF.

---

## ⚙️ Instalação

### Pré-requisitos

Você deve ter uma distribuição $\LaTeX$ instalada (como **TeX Live** ou **MiKTeX**) e o compilador `xelatex` ou `pdflatex` acessível no seu PATH.

* Python 3.12.0

### Via pip

```bash
    pip install texflow
````

*(Observação: substitua por `pip install .` ou o comando correto após empacotar o projeto.)*

-----

## 📖 Como Usar

### 1\. Crie seu Template Jinja-LaTeX

Seu template (`report.tex.jinja`) deve usar a sintaxe Jinja para injetar dados.

```tex
    > **Exemplo Simples:**
    >
    > 
    > \documentclass{article}
    > \title{Relatório Dinâmico de {{ nome_projeto }}}
    > \begin{document}
    > \maketitle


    > O valor médio calculado é: ${{ mean_value | round(2) }}$.

    > \\end{document}
```

### 2\. Prepare seus Dados (Python)

```python
    import texflow
    import numpy as np

    # Dados a serem injetados
    contexto = {
        "nome_projeto": "Análise Estatística",
        "mean_value": np.mean([10.5, 12.3, 9.8, 11.2])
    }

    # Inicializa o TeXFlow
    gerador = texflow.Generator(
        template_dir='./templates',
        output_dir='./output',
        compiler='xelatex' # ou 'pdflatex'
    )

    # Renderiza e compila
    gerador.render_and_compile(
        template_file='report.tex.jinja',
        output_name='report_final',
        context=contexto
    )

    print("Documento PDF gerado com sucesso em ./output/report_final.pdf")
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
