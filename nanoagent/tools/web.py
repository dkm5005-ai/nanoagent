"""Web tools for NanoAgent"""

from typing import Any

import httpx
from bs4 import BeautifulSoup

from .base import Tool, ToolResult


class WebSearchTool(Tool):
    """Tool for searching the web using DuckDuckGo"""

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web using DuckDuckGo. Returns a list of search results "
            "with titles, URLs, and snippets."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Maximum number of results (default: {self.max_results})",
                    "default": self.max_results,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        max_results = max_results or self.max_results

        try:
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", r.get("link", "")),
                        "snippet": r.get("body", r.get("snippet", "")),
                    })

            if not results:
                return ToolResult.success("No results found.")

            # Format results
            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(
                    f"{i}. {r['title']}\n"
                    f"   URL: {r['url']}\n"
                    f"   {r['snippet']}"
                )

            return ToolResult.success("\n\n".join(formatted))

        except ImportError:
            return ToolResult.error(
                "duckduckgo-search package not installed. "
                "Install with: pip install duckduckgo-search"
            )
        except Exception as e:
            return ToolResult.error(f"Search failed: {e}")


class WebFetchTool(Tool):
    """Tool for fetching and parsing web pages"""

    def __init__(self, timeout: int = 30, max_content_length: int = 50000):
        self.timeout = timeout
        self.max_content_length = max_content_length

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a web page and extract its text content. "
            "Useful for reading articles, documentation, etc."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to extract specific content",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        selector: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; NanoAgent/1.0; "
                            "+https://github.com/nanoagent)"
                        ),
                    },
                )
                response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            # Handle non-HTML content
            if "text/html" not in content_type.lower():
                text = response.text[:self.max_content_length]
                if len(response.text) > self.max_content_length:
                    text += f"\n\n[... truncated]"
                return ToolResult.success(text)

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Apply selector if provided
            if selector:
                selected = soup.select(selector)
                if not selected:
                    return ToolResult.error(f"No elements found matching selector: {selector}")
                text = "\n\n".join(el.get_text(separator=" ", strip=True) for el in selected)
            else:
                # Try to find main content
                main = soup.find("main") or soup.find("article") or soup.find("body")
                if main:
                    text = main.get_text(separator=" ", strip=True)
                else:
                    text = soup.get_text(separator=" ", strip=True)

            # Clean up whitespace
            import re
            text = re.sub(r"\s+", " ", text)
            text = re.sub(r"\n\s*\n", "\n\n", text)

            # Truncate if needed
            if len(text) > self.max_content_length:
                text = text[:self.max_content_length] + "\n\n[... truncated]"

            if not text.strip():
                return ToolResult.success("(page has no text content)")

            return ToolResult.success(text.strip())

        except httpx.HTTPStatusError as e:
            return ToolResult.error(f"HTTP {e.response.status_code}: {e.response.reason_phrase}")
        except httpx.RequestError as e:
            return ToolResult.error(f"Request failed: {e}")
        except Exception as e:
            return ToolResult.error(f"Failed to fetch page: {e}")
