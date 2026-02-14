"""Sourcing modules for various channels."""

from src.sourcing.github_trending import source_github as source_github_trending
from src.sourcing.github_search import source_github_search
from src.sourcing.linkedin import source_linkedin
from src.sourcing.twitter import source_twitter
from src.sourcing.product_hunt import source_product_hunt
from src.sourcing.hacker_news import source_hacker_news
from src.sourcing.reddit import source_reddit
from src.sourcing.rss import source_rss
from src.sourcing.academic import source_academic

__all__ = [
    "source_github_trending",
    "source_github_search",
    "source_linkedin",
    "source_twitter",
    "source_product_hunt",
    "source_hacker_news",
    "source_reddit",
    "source_rss",
    "source_academic",
]
