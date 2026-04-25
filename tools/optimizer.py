
import os
import csv
import json
import time
import argparse
import glob
import pandas as pd
import google.generativeai as genai
from datetime import datetime

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

# Objetivos:
# 1. Garantir FAQ em HTML visual + JSON-LD FAQPage schema.
# 2. Pontuar 1-10 em SEO/AIO.
# 3. Otimizar se score < 9.0.

def optimize_content_with_gemini(model, content, title):
    prompt = f"""
    ROLE: Especialista Sênior em SEO & AIO (Artificial Intelligence Optimization).
    TASK: Auditar e Otimizar o seguinte artigo HTML para WordPress.

    TÍTULO DO ARTIGO: {title}
    HTML DO ARTIGO:
    {content}

    INSTRUÇÕES OBRIGATÓRIAS:
    1. **FAQ:** Verificar se o FAQ está em DUAS representações:
       - HTML visual: <section class="faq-section"> com <h3> para perguntas e <p> para respostas.
       - JSON-LD: <script type="application/ld+json"> com FAQPage schema APÓS o </article>.
       Se alguma representação estiver faltando, CRIAR. Se o JSON-LD estiver dentro do article, MOVER para depois do </article>.

    2. **SCORING AIO:** Nota de 1 a 10 em "Generative Engine Optimization".
       Critérios: densidade de entidades, estrutura clara, respostas diretas, linguagem otimizada para NLP, tom conversacional em pt-BR.

    3. **OTIMIZAÇÃO:**
       - Se o Score estiver abaixo de 9.0, REESCREVER seções para melhorar.
       - O único <script> permitido é o JSON-LD FAQPage schema. Nenhum outro JS.
       - NENHUM link <a href=...> permitido.
       - Idioma OBRIGATÓRIO: pt-BR (Português do Brasil). Linguagem natural, traduzir termos técnicos em inglês.
       - Incluir tabelas comparativas (<table>) quando relevante.
       - Incluir listas (<ul>/<ol>) para organizar informações.
       - Densidade de keyword primária entre 0.5% e 4.0%.

    FORMATO DE SAÍDA (APENAS JSON):
    {{
        "aio_score": 8.5,
        "critique": "Explicação breve das lacunas encontradas.",
        "optimized_html": "HTML completo aqui (article + JSON-LD)..."
    }}
    """

    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        print(f"{Colors.FAIL}Erro na otimização: {e}{Colors.ENDC}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Orbit AI Content Optimizer (pt-BR)")
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--model", default="gemini-2.5-flash")
    parser.add_argument("--input_dir", default="output_csv_batches_v2", help="Diretório com CSVs para otimizar")
    args = parser.parse_args()

    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel(args.model)

    csv_files = glob.glob(f"{args.input_dir}/*.csv")
    report_data = []

    print(f"{Colors.HEADER}=== ORBIT AI OPTIMIZER (AUDITORIA & OTIMIZAÇÃO SEO/AIO) ==={Colors.ENDC}")
    print(f"Diretório: {args.input_dir} | Arquivos: {len(csv_files)}")

    for file_path in csv_files:
        print(f"\nProcessando: {file_path}")
        df = pd.read_csv(file_path)

        if 'post_content' not in df.columns:
            print("Pulando (sem coluna post_content)")
            continue

        updated_contents = []

        for index, row in df.iterrows():
            title = row.get('post_title', 'Título Desconhecido')
            content = row.get('post_content', '')

            if not isinstance(content, str) or len(content) < 100:
                updated_contents.append(content)
                continue

            print(f" -> Auditando: {title[:45]}...")

            result = optimize_content_with_gemini(model, content, title)

            if result:
                score = result.get('aio_score')
                critique = result.get('critique')
                new_html = result.get('optimized_html')

                color = Colors.OKGREEN if score >= 9.0 else Colors.WARNING
                print(f"    {color}Score AIO: {score}/10{Colors.ENDC} | {critique[:60]}...")

                updated_contents.append(new_html)
                report_data.append({
                    "Batch": os.path.basename(file_path),
                    "Título": title[:50],
                    "Score_AIO": score,
                    "Status": "Otimizado",
                    "Observação": critique
                })
            else:
                updated_contents.append(content)
                report_data.append({
                    "Batch": os.path.basename(file_path),
                    "Título": title[:50],
                    "Score_AIO": "N/A",
                    "Status": "Erro API",
                    "Observação": "Falha na chamada Gemini"
                })

            time.sleep(1.5)

        df['post_content'] = updated_contents
        df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
        print(f"{Colors.OKGREEN}>> Salvo: {file_path}{Colors.ENDC}")

    # Gerar Relatório
    if report_data:
        report_df = pd.DataFrame(report_data)
        os.makedirs("relatorios", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = f"relatorios/relatorio_otimizacao_{timestamp}.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# 📊 Relatório de Auditoria e Otimização SEO/AIO\n\n")
            f.write(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"**Modelo:** {args.model}\n\n")
            f.write(report_df.to_markdown(index=False))

        print(f"\n📊 Relatório salvo em {report_path}")

if __name__ == "__main__":
    main()
