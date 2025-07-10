import requests
import json
import os
from datetime import datetime, timedelta
from supabase import create_client, Client
import time
import base64
from dotenv import load_dotenv

class DXTDiscovery:
    def __init__(self, github_token, supabase_url, supabase_key):
        self.github_headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
    def search_dxt_repositories(self):
        """Search for repositories that might contain DXT extensions"""
        search_queries = [
            'manifest.json dxt extension',
            'anthropic dxt',
            'filename:manifest.json "dxt_version"',
            'mcp server extension'
        ]
        
        # Get existing repositories to avoid reprocessing
        existing_repos = set()
        try:
            # Get repos already in the DXT extensions table
            dxt_repos = self.supabase.table('dxt_extensions').select('repo_name').execute()
            existing_repos.update(repo['repo_name'] for repo in dxt_repos.data)
            
            # Get repos already checked and found to be non-DXT
            non_dxt_repos = self.supabase.table('non_dxt_repos').select('repo_name').execute()
            existing_repos.update(repo['repo_name'] for repo in non_dxt_repos.data)
        except Exception as e:
            print(f"Warning: Could not fetch existing repos: {e}")
        
        all_repos = set()
        
        for query in search_queries:
            print(f"Searching for: {query}")
            
            # Search repositories
            repo_url = f"https://api.github.com/search/repositories"
            repo_params = {
                'q': query,
                'sort': 'updated',
                'per_page': 100
            }
            
            repo_response = requests.get(repo_url, headers=self.github_headers, params=repo_params)
            
            if repo_response.status_code == 200:
                repos = repo_response.json().get('items', [])
                for repo in repos:
                    repo_name = repo['full_name']
                    if repo_name not in existing_repos:  # Skip already processed
                        all_repos.add((repo_name, repo['html_url'], repo.get('stargazers_count', 0), repo.get('updated_at', '')))
            
            # Search code for manifest.json files
            code_url = f"https://api.github.com/search/code"
            code_params = {
                'q': query,
                'per_page': 100
            }
            
            code_response = requests.get(code_url, headers=self.github_headers, params=code_params)
            
            if code_response.status_code == 200:
                files = code_response.json().get('items', [])
                for file in files:
                    repo = file['repository']
                    repo_name = repo['full_name']
                    if repo_name not in existing_repos:  # Skip already processed
                        all_repos.add((repo_name, repo['html_url'], repo.get('stargazers_count', 0), repo.get('updated_at', '')))
            
            # Rate limiting - GitHub allows 30 requests per minute for search
            time.sleep(2)
        
        return list(all_repos)
    
    def get_manifest_content(self, repo_full_name):
        """Try to find and read manifest.json from a repository"""
        possible_paths = [
            'manifest.json',
            'dxt/manifest.json',
            'extension/manifest.json',
            'src/manifest.json'
        ]
        
        for path in possible_paths:
            url = f"https://api.github.com/repos/{repo_full_name}/contents/{path}"
            response = requests.get(url, headers=self.github_headers)
            
            if response.status_code == 200:
                file_data = response.json()
                if file_data.get('type') == 'file':
                    # Decode base64 content
                    content = base64.b64decode(file_data['content']).decode('utf-8')
                    try:
                        manifest = json.loads(content)
                        # Check if it's actually a DXT manifest
                        if 'dxt_version' in manifest:
                            return manifest, path
                    except json.JSONDecodeError:
                        continue
            
            time.sleep(0.5)  # Small delay to be nice to GitHub API
        
        return None, None
    
    def get_repo_details(self, repo_full_name):
        """Get detailed repository information from GitHub API"""
        url = f"https://api.github.com/repos/{repo_full_name}"
        response = requests.get(url, headers=self.github_headers)
        
        if response.status_code == 200:
            repo_data = response.json()
            return {
                'updated_at': repo_data.get('updated_at'),
                'stars': repo_data.get('stargazers_count', 0),
                'url': repo_data.get('html_url', '')
            }
        else:
            print(f"Warning: Could not fetch details for {repo_full_name}")
            return {'updated_at': None, 'stars': 0, 'url': ''}
    
    def extract_dxt_info(self, manifest, repo_full_name):
        """Extract relevant information from manifest and repo"""
        # Get fresh repo details for accurate timestamps
        repo_details = self.get_repo_details(repo_full_name)
        
        return {
            'repo_name': repo_full_name,
            'repo_url': repo_details['url'],
            'stars': repo_details['stars'],
            'repo_updated_at': repo_details['updated_at'],
            'discovered_at': datetime.now().isoformat(),
            
            # From manifest
            'name': manifest.get('name', ''),
            'display_name': manifest.get('display_name', manifest.get('name', '')),
            'version': manifest.get('version', ''),
            'description': manifest.get('description', ''),
            'long_description': manifest.get('long_description', ''),
            'author_name': manifest.get('author', {}).get('name', ''),
            'author_email': manifest.get('author', {}).get('email', ''),
            'author_url': manifest.get('author', {}).get('url', ''),
            'homepage': manifest.get('homepage', ''),
            'documentation': manifest.get('documentation', ''),
            'keywords': json.dumps(manifest.get('keywords', [])),
            'license': manifest.get('license', ''),
            'server_type': manifest.get('server', {}).get('type', ''),
            'tools': json.dumps([tool.get('name', '') for tool in manifest.get('tools', [])]),
            'tools_count': len(manifest.get('tools', [])),
            'has_user_config': len(manifest.get('user_config', {})) > 0,
            'dxt_version': manifest.get('dxt_version', ''),
            'manifest_raw': json.dumps(manifest, indent=2)
        }
    
    def save_to_supabase(self, dxt_data):
        """Save DXT information to Supabase"""
        try:
            # Check if this repo already exists
            existing = self.supabase.table('dxt_extensions').select('*').eq('repo_name', dxt_data['repo_name']).execute()
            
            if existing.data:
                # Update existing record
                result = self.supabase.table('dxt_extensions').update(dxt_data).eq('repo_name', dxt_data['repo_name']).execute()
                print(f"Updated: {dxt_data['name']} ({dxt_data['repo_name']})")
            else:
                # Insert new record
                result = self.supabase.table('dxt_extensions').insert(dxt_data).execute()
                print(f"Added: {dxt_data['name']} ({dxt_data['repo_name']})")
                
        except Exception as e:
            print(f"Error saving {dxt_data['repo_name']}: {e}")
    
    def discover_and_save_all(self):
        """Main method to discover DXTs and save to database"""
        print("Starting DXT discovery...")
        
        # Find repositories
        repos = self.search_dxt_repositories()
        print(f"Found {len(repos)} potential repositories")
        
        dxt_count = 0
        
        for repo_info in repos:
            repo_full_name = repo_info[0]
            print(f"\nChecking {repo_full_name}...")
            
            # Try to get manifest
            manifest, manifest_path = self.get_manifest_content(repo_full_name)
            
            if manifest:
                print(f"Found DXT manifest at {manifest_path}")
                
                # Extract and save data
                dxt_data = self.extract_dxt_info(manifest, repo_full_name)
                self.save_to_supabase(dxt_data)
                dxt_count += 1
            else:
                print("No valid DXT manifest found")
                # Track as non-DXT to avoid future rechecking
                try:
                    self.supabase.table('non_dxt_repos').insert({'repo_name': repo_full_name}).execute()
                except:
                    pass  # Might already exist, ignore duplicate errors
        
        print(f"\nDiscovery complete! Found {dxt_count} DXT extensions")

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Configuration - you'll need to set these
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # Get from GitHub settings -> Developer settings -> Personal access tokens
    SUPABASE_URL = os.getenv('SUPABASE_URL')  # From your Supabase project settings
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')  # Supabase anon/public key
    
    if not all([GITHUB_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
        print("Please set GITHUB_TOKEN, SUPABASE_URL, and SUPABASE_KEY environment variables")
        return
    
    discovery = DXTDiscovery(GITHUB_TOKEN, SUPABASE_URL, SUPABASE_KEY)
    discovery.discover_and_save_all()

if __name__ == "__main__":
    main()
