"""Retrieve real public posts without invented fallback content."""

from urllib.parse import urlparse

import requests

# Use the public JSON URL shown in the task guide.
URL = "https://www.reddit.com/r/python/.json"
USER_AGENT = "DjangoEcommerceApp/1.0"


class RedditUnavailable(Exception):
    """Represent transport, HTTP or malformed-response failures."""

    def __init__(self, message, status_code=None):
        """Retain the message and optional HTTP status only."""
        super().__init__(message)
        self.status_code = status_code


def fetch_posts():
    """Return ten posts at most with title, author and URL."""
    try:
        response = requests.get(
            URL,
            headers={"User-Agent": USER_AGENT},
            timeout=(3.05, 10),
        )
        response.raise_for_status()
        children = response.json()["data"]["children"]
        if not isinstance(children, list):
            raise ValueError("Reddit children must be a list.")
        posts = []
        for child in children[:10]:
            post = child["data"]
            permalink = post.get("permalink")
            if isinstance(permalink, str) and permalink.startswith("/r/"):
                post["url"] = "https://www.reddit.com" + permalink
            title, author, url = post["title"], post["author"], post["url"]
            if not all(
                isinstance(value, str) for value in (title, author, url)
            ):
                raise ValueError("Invalid post fields.")
            # Reject executable URI schemes before rendering links.
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                continue
            posts.append({"title": title, "author": author, "url": url})
        return posts
    except requests.HTTPError as error:
        # Report the real access failure, not an empty successful feed.
        status = (
            error.response.status_code if error.response is not None else None
        )
        message = "Reddit is unavailable"
        if status is not None:
            message += f" (HTTP {status})"
        if status == 403:
            message += ". Reddit blocked the request; no posts were returned."
        elif status == 429:
            message += ". The rate limit was reached; try again later."
        else:
            message += ". Please try later."
        raise RedditUnavailable(message, status_code=status) from error
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        raise RedditUnavailable(
            "Reddit is unavailable. Please try later."
        ) from error
