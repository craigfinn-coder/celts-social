# CeltsAreHere social card generator

Every time a new article goes live on celtsarehere.com, this makes the Facebook
graphic for it — featured image, headline, house template — and puts it on a
web page your writers can grab it from. WordPress pings it the moment a post is
published, so the card is usually on the page within a minute. Nothing runs on
your Mac.

Two sizes per article: **1080×1380** for the feed and **1080×1920** for stories.

---

## Setting it up

You need a free GitHub account. Nothing else — no credit card, no software to
install, no command line.

**1. Make the repository.**
On github.com click **+** (top right) → **New repository**. Name it
`celts-social`. Choose **Public** (this matters — it's what makes the Actions
minutes free). Click **Create repository**.

**2. Put these files in it.**
On the empty repo page click **uploading an existing file**. Drag the whole
unzipped folder onto the page, wait for the file list to fill, then click
**Commit changes**.

**3. Turn on the web page.**
**Settings** → **Pages** (left sidebar) → under *Branch* pick **gh-pages**,
then **Save**. If `gh-pages` isn't in the list yet, that's expected — it appears
after step 4, so come back and do this then.

**4. Give it permission to save its own work.**
**Settings** → **Actions** → **General** → scroll to *Workflow permissions* →
select **Read and write permissions** → **Save**.

**5. Start it.**
**Actions** tab → **Poll CeltsAreHere** (left) → **Run workflow** → tick
**bootstrap** → **Run workflow**.

That first run marks everything currently on the site as "already done", so you
don't get fifteen cards at once. From then on it only picks up genuinely new
articles.

**6. Tell WordPress to ping it.**
There is deliberately no timer: polling the site every 15 minutes got GitHub's
runners blocked by the site's bot protection. Instead WordPress sends a
`repository_dispatch` event (type `new-post`) to this repo whenever a post is
published, and that starts a run. On the WordPress side that is a small snippet
on the `publish_post` hook that POSTs to
`https://api.github.com/repos/YOURNAME/celts-social/dispatches` with a
fine-grained token that has *Contents: read and write* on this repo.

Include the article's URL in the ping as `client_payload.url` (or `link` /
`permalink` / `post_url` / `post_permalink`). It isn't required, but with it the
run fetches that exact article straight away instead of waiting for it to show
up in the site's list.

Your writers' page is at:

```
https://YOURNAME.github.io/celts-social/
```

Bookmark it. Newest cards at the top, Download button under each one.

---

## Things you'll actually want to do

**The headline isn't right for social.**
Actions → Poll CeltsAreHere → Run workflow. Paste the article URL into *url*
and your better headline into *headline*. Run it. A new card appears on the
page in a minute or two.

**Check it's still running.**
The Actions tab lists every run. Green tick means fine. It's also stamped at the
top of your writers' page. A run labelled *new-post* was started by a WordPress
ping; its log has a "Ping payload" line showing exactly what WordPress sent.

**A card or Facebook post didn't go through (writers).**
In WordPress go to **Posts**, hover over the article and click
**Resend social card**. A green notice confirms the request reached GitHub.
The card is remade on the writers' page within a couple of minutes and, if
that article never made it to Facebook, it goes to Buffer. It will not post
an article to Facebook twice (`state/buffered.json` keeps track), so the link
is safe to press if you're not sure. It's also in the admin bar when you view
a published article on the site.

**How you'll know something failed.** A run turns red (and GitHub emails you)
if the card couldn't be made or Buffer refused the post after three tries. The
red run's summary says which article; the fix is the Resend link above.

**What made runs fail at random (fixed 20 Sept 2026).** The CDN caches
`/wp-json/wp/v2/posts` by path only, so the "latest posts" list is sometimes a
cached copy of some other request to that address (a different page, filter
or `_fields=` list). When that copy had no post IDs the run crashed with
`KeyError: 'id'` before making the pinged article's card; it only went out
when the next article was published. Unusable entries are now skipped, the
list only counts articles from the last 12 hours, the pinged article is always
fetched directly, and each ping also names WordPress's last few published
posts so one whose own ping got dropped is picked up by the next.

**A card didn't appear after publishing.**
First check the Actions tab for a *new-post* run at the time you published. If
there isn't one, the ping didn't arrive — check the WordPress snippet and the
token. If there is one and it says "No new articles", run the workflow by hand
with the article URL in *url*.

**Why it used to take six minutes (fixed 18 Sept 2026).** The site's CDN
(BunnyCDN) caches everything under `/wp-json` by path and ignores the query
string, so the latest-posts list is up to five minutes stale and cache-busters
do nothing. Pinged runs now fetch the article directly from its own unique
address (`/wp-json/wp/v2/posts/<id>`, using the `id` WordPress sends in the
ping, or the ID read off the article page), so the card is made seconds after
publishing. The stale list is only a backstop for missed pings.

**Heads are getting cut off in the crop.**
Open `src/brand.py` on GitHub, click the pencil, change `FOCAL_Y = 0.36` to
something lower like `0.28`, commit. Lower keeps more of the top of the photo.

**Stop it for a while.**
Actions tab → Poll CeltsAreHere → the `...` menu → Disable workflow.

---

## Where things are

| File | What it is |
|---|---|
| `src/brand.py` | Every colour, size and position. The look lives here. |
| `src/render.py` | Draws the card. |
| `src/poll.py` | Checks the site, decides what's new. |
| `src/gallery.py` | Builds the writers' page. |
| `state/seen.json` | Which articles are already done. Don't edit. |
| `.github/workflows/poll.yml` | The job that runs when WordPress pings, or when you press Run workflow. |

---

## Notes worth knowing

**The page is public.** Anyone with the link can see it, though it's not
indexed by search engines and nobody will guess the URL. The graphics are
going on Facebook anyway. If that's not acceptable, the repo can be made
private and the cards delivered to Google Drive instead — see below.

**Timing.** A ping starts a run within seconds, but GitHub queues jobs, so a
card can take a few minutes when their servers are busy. Runs never overlap: if
two posts go out together, the second waits for the first.

**The look ("news card", Sept 2026).** White NEWS label and the white
CELTS ARE HERE logo across the top, a green CELTIC NEWS subheading, the
headline left-aligned in Anton over a deep-green fade, and a green band with
"Full story in the first comment". Stories show the same card, without the
CTA wording, as a rounded panel over a blurred copy of the photo; the space
under the panel is for Instagram's link sticker. Label and CTA type is Archivo Bold. The label,
subheading and CTA wording are `LABEL_TEXT`, `SUB_TEXT` and the feed `cta` line in
`src/brand.py`; long headlines shrink automatically down to `MIN_HEADLINE_SIZE`.
The logo is the same white PNG the Graphics Builder uses.

**Old cards are removed** from the page after the newest 240, so it stays
fast. Every run is also kept as a downloadable backup under the Actions tab
for 30 days.

---

## Optional: deliver to Google Drive or Dropbox instead

Only worth doing if the writers would rather have the files sync to a folder.
Install [rclone](https://rclone.org), run `rclone config` to connect your
account, then add two repository secrets under **Settings → Secrets and
variables → Actions**:

| Secret | Value |
|---|---|
| `RCLONE_CONF` | the whole contents of `~/.config/rclone/rclone.conf` |
| `RCLONE_REMOTE` | e.g. `gdrive:CeltsAreHere/Social Cards` |

The gallery page keeps working either way.

---

## Running it yourself

```bash
pip install -r requirements.txt
python src/poll.py --url https://celtsarehere.com/some-article/ --no-upload
python tests/test_offline.py    # smoke test, no network needed
```
