import feedparser
import os
from datetime import datetime
from livekit.agents import function_tool

@function_tool()
async def get_top_news(country: str = "india") -> str:
    """
    Gets latest news from RSS feeds for different countries.
    
    Args:
        country: Country for news (india, usa, uk, australia, canada, technology, business, sports, entertainment)
    
    Returns:
        str: Latest news headlines with links
    """
    try:
        print(f"🔍 Getting news for country: {country}")
        
        # RSS feeds dictionary
        rss_feeds = {
            "india": "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
            "usa": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", 
            "uk": "https://feeds.bbci.co.uk/news/uk/rss.xml",
            "australia": "https://feeds.bbci.co.uk/news/world/australia/rss.xml",
            "canada": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
            "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
            "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
            "sports": "https://feeds.bbci.co.uk/news/sport/rss.xml",
            "entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"
        }
        
        # Check if country exists in feeds
        country_lower = country.lower()
        print(f"📋 Checking country: {country_lower}")
        
        if country_lower not in rss_feeds:
            available_countries = ", ".join(rss_feeds.keys())
            error_msg = f"❌ Country '{country}' not found. Available options: {available_countries}"
            print(error_msg)
            return error_msg
        
        # Get RSS feed
        feed_url = rss_feeds[country_lower]
        print(f"🌐 Fetching RSS feed: {feed_url}")
        
        feed = feedparser.parse(feed_url)
        print(f"✅ RSS feed fetched successfully")
        
        # Check if feed was parsed successfully
        if feed.bozo:
            error_msg = f"❌ RSS feed load karne mein error: {feed.bozo_exception}"
            print(error_msg)
            return error_msg
        
        # Check if entries exist
        if not feed.entries:
            error_msg = f"❌ No news entries found in RSS feed"
            print(error_msg)
            return error_msg
        
        print(f"📰 Found {len(feed.entries)} news entries")
        
        # Format news
        news_output = f"📰 **Latest {country.upper()} News:**\n\n"
        
        for i, entry in enumerate(feed.entries[:5], 1):  # Top 5 news
            title = entry.get('title', 'No title')
            description = entry.get('description', 'No description')
            link = entry.get('link', 'No link')
            
            print(f"📖 Processing news {i}: {title[:50]}...")
            
            news_output += f"{i}. **{title}**\n"
            news_output += f"   📝 {description}\n"
            
        
        news_output += f"---\nTotal {len(feed.entries)} news items available"
        
        print("✅ News formatting completed successfully")
        return news_output
        
    except Exception as e:
        error_msg = f"❌ News fetch karne mein error: {str(e)}"
        print(f"🚨 EXCEPTION: {error_msg}")
        import traceback
        print(f"🔍 Stack trace: {traceback.format_exc()}")
        return error_msg