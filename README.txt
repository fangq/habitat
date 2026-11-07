= Welcome to Habitat =
<toc>

Habitat is a small, fast wiki engine written in Perl. Put it on any web
server that runs Perl and you have a website that you and your
collaborators can edit from a browser, with every change kept in the
page history.

'''This is a built-in page.''' A new Habitat wiki shows it until someone
edits it. To replace it with your own front page, log in and click
''Edit this page''.

== # What Habitat can do ==

* '''Wiki editing.''' Simple text markup ([[Habitat/Markup]]), a full revision history with diffs for every page, [http:?RecentChanges Recent changes], an RSS feed, and full-text search.
* '''Pages in a tree.''' Names like <tt>Project/Notes/2026</tt> make subpages. A <tt><nowiki><localtree></nowiki></tt> tag lists the pages under the current one.
* '''Write once, reuse anywhere.''' <tt><nowiki>{{Page}}</nowiki></tt> embeds another page, rendered. <tt><nowiki>{(Page)}</nowiki></tt> embeds its raw text.
* '''Page rules.''' A page can carry text-rewriting rules that also apply to all of its subpages, so a section of the wiki can be turned into a bug tracker, a glossary or a slide deck. See [[Habitat/NewSyntax]].
* '''Markdown.''' A page that starts with <tt><nowiki><!-- markdown --></nowiki></tt> is written in Markdown.
* '''Blogs and forums.''' A <tt><nowiki><board></nowiki></tt> line turns a page into a blog or a discussion forum. Every post and every reply is its own page, with paging, tags, sticky and closed topics, and moderation.
* '''Accounts and permissions.''' Registration can be open, or limited to people who have an editor or administrator token. Users can reset a lost password by email. Pages can be restricted for reading, for editing, or locked.
* '''Safe by default.''' Passwords are hashed with bcrypt. Every form is CSRF-protected. Logins are throttled. Raw HTML from users is scrubbed; only pages last saved by an administrator may carry scripts.
* '''Runs almost anywhere.''' Plain CGI on shared hosting, PSGI (Starman, plackup), mod_perl or FastCGI. Data goes in SQLite (the default), MariaDB/MySQL or PostgreSQL. A static page cache lets Apache serve anonymous visitors without starting Perl.
* '''English and Chinese''' user interface ([http:?action=browse&id=Home&lang=cn 中文]).

== # Getting started ==

# '''Create an account.''' Use [http:?action=newlogin Register] at the top of the page. If this wiki only takes registrations from invited people, you need the editor or administrator token from the site owner. Typing the administrator token as well makes your account an administrator.
# '''Edit a page.''' Click ''Edit this page'', change the text, and save. Nothing is lost: ''View other revisions'' shows every earlier version.
# '''Make a new page.''' Write a link such as <tt><nowiki>[[My New Page]]</nowiki></tt> on any page, save, and follow the link to start writing the new page.
# '''Learn the markup''' from [[Habitat/Markup]], and the advanced features from [[Habitat/NewSyntax]].
# '''Run your own wiki''' by following [[Habitat/Install]].

== # Built-in pages ==

!! Page !! What it is !!
|| [[Habitat/Install]] || Download, install and configure Habitat ||
|| [[Habitat/Markup]] || The text markup, with examples ||
|| [[Habitat/NewSyntax]] || Embedding, page rules, Markdown, boards ||
|| [http:?action=index All pages] || Every page in this wiki ||
|| [http:?RecentChanges Recent changes] || What changed lately ||

Like this page, the built-in pages are only defaults: save a page with the
same name to replace one.

== # Source code and help ==

* Source code, releases and the issue tracker: https://github.com/fangq/habitat
* Project page: https://wenq.org/habitat/
* License: GNU General Public License, version 2 or later.

Habitat started in 2006 as the wiki of the
[https://wenq.org/en/ WenQuanYi] open-source font project, built by
[https://github.com/fangq Qianqian Fang] on top of
[https://www.usemod.com/cgi-bin/wiki.pl UseModWiki]. In 2026 it was
reworked for security, speed and modern servers.
