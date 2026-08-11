"""
Simple Web Search with Microsoft Edge
Directly opens Edge browser and searches user's query
"""

import webbrowser
import urllib.parse
from livekit.agents import function_tool

@function_tool()
async def search_web(query: str) -> str:
    """
    Opens Microsoft Edge and searches the user's query directly in the browser.
    
    Args:
        query: User's search question or terms
        
    Returns:
        str: Confirmation message that search has been opened
    """
    try:
        # Encode the query for URL
        encoded_query = urllib.parse.quote_plus(query)
        
        # Create search URL
        search_url = f"https://www.bing.com/search?q={encoded_query}"
        
        # Open Microsoft Edge with the search
        webbrowser.register('edge', None, webbrowser.BackgroundBrowser("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"))
        webbrowser.get('edge').open_new_tab(search_url)
        
        return f"✅ मैंने Microsoft Edge में आपकी query '{query}' के लिए search open कर दिया है। ब्राउज़र में results देखें!"
        
    except Exception as e:
        # Fallback - use default browser
        try:
            search_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
            webbrowser.open_new_tab(search_url)
            return f"✅ मैंने आपकी query '{query}' के लिए browser में search open कर दिया है।"
        except Exception as e2:
            return f"❌ Browser में search open करने में problem आई: {e2}"

