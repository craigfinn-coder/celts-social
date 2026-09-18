"""Regression tests for delayed WordPress visibility; no network or rendering."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import poll


def post(pid, slug):
    return {"id": pid, "slug": slug, "status": "publish",
            "date_gmt": f"2026-09-16T16:{pid:02}:00",
            "title": {"rendered": slug},
            "link": f"https://celtsarehere.com/{slug}/"}


class PublishRetryTest(unittest.TestCase):
    def run_poll(self, feeds, hints, argv, rendered=None):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "seen.json"
            state.write_text(json.dumps({"seen": [1], "last_run": None}))
            with (patch.object(poll, "STATE_FILE", state),
                  patch.object(poll, "fetch_posts", side_effect=feeds),
                  patch.object(poll, "fetch_hinted", side_effect=hints),
                  patch.object(poll, "process", return_value=(
                      [Path("card.jpg")] if rendered is None else rendered)) as process,
                  patch.object(poll.time, "sleep") as sleep,
                  patch.object(sys, "argv", ["poll.py", "--no-upload"] + argv),
                  contextlib.redirect_stdout(io.StringIO()),
                  contextlib.redirect_stderr(io.StringIO()) as errors):
                self.assertEqual(poll.main(), 0)
            return (json.loads(state.read_text())["seen"],
                    [c.args[0]["id"] for c in process.call_args_list],
                    sleep.call_count, errors.getvalue())

    def test_previous_post_does_not_satisfy_new_post_ping(self):
        old, newest = post(2, "previous"), post(3, "newest")
        seen, made, sleeps, _ = self.run_poll(
            [[old], [old], [old]], [[], [], [newest]],
            ["--expect-new", "--hint", newest["link"]])
        self.assertEqual(made, [2, 3])
        self.assertEqual(seen, [1, 2, 3])
        self.assertEqual(sleeps, 2)

    def test_already_processed_hint_does_not_wait_for_unrelated_post(self):
        done = post(1, "done")
        seen, made, sleeps, _ = self.run_poll(
            [[done]], [[done]], ["--expect-new", "--hint", done["link"]])
        self.assertEqual((seen, made, sleeps), ([1], [], 0))

    def test_stale_retry_does_not_lose_backlog(self):
        old, newest = post(2, "previous"), post(3, "newest")
        _, made, _, _ = self.run_poll(
            [[old], []], [[], [newest]],
            ["--expect-new", "--hint", newest["link"] + "?source=wp"])
        self.assertEqual(made, [2, 3])

    def test_missing_hint_has_bounded_wait_and_warning(self):
        old = post(2, "previous")
        n = poll.PUBLISH_RECHECKS + 1
        _, made, sleeps, errors = self.run_poll(
            [[old]] * n, [[]] * n,
            ["--expect-new", "--hint", "https://celtsarehere.com/missing/"])
        self.assertEqual(made, [2])
        self.assertEqual(sleeps, poll.PUBLISH_RECHECKS)
        self.assertIn("::warning::", errors)

    def test_post_without_card_is_not_marked_done(self):
        seen, made, _, _ = self.run_poll([[post(2, "no-image")]], [[]], [], [])
        self.assertEqual(made, [2])
        self.assertEqual(seen, [1])

    def test_ping_without_hint_retains_retry_behavior(self):
        _, made, sleeps, _ = self.run_poll(
            [[], [post(2, "new")]], [[], []], ["--expect-new"])
        self.assertEqual((made, sleeps), ([2], 1))

    def test_hint_gets_priority_when_clearing_backlog(self):
        expected, newer = post(2, "expected"), post(3, "newer")
        with patch.object(poll, "MAX_PER_RUN", 1):
            _, made, _, _ = self.run_poll(
                [[expected, newer]], [[expected]],
                ["--expect-new", "--hint", expected["link"]])
        self.assertEqual(made, [2])


class DirectLookupTest(unittest.TestCase):
    """The CDN ignores query strings on /wp-json, so ?slug= returns the cached
    latest list. Specific articles must come from unique paths instead."""

    def test_ping_with_id_needs_no_list_and_no_wait(self):
        newest = post(3, "newest")
        with (patch.object(poll, "fetch_post_by_id", return_value=newest) as by_id,
              patch.object(poll, "_article_html") as page):
            self.assertEqual(poll.fetch_hinted([newest["link"]], ["3"]), [newest])
        by_id.assert_called_once_with("3")
        page.assert_not_called()

    def test_url_without_id_reads_id_off_article_page(self):
        newest = post(3, "newest")
        html = '<link rel="alternate" type="application/json" ' \
               'href="https://celtsarehere.com/wp-json/wp/v2/posts/3" />'
        with (patch.object(poll, "_article_html", return_value=html),
              patch.object(poll, "fetch_post_by_id", return_value=newest) as by_id):
            self.assertEqual(poll.fetch_post_by_url(newest["link"]), newest)
        by_id.assert_called_once_with("3")

    def test_og_fallback_when_api_unavailable(self):
        html = ('<body class="postid-7"><meta property="og:title" '
                'content="Big News | Celts Are Here" /><meta property="og:image" '
                'content="https://celtsarehere.com/i.jpg" />')
        with (patch.object(poll, "_article_html", return_value=html),
              patch.object(poll, "fetch_post_by_id", return_value=None)):
            got = poll.fetch_post_by_url("https://celtsarehere.com/big-news/")
        self.assertEqual((got["id"], got["title"]["rendered"],
                          got["jetpack_featured_media_url"]),
                         (7, "Big News", "https://celtsarehere.com/i.jpg"))

    def test_wrong_or_unpublished_id_rejected(self):
        self.assertFalse(poll._usable(dict(post(4, "x")), 3))
        self.assertFalse(poll._usable(dict(post(3, "x"), status="draft"), 3))
        self.assertTrue(poll._usable(post(3, "x"), "3"))


if __name__ == "__main__":
    unittest.main()
