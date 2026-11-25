"""Check Reddit access without substituting mocked or saved posts."""

from django.core.management.base import BaseCommand, CommandError

from functions.reddit import fetch_posts, RedditUnavailable


class Command(BaseCommand):
    """Check live access to the task's public JSON feed."""

    help = "Fetch real r/python JSON posts and report whether access works."

    def handle(self, *args, **options):
        """Print received posts or report why display is unverified."""
        try:
            posts = fetch_posts()
        except RedditUnavailable as error:
            raise CommandError(str(error)) from error
        if not posts:
            raise CommandError(
                "Reddit returned no usable posts; live display is unverified."
            )
        self.stdout.write(f"Received {len(posts)} live r/python posts.")
        for post in posts:
            self.stdout.write(
                f"{post['title']} — {post['author']} — {post['url']}"
            )
