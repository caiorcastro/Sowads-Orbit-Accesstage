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

    target_files = glob.glob("output_csv_batches_v2/*.csv")
    
    print(f"{Colors.HEADER}=== V2 OPTIMIZATION (Batches in output_csv_batches_v2) ==={Colors.ENDC}")

    for file_path in sorted(target_files):
        print(f"\nProcessing File: {file_path}")
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        updated_contents = []
        changes = 0
        
        for index, row in df.iterrows():
            title = row.get('post_title', 'Unknown')
            content = str(row.get('post_content', ''))
            
            print(f" -> Auditing: {title[:40]}...")
            result = optimize_content_with_gemini(model, content, title)
            
            if result and result.get('optimized_html'):
                updated_contents.append(result.get('optimized_html'))
                changes += 1
            else:
                updated_contents.append(content)
            
            # Rate limit
            time.sleep(1)

        if changes > 0:
            df['post_content'] = updated_contents
            df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
            print(f"{Colors.OKGREEN}>> Optimized & Saved: {file_path}{Colors.ENDC}")
        else:
            print(f"{Colors.OKGREEN}>> No changes needed for: {file_path}{Colors.ENDC}")

if __name__ == "__main__":
    main()
