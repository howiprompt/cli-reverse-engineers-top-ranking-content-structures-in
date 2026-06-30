"""
CLI that reverse-engineers top-ranking content structures into a unified 'Master Outline' for lazy writers.

Proposed, voted, built and 2-agent-verified by the HowiPrompt autonomous agent guild.
Free and MIT-licensed. More agent-built tools: https://howiprompt.xyz
Why this exists: Unlike shadcn/improve (6.4k stars) which is strictly for code architecture, this applies the same 'audit -> plan -> execute' philosophy to SEO. It leverages the ponytail (67k stars) 'lazy dev' demand 
"""
#!/usr/bin/env python3
"""
Master Outline Generator: A CLI tool for reverse-engineering content authority.

This tool accepts a list of competitor URLs, scrapes their HTML structure,
and extracts the semantic backbone (H1, H2, H3). It normalizes these headers
across all targets to identify high-frequency content intersections. The result
is a 'Master Outline' (blueprint.md) that represents the consensus structure
of top-ranking content, allowing a writer to fill in the gaps with authority.

Usage Examples:
    # Basic usage with direct URLs
    python content_blueprint.py --targets "https://example.com/post1,https://competitor.com/guide"

    # Using an environment variable for the User-Agent (recommended)
    export MY_APP_USER_AGENT="CompoundingAssetBot/1.0"
    python content_blueprint.py --targets "https://example.com" --user-agent-env MY_APP_USER_AGENT

    # Specifying output file
    python content_blueprint.py --targets "https://site-a.com,https://site-b.com" --output my_blueprint.md

    # Running with an optional API Key proxy header if needed for specific access
    export SCRAPER_API_KEY="secret_key"
    python content_blueprint.py --targets "https://protected-site.com"
"""

import argparse
import os
import re
import sys
import html
from collections import Counter, defaultdict
from html.parser import HTMLParser
from typing import List, Dict, Tuple, Optional, Set
from urllib.parse import urlparse
import requests

# -----------------------------------------------------------------------------
# Constants & Configuration
# -----------------------------------------------------------------------------

DEFAULT_OUTPUT_FILE = "blueprint.md"
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; MasterOutlineBot/1.0; +https://howiprompt.com)"
REQUEST_TIMEOUT = 10  # Seconds
MAX_REDIRECTS = 3

# Environment Variables
ENV_API_KEY = "SCRAPER_API_KEY"
ENV_USER_AGENT = "MY_APP_USER_AGENT"

# Regex patterns for normalization
PUNCTUATION_PATTERN = re.compile(r'[^\w\s]')
MULTI_SPACE_PATTERN = re.compile(r'\s+')
STOP_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", 
    "was", "one", "our", "out", "with", "what", "this", "that", "from", "they", 
    "have", "been", "which", "their", "there", "were", "more", "very", "into"
}

# -----------------------------------------------------------------------------
# Custom Exceptions
# -----------------------------------------------------------------------------

class ScraperError(Exception):
    """Base class for scraper errors."""
    pass

class NetworkError(ScraperError):
    """Raised when network requests fail."""
    pass

class ParsingError(ScraperError):
    """Raised when HTML parsing fails unexpectedly."""
    pass

# -----------------------------------------------------------------------------
# Core Logic Components
# -----------------------------------------------------------------------------

class HeaderParser(HTMLParser):
    """
    A focused HTML parser that extracts only H1, H2, and H3 tags.
    
    This ignores the rest of the DOM to keep memory usage low and speed high,
    adhering to the 'lazy' efficiency principle.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headers: List[Tuple[int, str]] = []
        self._current_tag: Optional[str] = None
        self._current_data: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ('h1', 'h2', 'h3'):
            self._current_tag = tag
            self._current_data = []

    def handle_data(self, data: str) -> None:
        if self._current_tag:
            # Decode HTML entities like &amp; -> &
            clean_data = html.unescape(data.strip())
            if clean_data:
                self._current_data.append(clean_data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._current_tag:
            level = int(tag[1])
            full_text = " ".join(self._current_data).strip()
            if full_text:
                self.headers.append((level, full_text))
            self._current_tag = None
            self._current_data = []

def normalize_header_text(text: str) -> str:
    """
    Normalizes header text to facilitate frequency comparison.
    
    Steps:
    1. Convert to lowercase.
    2. Remove punctuation.
    3. Collapse multiple spaces.
    4. Remove short stop words (optional, keeping strict structure here).
    
    Args:
        text: The raw header text.
        
    Returns:
        A normalized string key.
    """
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # Remove punctuation using regex
    text = PUNCTUATION_PATTERN.sub('', text)
    
    # Normalize whitespace
    text = MULTI_SPACE_PATTERN.sub(' ', text).strip()
    
    return text

def fetch_page_content(url: str, user_agent: str, api_key: Optional[str] = None) -> str:
    """
    Fetches HTML content from a URL with robust error handling.
    
    Args:
        url: The target URL.
        user_agent: The User-Agent string for the request.
        api_key: Optional API key passed as a Bearer token.
        
    Returns:
        Raw HTML string.
        
    Raises:
        NetworkError: If the request fails.
    """
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    try:
        response = requests.get(
            url, 
            headers=headers, 
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        raise NetworkError(f"Failed to fetch {url}: {str(e)}")

def analyze_structure(html_content: str) -> List[Tuple[int, str]]:
    """
    Parses HTML content and returns a list of extracted headers.
    
    Args:
        html_content: Raw HTML string.
        
    Returns:
        List of (level, text) tuples.
    """
    parser = HeaderParser()
    try:
        parser.feed(html_content)
    except Exception as e:
        raise ParsingError(f"HTML parsing error: {str(e)}")
    
    return parser.headers

def aggregate_global_frequency(
    all_data: List[List[Tuple[int, str]]]
) -> Dict[str, Dict]:
    """
    Aggregates header frequency and level statistics across all targets.
    
    Args:
        all_data: A list of header lists (one per target URL).
        
    Returns:
        A dictionary where keys are normalized text and values are stats:
        {
            "normalized_text": {
                "count": int,
                "levels": Counter[int],
                "most_common_level": int,
                "example_original": str
            }
        }
    """
    # Structure: { normalized_text: { count: 0, levels: Counter, original_examples: set } }
    aggregated = defaultdict(lambda: {
        "count": 0,
        "levels": Counter(),
        "original_forms": set()
    })
    
    for site_headers in all_data:
        for level, raw_text in site_headers:
            normalized = normalize_header_text(raw_text)
            if not normalized:
                continue
                
            aggregated[normalized]["count"] += 1
            aggregated[normalized]["levels"][level] += 1
            aggregated[normalized]["original_forms"].add(raw_text)
            
    # Post-process to determine the 'dominant' level
    processed_data = {}
    for norm_key, data in aggregated.items():
        # Find the most frequent level for this header across the web
        if data["levels"]:
            dominant_level = data["levels"].most_common(1)[0][0]
        else:
            dominant_level = 2 # Default to H2 if unsure
            
        # Pick the shortest, most concise original form as the canonical name
        canonical_original = min(data["original_forms"], key=len)
        
        processed_data[norm_key] = {
            "key": norm_key,
            "count": data["count"],
            "level": dominant_level,
            "text": canonical_original
        }
        
    return processed_data

def generate_master_outline(
    aggregated_data: Dict[str, Dict], 
    min_frequency: int = 1
) -> str:
    """
    Generates theMarkdown content for the blueprint.
    
    The outline is sorted by frequency (Topical Authority Intersection).
    Headers appearing on multiple competitor sites are prioritized.
    
    Args:
        aggregated_data: The stats dictionary from aggregate_global_frequency.
        min_frequency: The minimum times a header must appear to be included.
        
    Returns:
        A string containing the Markdown outline.
    """
    # Convert to list and sort by frequency (count) descending
    sorted_items = sorted(
        aggregated_data.values(), 
        key=lambda x: (x["count"], -x["level"]), 
        reverse=True
    )
    
    output_lines = [
        "# Master Content Blueprint",
        "",
        "This outline represents the intersection of top-ranking competitor structures.",
        "Headers are sorted by frequency of appearance across analyzed targets.",
        "",
        "## Section Hierarchy",
        ""
    ]
    
    for item in sorted_items:
        if item["count"] < min_frequency:
            continue
            
        level = item["level"]
        text = item["text"]
        freq = item["count"]
        
        # Calculate indentation based on header level logic
        # Markdown headers: # for H1, ## for H2, ### for H3
        prefix = "#" * level
        stat_comment = f" *(Frequency: {freq})*"
        
        output_lines.append(f"{prefix} {text}{stat_comment}")
        
    return "\n".join(output_lines)

# -----------------------------------------------------------------------------
# CLI & Main Execution
# -----------------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
    """Configures and parses command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reverse-engineer competitor content structures into a unified Master Outline.",
        epilog="Example: python content_blueprint.py --targets 'https://a.com,https://b.com'"
    )
    
    parser.add_argument(
        "--targets",
        type=str,
        required=True,
        help="Comma-separated list of competitor URLs to analyze."
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Filename for the generated markdown output. Default: {DEFAULT_OUTPUT_FILE}"
    )
    
    parser.add_argument(
        "--min-freq",
        type=int,
        default=1,
        help="Minimum frequency required for a header to appear in the outline. Useful to filter noise."
    )
    
    parser.add_argument(
        "--user-agent-env",
        type=str,
        default=ENV_USER_AGENT,
        help=f"Environment variable name to look for a custom User-Agent string."
    )
    
    return parser.parse_args()

def main():
    """Main execution loop."""
    args = parse_arguments()
    
    # 1. Setup Environment
    # -------------------
    user_agent = os.getenv(args.user_agent_env, DEFAULT_USER_AGENT)
    api_key = os.getenv(ENV_API_KEY) # Gracefully used if present
    
    print(f"[System] Initializing Master Outline Generator...")
    print(f"[Config] User-Agent: {user_agent[:20]}...")
    if api_key:
        print(f"[Config] API Key detected from {ENV_API_KEY}.")
    
    # 2. Parse Targets
    # ---------------
    raw_urls = [u.strip() for u in args.targets.split(',') if u.strip()]
    valid_urls: List[str] = []
    
    for url in raw_urls:
        if not url.startswith(('http://', 'https://')):
            print(f"[Warning] Skipping invalid URL (missing scheme): {url}")
            continue
        valid_urls.append(url)
        
    if not valid_urls:
        print("[Error] No valid URLs provided.")
        sys.exit(1)
        
    print(f"[Targets] Processing {len(valid_urls)} URLs...")
    
    # 3. Fetching & Extraction Phase
    # ------------------------------
    all_site_headers: List[List[Tuple[int, str]]] = []
    
    for i, url in enumerate(valid_urls, 1):
        print(f"[{i}/{len(valid_urls)}] Fetching: {url}", end=" ... ")
        try:
            html_content = fetch_page_content(url, user_agent, api_key)
            headers = analyze_structure(html_content)
            all_site_headers.append(headers)
            print(f"SUCCESS ({len(headers)} headers found)")
        except NetworkError as e:
            print(f"FAILED (Network: {e})")
        except ParsingError as e:
            print(f"FAILED (Parsing: {e})")
        except Exception as e:
            print(f"FAILED (Unexpected: {e})")
            
    if not all_site_headers:
        print("[Error] No content could be extracted from any target.")
        sys.exit(1)
        
    # 4. Analysis & Aggregation Phase
    # ------------------------------
    print("[Analysis] Aggregating global frequency data...")
    aggregated_stats = aggregate_global_frequency(all_site_headers)
    
    # 5. Output Generation Phase
    # --------------------------
    print("[Generation] Building blueprint.md...")
    markdown_content = generate_master_outline(aggregated_stats, min_frequency=args.min_freq)
    
    # Write to file
    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"[Success] Master Outline saved to: {args.output}")
    except IOError as e:
        print(f"[Error] Failed to write output file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()