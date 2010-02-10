= Welcome to Habitat - a portable content management system =
{{atom/menu/HabitatMenu}}
<toc>
== # What is Habitat ==

Habitat is a very small, super fast, easy-to-install and highly customizable
content management system designed for personal or community use.
Habitat is written in perl, and can use sqlite database as the
backend. It even contains a build-in cgi webserver. Habitat
can be run from a local computer by an individual user, or installed
on a public website serving a group of users.

Habitat is a wiki engine too. Users can quickly build their 
own websites or information archive using this software by
creating, editing and managing wiki pages online. It provides
an efficient collaborative platform for an online community 
to develop software or resources.

Habitat was derived from [http://www.usemod.com/cgi-bin/wiki.pl UseModWiki] 
by [http://nmr.mgh.harvard.edu/~fangq/ Qianqian Fang], 
who had also founded the collaborative font development project - 
[http://wenq.org/en/ WenQuanYi]. Habitat is a result of 5 years 
continuous improvement of the WenQuanYi Wiki starting from the 
original UseModWiki. A lot of 
new features were added, such as the user management system,
database backend, hierarchical wiki page namespace, multi-language
support, object-oriented structure and interfaces for plugins.
See [http://wenq.org/habitat/index.cgi?WhatsNew What's New] for
a full list of the new features.

{(Habitat/Download)}

== # How to use Habitat ==

If you run Habitat for the first time, please click on the
"[http:?action=newlogin Register]" link on the left to create a username/password
for yourself. You can also apply the admin password you set
previously. Otherwise, you will be considered as an 
anonymous user and Habitat will only display your IP address.

If you want to make you the only person who can make changes, 
you have to login as an administrator (by setting the admin password
in the register page), and set <tt>EditAllowed</tt> to 0 in the <tt>config</tt>
file. If you want to run Habitat for personal use, this is 
highly recommended.

To create or modify pages, simply click on the "[http:?action=edit&id=Home Edit this page]" 
link on the top. Habitat supports many common Wiki markup
rules used by [http://www.usemod.com/cgi-bin/wiki.pl?TextFormattingRules UseModWiki] 
or [http://en.wikipedia.org/wiki/Help:Wiki_markup Wikipedia]. Please check out 
[Local:Habitat/Markup Markup Format] and [Local:Habitat/NewSyntax NewSyntax]
pages for more details about formatting.

A new feature of Habitat is the support of hierarchical pages.
You can create something like "[[Page/Subpage]]"
or "[[Page/Subpage/Subsubpage]]" to represent more complex
information or resources.

== # Where to get help ==

Please visit the [http://wenq.org/forum/viewforum.php?f=8 Habitat forum]
to get more information and help for using Habitat. We also actively
post new versions or patches at the [http://wenq.org/habitat/ Habitat 
website].

Habitat is an open-source project. You are welcome to contribute 
and become a developer. Please visit 
[http://wenq.org/habitat/ Habitat website] for more details.

== # A bigger picture ==

Habitat is a sub-project of the [http://huc.sf.net Human Understandable Computing]
(HUC) project. The overall goal of HUC is to promote open, safe,
collaborative and intuitive programming models. The focus of
the project is to develop software tools that are written 
in non-obscured scripting languages and driven by human understandable 
text, graphics and multimedia data (such as voice, video or gesture).
Habitat is a demonstration of the basic principles for HUC,
as it is written by high-level scripting language and 
manipulates human understandable text information.

We welcome anyone who embraces the notion of HUC to join
us. We believe that the more software following the principles of
HUC, the more open and safer our software ecosystem will be.
