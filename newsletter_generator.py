import os
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv
import json
from anthropic import Anthropic

print("Script starting...")

class ClaudeNewsletterGenerator:
    def __init__(self, supabase_url, supabase_key, anthropic_api_key):
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.claude = Anthropic(api_key=anthropic_api_key)
    
    def get_dxts_for_newsletter(self, limit=5):
        """Get unfeatured DXTs for the newsletter"""
        try:
            # Get unfeatured DXTs, ordered by stars and recency
            result = self.supabase.table('dxt_extensions').select('*').eq('featured_in_newsletter', False).order('stars', desc=True).order('discovered_at', desc=True).limit(limit).execute()
            
            # If no unfeatured DXTs, get any DXTs (for first issue)
            if not result.data:
                result = self.supabase.table('dxt_extensions').select('*').order('stars', desc=True).limit(limit).execute()
            
            return result.data
        except Exception as e:
            print(f"Error fetching DXTs: {e}")
            return []
    
    def generate_dxt_content_with_claude(self, dxt):
        """Use Claude API to generate engaging content for a DXT"""
        
        # Prepare DXT data for Claude
        name = dxt.get('display_name') or dxt.get('name', 'Unnamed Extension')
        description = dxt.get('description', '')
        long_description = dxt.get('long_description', '')
        author = dxt.get('author_name', 'Unknown Author')
        repo_url = dxt.get('repo_url', '')
        stars = dxt.get('stars', 0)
        tools = dxt.get('tools', [])
        server_type = dxt.get('server_type', '')
        category = dxt.get('category', 'Uncategorized')
        category_reasoning = dxt.get('category_reasoning', '')
        
        # Parse tools if it's a JSON string
        if isinstance(tools, str):
            try:
                tools = json.loads(tools)
            except:
                tools = []
        
        # Create prompt for Claude
        prompt = f"""You're writing for DXT Weekly, a newsletter about Desktop Extensions (DXTs) for AI applications like Claude. Your audience is developers, productivity enthusiasts, and AI power users.

Write a compelling newsletter entry for this DXT:

**Name:** {name}
**Author:** {author}
**Description:** {description}
**Long Description:** {long_description}
**Tools:** {', '.join(tools) if tools else 'Not specified'}
**Server Type:** {server_type}
**GitHub Stars:** {stars}
**Repository:** {repo_url}
**Category:** {category}
**Category Reasoning:** {category_reasoning}

Please write:
1. An engaging headline (different from the repo name, focused on what it does)
2. A 2-3 sentence narrative explaining what this does and why someone would want it
3. A brief use case example ("Good for..." or "Useful when...")

Keep it professional, clear, and focused on practical value. No emojis. Don't mention the technical details like server type unless relevant to the user.

IMPORTANT: Output ONLY the newsletter entry content. Do not include any notes, commentary, or explanations about your writing process. Do not add "Note:" sections.

Output format should be exactly:
**[Your Headline]**
by [Author]

[Your narrative and use case content]

View on GitHub: {repo_url}

--

Nothing else."""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system="You are a professional newsletter writer. Output only the requested content with no meta-commentary, notes, or explanations about your writing process.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.content[0].text.strip()
            
            # Post-processing: Remove any lines starting with "Note:"
            lines = content.split('\n')
            clean_lines = [line for line in lines if not line.strip().lower().startswith('note:')]
            content = '\n'.join(clean_lines).strip()
            
            return content
            
        except Exception as e:
            print(f"Error generating content with Claude for {name}: {e}")
            # Fallback to simple template
            return f"""### {name}
*by {author}*

{description or long_description}

View on GitHub: {repo_url}

---"""
    
    def generate_newsletter_intro_with_claude(self, dxts, issue_number=1):
        """Generate newsletter intro using Claude"""
        
        dxt_summaries = []
        for dxt in dxts:
            name = dxt.get('display_name') or dxt.get('name', 'Unnamed')
            description = dxt.get('description', '')
            dxt_summaries.append(f"- {name}: {description}")
        
        prompt = f"""You're writing issue #{issue_number} of DXT Weekly, a newsletter about Desktop Extensions for AI applications.

DXTs are like browser extensions but for AI apps like Claude - they add new capabilities through the Model Context Protocol.

This issue features:
{chr(10).join(dxt_summaries)}

Write a brief, engaging introduction (2-3 paragraphs) that:
1. Welcomes readers to this issue of DXT Weekly
2. Sets up excitement for the extensions we're featuring

Keep it professional and accessible. No emojis.

IMPORTANT: Output only the introduction text. No notes or commentary about your writing."""
        
        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                system="You are a professional newsletter writer. Output only the requested content with no meta-commentary or explanations.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            content = response.content[0].text.strip()
            
            # Post-processing: Remove any lines starting with "Note:"
            lines = content.split('\n')
            clean_lines = [line for line in lines if not line.strip().lower().startswith('note:')]
            content = '\n'.join(clean_lines).strip()
            
            return content
            
        except Exception as e:
            print(f"Error generating intro with Claude: {e}")
            # Fallback
            return f"Welcome to DXT Weekly Issue #{issue_number}! Here are the most interesting Desktop Extensions we've discovered:"
    
    def generate_newsletter_content(self, issue_number=1):
        """Generate complete newsletter content using Claude API"""
        
        # Get DXTs to feature
        dxts = self.get_dxts_for_newsletter()
        
        if not dxts:
            return "No DXTs found to feature. Check your database connection."
        
        print(f"Generating content for {len(dxts)} DXTs using Claude API...")
        
        # Generate intro with Claude
        intro = self.generate_newsletter_intro_with_claude(dxts, issue_number)
        
        # Generate date and header
        current_date = datetime.now().strftime("%B %d, %Y")
        header = f"DXT Weekly #{issue_number}"
        
        # Start newsletter
        newsletter = f"""# {header}
*{current_date}*

{intro}

"""
        
        # Generate content for each DXT using Claude
        for i, dxt in enumerate(dxts, 1):
            print(f"Generating content for DXT {i}/{len(dxts)}: {dxt.get('name', 'Unnamed')}")
            dxt_content = self.generate_dxt_content_with_claude(dxt)
            newsletter += dxt_content + "\n\n"
        
        # Add footer
        newsletter += f"""## What's Next

The DXT ecosystem is growing rapidly! We're tracking {len(dxts)} extensions and counting.

**Got a DXT to share?** Drop us a line - we'd love to feature it in next week's issue.

**Want to build your own DXT?** Check out Anthropic's DXT documentation: https://github.com/anthropics/dxt to get started.

---

*DXT Weekly is an independent newsletter tracking the Desktop Extension ecosystem. Not affiliated with Anthropic.*

**Subscribe at dxtweekly.com** | **Suggest a DXT** | **Sponsor this newsletter**"""
        
        return newsletter
    
    def save_to_markdown(self, content, issue_number):
        """Save newsletter content to markdown file"""
        filename = os.path.join("newsletters", f"newsletter-{issue_number:03d}.md")
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Newsletter saved to {filename}")
            return filename
        except Exception as e:
            print(f"Error saving to markdown: {e}")
            return None
    
    def mark_as_featured(self, dxt_ids, issue_number, newsletter_date=None):
        """Mark DXTs as featured in newsletter"""
        if newsletter_date is None:
            newsletter_date = datetime.now().date().isoformat()
        
        for dxt_id in dxt_ids:
            try:
                self.supabase.table('dxt_extensions').update({
                    'featured_in_newsletter': True,
                    'newsletter_date': newsletter_date,
                    'featured_in_issue': issue_number
                }).eq('id', dxt_id).execute()
            except Exception as e:
                print(f"Error marking DXT {dxt_id} as featured: {e}")
    
    def save_to_supabase_newsletters(self, content, dxts, issue_number):
        """Save newsletter record to Supabase"""
        try:
            # Extract title from content (first line after #)
            lines = content.split('\n')
            title = next((line.strip('# ') for line in lines if line.startswith('# ')), f"DXT Weekly #{issue_number}")
            
            newsletter_data = {
                'issue_number': issue_number,
                'title': title,
                'content': content,
                'status': 'draft'
            }
            
            # Check if this issue already exists
            existing = self.supabase.table('newsletters').select('*').eq('issue_number', issue_number).execute()
            
            if existing.data:
                # Update existing
                result = self.supabase.table('newsletters').update(newsletter_data).eq('issue_number', issue_number).execute()
                print(f"Updated newsletter record for issue #{issue_number}")
            else:
                # Insert new
                result = self.supabase.table('newsletters').insert(newsletter_data).execute()
                print(f"Created newsletter record for issue #{issue_number}")
            
            return result.data[0]['id'] if result.data else None
            
        except Exception as e:
            print(f"Error saving to Supabase: {e}")
            return None
    
    def preview_next_issue(self, issue_number=2):
        """Preview what would be in the next issue"""
        dxts = self.get_dxts_for_newsletter(limit=5)
        
        if not dxts:
            return "No new DXTs to feature in next issue."
        
        preview = f"**Preview of Issue #{issue_number}:**\n\n"
        for dxt in dxts:
            name = dxt.get('display_name') or dxt.get('name', 'Unnamed')
            author = dxt.get('author_name', 'Unknown')
            preview += f"• **{name}** by {author}\n"
        
        return preview
    
    def get_next_issue_number(self):
        """Get the next issue number by finding the highest existing issue and adding 1"""
        try:
            # Get the highest issue number from the database
            result = self.supabase.table('newsletters').select('issue_number').order('issue_number', desc=True).limit(1).execute()
            
            if result.data:
                # If there are existing issues, increment the highest number
                next_issue = result.data[0]['issue_number'] + 1
            else:
                # If no issues exist, start with issue 1
                next_issue = 1
                
            print(f"Next issue number: {next_issue}")
            return next_issue
            
        except Exception as e:
            print(f"Error determining next issue number: {e}")
            # Fallback to issue 1
            return 1

def main():
    load_dotenv()
    
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
    
    if not all([SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY]):
        print("Please set SUPABASE_URL, SUPABASE_KEY, and ANTHROPIC_API_KEY environment variables")
        return
    
    generator = ClaudeNewsletterGenerator(SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY)
    
    # Get the next issue number dynamically
    issue_number = generator.get_next_issue_number()
    
    # Generate newsletter with the correct issue number
    print(f"Generating DXT Weekly Issue #{issue_number} with Claude API...")
    print("=" * 60)
    
    newsletter_content = generator.generate_newsletter_content(issue_number=issue_number)
    print(newsletter_content)
    
    print("\n" + "=" * 60)
    print("Newsletter generated!")
    
    # Get DXTs for saving
    dxts = generator.get_dxts_for_newsletter()
    
    # Save to markdown file with correct issue number
    markdown_file = generator.save_to_markdown(newsletter_content, issue_number=issue_number)
    
    # Save to Supabase with correct issue number
    newsletter_id = generator.save_to_supabase_newsletters(newsletter_content, dxts, issue_number=issue_number)
    
    print(f"\nNewsletter saved to:")
    if markdown_file:
        print(f"  📄 Markdown: {markdown_file}")
    if newsletter_id:
        print(f"  🗄️  Database: Record ID {newsletter_id}")
    
    print("\nReady to publish! You can:")
    print("  - Edit the markdown file if needed")
    print("  - Copy content to Substack")
    print("  - Track status in Supabase")
    
    # Ask if user wants to mark DXTs as featured
    response = input("\nMark these DXTs as featured? (y/n): ").lower()
    if response == 'y':
        dxt_ids = [dxt['id'] for dxt in dxts]
        generator.mark_as_featured(dxt_ids, issue_number)
        print("DXTs marked as featured!")
        
        # Update newsletter status to published with correct issue number
        try:
            generator.supabase.table('newsletters').update({
                'status': 'published',
                'published_at': datetime.now().isoformat()
            }).eq('issue_number', issue_number).execute()
            print("Newsletter status updated to 'published'")
        except Exception as e:
            print(f"Error updating newsletter status: {e}")
        
        # Show preview of next issue
        print("\n" + generator.preview_next_issue(issue_number + 1))
    else:
        print("DXTs not marked as featured - you can generate this issue again later")

if __name__ == "__main__":
    main()