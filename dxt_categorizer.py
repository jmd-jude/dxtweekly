import json
from anthropic import Anthropic
from supabase import create_client
import os
from dotenv import load_dotenv

class DXTCategorizer:
    def __init__(self, anthropic_api_key, supabase_url, supabase_key):
        self.claude = Anthropic(api_key=anthropic_api_key)
        self.supabase = create_client(supabase_url, supabase_key)
        
        # Predefined categories to maintain consistency
        self.categories = [
            "Development Tools",
            "Data & Analytics", 
            "Content Creation",
            "Productivity & Organization",
            "Communication & Collaboration",
            "Security & Privacy",
            "AI & Machine Learning",
            "Cloud & Infrastructure",
            "Business & Finance",
            "Research & Education",
            "Other"
        ]
    
    def get_uncategorized_dxts(self):
        """Get DXTs that haven't been categorized yet"""
        result = self.supabase.table('dxt_extensions').select(
            'id, name, description, long_description, tools'
        ).is_('category', None).execute()
        
        return result.data
    
    def categorize_batch(self, dxts, batch_size=10):
        """Send batch of DXTs to Claude for categorization"""
        
        # Prepare data for Claude
        dxt_data = []
        for dxt in dxts[:batch_size]:
            description = dxt.get('long_description') or dxt.get('description', '')
            tools = dxt.get('tools', [])
            if isinstance(tools, str):
                tools = json.loads(tools) if tools else []
            
            dxt_data.append({
                'id': dxt['id'],
                'name': dxt.get('name', 'Unnamed'),
                'description': description,
                'tools': tools
            })
        
        prompt = f"""You're analyzing Desktop Extensions (DXTs) for AI applications to categorize them by function.

    Available categories: {', '.join(self.categories)}

    For each DXT below, assign it to the most appropriate category based on its description and capabilities:

    {json.dumps(dxt_data, indent=2)}

    Respond with ONLY a JSON array like this:
    [
    {{"id": 1, "category": "Development Tools", "reasoning": "Brief explanation"}},
    {{"id": 2, "category": "Data & Analytics", "reasoning": "Brief explanation"}}
    ]

    Choose the single most appropriate category for each. Use "Other" sparingly only if nothing else fits."""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system="You are a technology categorization expert. Output only valid JSON.",
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Get raw response and strip markdown formatting
            raw_response = response.content[0].text.strip()
            
            # Remove markdown code blocks if present
            if raw_response.startswith('```json'):
                raw_response = raw_response[7:]  # Remove ```json
            if raw_response.startswith('```'):
                raw_response = raw_response[3:]   # Remove ``` 
            if raw_response.endswith('```'):
                raw_response = raw_response[:-3]  # Remove closing ```
            
            raw_response = raw_response.strip()
            
            # Parse Claude's response
            categorizations = json.loads(raw_response)
            return categorizations
            
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")
            print(f"Raw response was: '{raw_response}'")
            return []
        except Exception as e:
            print(f"Error categorizing batch: {e}")
            return []
    
    def update_categories(self, categorizations):
        """Update database with categorizations"""
        for item in categorizations:
            try:
                self.supabase.table('dxt_extensions').update({
                    'category': item['category'],
                    'category_reasoning': item.get('reasoning', '')
                }).eq('id', item['id']).execute()
                
                print(f"Updated {item['id']}: {item['category']}")
            except Exception as e:
                print(f"Error updating {item['id']}: {e}")
    
    def run_categorization(self):
        """Main method to categorize all uncategorized DXTs"""
        print("Starting DXT categorization...")
        
        uncategorized = self.get_uncategorized_dxts()
        print(f"Found {len(uncategorized)} uncategorized DXTs")
        
        # Process in batches
        for i in range(0, len(uncategorized), 10):
            batch = uncategorized[i:i+10]
            print(f"\nProcessing batch {i//10 + 1}...")
            
            categorizations = self.categorize_batch(batch)
            if categorizations:
                self.update_categories(categorizations)
        
        print("\nCategorization complete!")
    
    def get_category_stats(self):
        """Get category distribution stats"""
        result = self.supabase.table('dxt_extensions').select(
            'category'
        ).not_.is_('category', None).execute()
        
        from collections import Counter
        categories = [item['category'] for item in result.data]
        stats = Counter(categories)
        
        print("\n📊 DXT Category Distribution:")
        for category, count in stats.most_common():
            print(f"  {category}: {count}")
        
        return stats
    
def main():
    load_dotenv()
    
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    SUPABASE_URL = os.getenv('SUPABASE_URL') 
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    
    if not all([ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY]):
        print("Please set ANTHROPIC_API_KEY, SUPABASE_URL, and SUPABASE_KEY environment variables")
        return
    
    # Create categorizer
    categorizer = DXTCategorizer(ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY)
    
    print("Starting DXT categorization for all uncategorized extensions...")
    
    # Run categorization
    categorizer.run_categorization()
    
    # Show results
    categorizer.get_category_stats()

if __name__ == "__main__":
    main()