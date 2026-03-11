import argparse
import glob
import pandas as pd
import google.generativeai as genai
from orbit_optimizer import optimize_content_with_gemini, Colors
import os
import csv
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()

    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel(args.model)

    # Exclude lote_2 which is being processed by the other process
    all_files = glob.glob("output_csv_batches/*.csv")
    target_files = [f for f in all_files if "lote_2" not in f]

    print(f"{Colors.HEADER}=== STARTING PARALLEL OPTIMIZATION (Batches 1, 3-6) ==={Colors.ENDC}")

    report_data = []

    for file_path in sorted(target_files):
        print(f"\nProcessing File: {file_path}")
        df = pd.read_csv(file_path)
        
        updated_contents = []
        for index, row in df.iterrows():
            title = row.get('post_title', 'Unknown')
            content = row.get('post_content', '')
            
            print(f" -> Auditing: {title[:40]}...")
            result = optimize_content_with_gemini(model, content, title)
            
            if result:
                score = result.get('aio_score')
                critique = result.get('critique')
                new_html = result.get('optimized_html')
                print(f"    {Colors.OKGREEN}Score: {score}/10{Colors.ENDC} | Fix: {critique[:60]}...")
                updated_contents.append(new_html)
                report_data.append({"Batch": os.path.basename(file_path), "Title": title, "Score": score, "Critique": critique})
            else:
                updated_contents.append(content)
                report_data.append({"Batch": os.path.basename(file_path), "Title": title, "Score": "ERROR"})
            
            time.sleep(1)

        df['post_content'] = updated_contents
        df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
        print(f"{Colors.OKGREEN}>> Saved Optimized File: {file_path}{Colors.ENDC}")

    # Append to report (simple append mode or separate file)
    report_df = pd.DataFrame(report_data)
    with open("relatorios/relatorio_otimizacao_seo_aio_part2.md", 'w') as f:
        f.write("# Relatório Parcial (Lotes 1, 3-6)\n\n")
        f.write(report_df.to_markdown(index=False))

if __name__ == "__main__":
    main()
