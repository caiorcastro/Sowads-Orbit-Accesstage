import pandas as pd
import google.generativeai as genai
from d4u_optimizer import optimize_content_with_gemini, Colors
import os
import csv
import time
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True)
    args = parser.parse_args()

    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel("gemini-2.5-flash") # Use Flash for speed on fix

    targets = [
        "output_csv_batches/lote_4_artigos_31_a_40.csv",
        "output_csv_batches/lote_6_artigos_51_a_57.csv",
        "output_csv_batches/lote_5_artigos_41_a_50.csv" # Include 5 just in case (Article 10 failed)
    ]

    print(f"{Colors.HEADER}=== TARGETED FIX (Batches 4, 5, 6) ==={Colors.ENDC}")

    for file_path in targets:
        if not os.path.exists(file_path):
            continue
            
        print(f"\nProcessing File: {file_path}")
        df = pd.read_csv(file_path)
        
        updated_contents = []
        changes = 0
        
        for index, row in df.iterrows():
            title = row.get('post_title', 'Unknown')
            content = str(row.get('post_content', ''))
            
            # Simple heuristic: If it has JSON-LD/Script or missing FAQ section, force optimize
            needs_fix = False
            if '<script type="application/ld+json">' in content:
                needs_fix = True
            if '<section class="faq-section">' not in content:
                 needs_fix = True
            
            if needs_fix:
                print(f" -> Fixing: {title[:40]}...")
                result = optimize_content_with_gemini(model, content, title)
                if result and result.get('optimized_html'):
                    updated_contents.append(result.get('optimized_html'))
                    changes += 1
                else:
                    updated_contents.append(content)
            else:
                updated_contents.append(content)
            
        if changes > 0:
            df['post_content'] = updated_contents
            df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
            print(f"{Colors.OKGREEN}>> Fixed and Saved: {file_path} ({changes} articles updated){Colors.ENDC}")
        else:
            print(f"{Colors.OKGREEN}>> No changes needed for: {file_path}{Colors.ENDC}")

if __name__ == "__main__":
    main()
