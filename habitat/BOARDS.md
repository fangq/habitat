# Boards: blogs and discussion forums

A *board* is an ordinary wiki page that lists its subpages as posts.
Every post and every reply is its own wiki page, so each has its own
history, diff, permissions and edit link, and nothing is ever appended
into one ever-growing page.

## Creating a board

Put a directive on a line of its own in any page, and save it **as an
administrator** (a board only becomes active, or changes its settings,
when an admin saves the page; other users' edits of the page text are
fine but leave the settings as they were):

    Welcome to our forum.
    <board type=forum perpage=20 post=user reply=user>

    Lab news.
    <board type=blog perpage=10 post=editor reply=user>

| Setting   | Values                          | forum default | blog default |
|-----------|---------------------------------|---------------|--------------|
| `type`    | `forum`, `blog`                 |               |              |
| `perpage` | 1-200 (posts per page, replies per page) | 20   | 10           |
| `post`    | `anon`, `user`, `editor`, `admin` | `user`      | `editor`     |
| `reply`   | `anon`, `user`, `editor`, `admin` | `user`      | `user`       |

`anon` means anyone (with the CAPTCHA, if `$UseCaptcha`); `user` means
logged-in users; an unknown value counts as `admin`. Remove the line (as
an admin) to switch the board off; its pages stay as normal wiki pages.

## How it looks

* **Forum**: a table of topics, sticky topics first, then by last
  activity (newest reply), with starter, reply count and last poster.
  Topics are named `Forum/0001`, `Forum/0002`, ...
* **Blog**: newest posts first with a short excerpt and the comment
  count. Posts are named from the date and title, e.g.
  `Blog/2026-11-07-New-GPU-Cluster` (`-2`, `-3` on a clash; a title with
  no Latin letters falls back to `Blog/2026-11-07-p12`).
* **Thread** (a post's page): the post, then its replies in order,
  paginated, each with author, date, permalink (`#r0003`) and edit link.
  Replies are named `Forum/0001/0001`, `Forum/0001/0002`, ...
* `?action=browse&id=Forum&tag=help` lists the posts with that tag.

## Who can do what

| Action | Who |
|--------|-----|
| New post / reply | the board's `post` / `reply` level; replies to a closed thread only editors+ |
| Edit a post or reply | its creator (logged in), editors, admins |
| Sticky, close/reopen, delete a reply or a whole thread | editors, admins |
| Rebuild the board index | admins |

Pages under a board cannot be created by hand by ordinary users (only
through *New post* / *Reply*), and the normal read restrictions
(`%Permissions`, rule-stack clearance, `%EditPermissions`, page locks)
still apply: a restricted post shows as "(restricted)" in the list and
its title, text and replies stay hidden.

When a page becomes a board, the subpages it already has become its posts
(and their subpages replies): from then on they follow the board's edit
rules (creator, editors, admins).

Because only an administrator's save activates or changes a board, look
out for a `<board ...>` line that someone else added to a page before you
save it as an administrator.

## Post format

Posts keep their metadata in their own text, in a header the renderer
hides:

    <!-- post
    title: How do I install MCX?
    tags: help, mcx
    sticky: 1
    closed: 1
    -->
    The post body, in normal wiki markup (or <!-- markdown -->).

The *edit post* link gives a form with title/tags fields; the normal
*Edit this page* shows the raw text including the header. `sticky` and
`closed` only take effect when an editor or admin saves them.

## The index table

`pagemeta` (created automatically) holds one row per board, post and
reply: creator, title, tags, times, reply count, sticky/closed and the
board settings. It is derived data: if it ever gets out of step (e.g.
pages edited in the database directly, or restored from a backup), an
admin can press **Rebuild board index** on the board page
(`action=boardrebuild`), which re-reads the pages (the creator is taken
from each page's first revision).

## Limits (phase 1)

* A board inside a board is not supported (a directive on a post is
  ignored); posts are one level, replies one level below.
* Renaming a post does not move its replies, and renaming a board page
  switches the board off (save the new page as admin to switch it on).
  *Delete thread* deletes the replies too (all go to `deletedpage`).
* If a post fails half-way (server crash between naming and saving), its
  name can show in the list without a page; *Rebuild board index* clears it.
* On a board page, a `<board ...>` line is expanded even inside `<pre>`;
  wrap it in `<nowiki>` to show it literally.
* No per-board RSS feed yet; posts appear in RecentChanges like any edit.
* Existing `Page..discuss` pages are unchanged.
