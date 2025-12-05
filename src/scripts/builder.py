import os
import time

from jinja2 import Environment, FileSystemLoader

def build():
    
    # --- 1. CONFIGURAÇÃO DO JINJA2 ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env = Environment(
        loader=FileSystemLoader(script_dir),
        trim_blocks=True,
        lstrip_blocks=True    
    )
    
    # Certifique-se de que o template (.tex) está na mesma pasta
    template = env.get_template('certificado_template.tex') 

    # --- 2. DADOS VARIÁVEIS ---
    alunos_para_certificar = [
        {
            'nome_aluno': 'Lucas Fontes',
            'nome_curso': 'Análise de Dados Avançada',
            'horas_aula': 80,
            'nota_final': 9.5,
            'data_emissao': '05 de Dezembro de 2025'
        }
    ]
    
    # --- 3. Processamento e Compilação com XeLaTeX ---
    for aluno in alunos_para_certificar:
        # 3.1. Renderização
        output_latex_code = template.render(aluno)

        # 3.2. Salva o arquivo .tex
        nome_arquivo_base = aluno['nome_aluno'].replace(' ', '_').lower()
        tex_filename = f"{nome_arquivo_base}_certificado.tex"
        pdf_filename = f"{nome_arquivo_base}_certificado.pdf"

        with open(tex_filename, 'w', encoding='utf8') as f:
            f.write(output_latex_code)
        
        print(f"Gerado {tex_filename}...")

        # 3.3. COMPILAÇÃO: Chamando o XeLaTeX
        try:
            # Usamos 'xelatex' em vez de 'pdflatex'
            # O modo 'batchmode' suprime mensagens no terminal
            os.system(f"xelatex -interaction=batchmode {tex_filename}")
            os.system(f"xelatex -interaction=batchmode {tex_filename}") # Duas vezes para referências

            # Opcional: Limpar arquivos auxiliares (.log, .aux, etc.)
            os.system(f"rm *.aux *.log *.out" if os.name != 'nt' else f"del *.aux *.log *.out")
            
            print(f"Sucesso ao gerar {pdf_filename} usando XeLaTeX!")
        except Exception as e:
            print(f"Falha na compilação do PDF para {aluno['nome_aluno']}: {e}")