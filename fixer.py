import os
import requests
import time
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

class DXTTimestampFixer:
    def __init__(self, github_token, supabase_url, supabase_key):
        self.github_headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.supabase: Client = create_client(supabase_url, supabase_key)
    
    def get_dxts_missing_timestamps(self):
        """Get all DXTs with missing or empty repo_updated_at timestamps"""
        try:
            # Get DXTs where repo_updated_at is null or empty
            result = self.supabase.table('dxt_extensions').select('id, repo_name').is_('repo_updated_at', 'null').execute()
            return result.data
        except Exception as e:
            print(f"Error fetching DXTs: {e}")
            return []
    
    def fetch_repo_timestamp(self, repo_name):
        """Fetch the updated_at timestamp from GitHub API"""
        url = f"https://api.github.com/repos/{repo_name}"
        
        try:
            response = requests.get(url, headers=self.github_headers)
            
            if response.status_code == 200:
                repo_data = response.json()
                updated_at = repo_data.get('updated_at')
                stars = repo_data.get('stargazers_count', 0)
                return updated_at, stars
            elif response.status_code == 404:
                print(f"Repository {repo_name} not found (may be deleted/private)")
                return None, None
            else:
                print(f"Error fetching {repo_name}: HTTP {response.status_code}")
                return None, None
                
        except Exception as e:
            print(f"Error fetching {repo_name}: {e}")
            return None, None
    
    def update_timestamp(self, dxt_id, repo_name, updated_at, stars):
        """Update the timestamp in the database"""
        try:
            update_data = {'repo_updated_at': updated_at}
            
            # Also update stars if we got fresh data
            if stars is not None:
                update_data['stars'] = stars
            
            result = self.supabase.table('dxt_extensions').update(update_data).eq('id', dxt_id).execute()
            
            if result.data:
                star_info = f" (⭐ {stars})" if stars else ""
                print(f"✅ Updated {repo_name}: {updated_at}{star_info}")
            else:
                print(f"❌ Failed to update {repo_name}")
                
        except Exception as e:
            print(f"❌ Error updating {repo_name}: {e}")
    
    def fix_all_timestamps(self):
        """Main method to fix all missing timestamps"""
        print("🔍 Finding DXTs with missing timestamps...")
        
        dxts = self.get_dxts_missing_timestamps()
        
        if not dxts:
            print("✅ No missing timestamps found!")
            return
        
        print(f"📝 Found {len(dxts)} DXTs with missing timestamps")
        print("🔄 Fetching fresh data from GitHub...\n")
        
        success_count = 0
        
        for i, dxt in enumerate(dxts, 1):
            dxt_id = dxt['id']
            repo_name = dxt['repo_name']
            
            print(f"[{i}/{len(dxts)}] Fetching {repo_name}...")
            
            updated_at, stars = self.fetch_repo_timestamp(repo_name)
            
            if updated_at:
                self.update_timestamp(dxt_id, repo_name, updated_at, stars)
                success_count += 1
            else:
                print(f"⚠️  Could not get timestamp for {repo_name}")
            
            # Rate limiting - be nice to GitHub API
            time.sleep(0.5)
        
        print(f"\n🎉 Complete! Updated {success_count}/{len(dxts)} timestamps")
        
        if success_count < len(dxts):
            failed_count = len(dxts) - success_count
            print(f"⚠️  {failed_count} repositories could not be updated (likely deleted/private)")

def main():
    load_dotenv()
    
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    if not all([GITHUB_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
        print("❌ Please set GITHUB_TOKEN, SUPABASE_URL, and SUPABASE_KEY environment variables")
        return
    
    print("🛠️  DXT Timestamp Fixer")
    print("=" * 40)
    
    fixer = DXTTimestampFixer(GITHUB_TOKEN, SUPABASE_URL, SUPABASE_KEY)
    fixer.fix_all_timestamps()

if __name__ == "__main__":
    main()