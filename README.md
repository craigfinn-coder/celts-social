# CeltsAreHere social card generator

Every time a new article goes live on celtsarehere.com, this makes the Facebook
graphic for it — featured image, headline, house template — and puts it on a
web page your writers can grab it from. It checks every 15 minutes, on its own,
forever. Nothing runs on your Mac.

Two sizes per article: **1080×1380** for the feed and **1080×1920** for stories.

---

## Setting it up

You need a free GitHub account. Nothing else — no credit card, no software to
install, no command line.

**1. Make the repository.**
On github.com click **+** (top right) → **New repository**. Name it
`celts-social`. Choose **Public** (this matters — it's what makes the schedule
free). Click **Create repository**.

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
don't get fifteen cards at once. From then on it runs itself every 15 minutes
and only picks up genuinely new articles.

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
top of your writers' page.

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
| `.github/workflows/poll.yml` | The 15-minute schedule. |

---

## Notes worth knowing

**The page is public.** Anyone with the link can see it, though it's not
indexed by search engines and nobody will guess the URL. The graphics are
going on Facebook anyway. If that's not acceptable, the repo can be made
private and the cards delivered to Google Drive instead — see below.

**Timing is a floor, not a promise.** GitHub queues scheduled jobs, so a run
can land a few minutes late when their servers are busy.

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
