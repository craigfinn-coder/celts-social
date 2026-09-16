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

**A card didn't appear after publishing.**
First check the Actions tab for a *new-post* run at the time you published. If
there isn't one, the ping didn't arrive — check the WordPress snippet and the
token. If there is one and it says "No new articles", run the workflow by hand
with the article URL in *url*. (The site's CDN caches the article list for five
minutes; every request carries a cache-buster and pinged runs re-check for up
to six minutes for the specific article URL in the ping. An older unseen
article does not end that wait. If the article is still unavailable, the run
shows a warning rather than silently treating the older card as fulfilment.)

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

**The font.** Barlow Condensed ExtraBold was matched to your reference
graphics by measurement — within 3px on every line — not taken from your
original file. If you have the real one, drop the `.ttf` into `assets/fonts/`
and point `HEADLINE_FONT` in `src/brand.py` at it.

**The green flag and logo footer** were lifted straight out of your two
reference graphics, so those are pixel-exact.

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
