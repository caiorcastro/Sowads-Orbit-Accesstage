
import requests
import json
import argparse
import time

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def submit_urls_to_bing(api_key, host_url, url_list):
    """
    Submits a list of URLs to Bing via the IndexNow protocol.
    Docs: https://www.bing.com/indexnow
    """
    endpoint = "https://api.indexnow.org/indexnow"
    
    payload = {
        "host": host_url.replace("https://", "").replace("http://", ""),
        "key": api_key,
        "keyLocation": f"{host_url}/{api_key}.txt",
        "urlList": url_list
    }

    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }

    try:
        print(f"{Colors.HEADER}Sending {len(url_list)} URLs to Bing IndexNow...{Colors.ENDC}")
        response = requests.post(endpoint, data=json.dumps(payload), headers=headers)
        
        if response.status_code == 200:
            print(f"{Colors.OKGREEN}SUCCESS: Bing received the URLs via IndexNow.{Colors.ENDC}")
            print(f"Response: {response.text}")
        elif response.status_code == 202:
             print(f"{Colors.OKGREEN}ACCEPTED: Bing accepted the request (202).{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}ERROR: Failed with status {response.status_code}{Colors.ENDC}")
            print(f"Details: {response.text}")
            
    except Exception as e:
        print(f"{Colors.FAIL}EXCEPTION: {e}{Colors.ENDC}")

def main():
    parser = argparse.ArgumentParser(description="Bing IndexNow Force Pusher")
    parser.add_argument("--api_key", required=True, help="Your IndexNow API Key")
    parser.add_argument("--host", required=True, help="Your domain, e.g., https://www.sowads.com.br")
    parser.add_argument("--urls_file", help="Text file with list of URLs to submit")
    parser.add_argument("--single_url", help="Submit a single URL")
    
    args = parser.parse_args()

    urls_to_submit = []

    if args.single_url:
        urls_to_submit.append(args.single_url)
    
    if args.urls_file:
        try:
            with open(args.urls_file, 'r') as f:
                lines = f.readlines()
                urls_to_submit.extend([line.strip() for line in lines if line.strip()])
        except Exception as e:
            print(f"Error reading file: {e}")

    if not urls_to_submit:
        print(f"{Colors.WARNING}No URLs provided. Use --single_url or --urls_file{Colors.ENDC}")
        return

    # Batch submission (IndexNow allows up to 10k items per post, but we act safe)
    submit_urls_to_bing(args.api_key, args.host, urls_to_submit)

if __name__ == "__main__":
    main()
