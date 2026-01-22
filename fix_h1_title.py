
import pandas as pd
import os
import re
import glob
import csv

def fix_batch(file_path):
    print(f"Processing: {file_path}")
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    updated_titles = []
    updated_contents = []
    changes_count = 0

    for index, row in df.iterrows():
        title = row.get('post_title', '')
        content = str(row.get('post_content', ''))
        
        # Regex to find <h1>...</h1>
        # We look for the first H1
        match = re.search(r'<h1>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
        
        if match:
            h1_text = match.group(1).strip()
            
            # Remove HTML tags from title if any (clean text)
            clean_title = re.sub(r'<[^>]+>', '', h1_text)
            
            # Update Title
            new_title = clean_title
            
            # Remove H1 from content
            # We replace the whole <h1>...</h1> match with empty string
            new_content = content.replace(match.group(0), '', 1)
            
            # Simple cleanup of leading whitespace
            new_content = new_content.strip()
            
            updated_titles.append(new_title)
            updated_contents.append(new_content)
            changes_count += 1
        else:
            updated_titles.append(title)
            updated_contents.append(content)

    if changes_count > 0:
        df['post_title'] = updated_titles
        df['post_content'] = updated_contents
        df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
        print(f" >> Fixed {changes_count} articles in {os.path.basename(file_path)}")
    else:
        print(f" >> No H1 changes needed for {os.path.basename(file_path)}")

def main():
    files = glob.glob("output_csv_batches*/*.csv")
    for f in files:
        fix_batch(f)

if __name__ == "__main__":
    main()
