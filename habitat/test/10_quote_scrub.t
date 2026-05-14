#!/usr/bin/env perl
# Output sanitization. Two layers:
#   1. QuoteHtml() — minimal entity-encoding for any text that flows
#      into HTML output (titles, etc.). Pre-existing helper.
#   2. ScrubRawHtml() — Stage 0 HTML::Scrubber wrapper, applied to
#      page-author-provided <html>...</html> blocks before they reach
#      the browser. The allow-list rejects <script>, <iframe>,
#      <object>, on* handlers, javascript: URLs.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();

# ----------------------------------------------------------------
# QuoteHtml
# ----------------------------------------------------------------
is( HabitatEngine::QuoteHtml("plain text"),  "plain text",      "passthrough plain" );
is( HabitatEngine::QuoteHtml("a < b"),       "a &lt; b",        "&lt; for <" );
is( HabitatEngine::QuoteHtml("a > b"),       "a &gt; b",        "&gt; for >" );
is( HabitatEngine::QuoteHtml("Tom & Jerry"), "Tom &amp; Jerry", "&amp; for &" );

# Named char-references kept intact (passthrough after escape)
is( HabitatEngine::QuoteHtml("&copy;"), "&copy;", "named entity preserved" );
is( HabitatEngine::QuoteHtml("&#65;"),  "&#65;",  "numeric entity preserved" );

# The classic XSS canary: full script tag goes to escaped form
is(
    HabitatEngine::QuoteHtml("<script>alert(1)</script>"),
    "&lt;script&gt;alert(1)&lt;/script&gt;",
    "script tag escaped"
);

# Quotes are NOT escaped (matches existing behavior — callers wrap
# attribute values in quotes only if they're safe by construction)
is( HabitatEngine::QuoteHtml(q{"hi" 'there'}), q{"hi" 'there'}, "quotes pass through" );

# Empty / undef
is( HabitatEngine::QuoteHtml(""), "", "empty input" );

# ----------------------------------------------------------------
# ScrubRawHtml — allowed structural / inline tags pass through
# ----------------------------------------------------------------
for my $tag (qw(b i u em strong p br hr h1 h2 ul ol li table tr td th span div pre code)) {
    my $in  = "<$tag>x</$tag>";
    my $out = HabitatEngine::ScrubRawHtml($in);
    like( $out, qr/<\Q$tag\E>/i, "allowed tag <$tag> survives" );
}

# Self-closing <br>, <hr>, <p>
like( HabitatEngine::ScrubRawHtml("<br>"), qr/<br/i, "<br> survives" );

# ----------------------------------------------------------------
# ScrubRawHtml — dangerous tags stripped
# ----------------------------------------------------------------
for my $payload (
    "<script>alert(1)</script>",
    "<script src=\"//evil.example/x.js\"></script>",
    "<iframe src=\"//evil.example\"></iframe>",
    "<object data=\"x.swf\"></object>",
    "<embed src=\"x.swf\">",
    "<style>body{display:none}</style>",
    "<link rel=\"stylesheet\" href=\"//evil/x.css\">",
    "<meta http-equiv=\"refresh\" content=\"0;url=//evil\">",
    "<base href=\"//evil/\">",
  )
{
    my $clean = HabitatEngine::ScrubRawHtml($payload);
    unlike( $clean, qr/<\s*script/i, "script removed from: $payload" )
      if $payload =~ /script/i;
    unlike( $clean, qr/<\s*iframe/i, "iframe removed from: $payload" )
      if $payload =~ /iframe/i;
    unlike( $clean, qr/<\s*object/i, "object removed from: $payload" )
      if $payload =~ /object/i;
    unlike( $clean, qr/<\s*embed/i, "embed removed from: $payload" )
      if $payload =~ /embed/i;
    unlike( $clean, qr/<\s*style/i, "style removed from: $payload" )
      if $payload =~ /style/i;
    unlike( $clean, qr/<\s*link/i, "link removed from: $payload" )
      if $payload =~ /<\s*link/i;
    unlike( $clean, qr/<\s*meta/i, "meta removed from: $payload" )
      if $payload =~ /<\s*meta/i;
    unlike( $clean, qr/<\s*base\s/i, "base removed from: $payload" )
      if $payload =~ /<\s*base\s/i;
}

# ----------------------------------------------------------------
# ScrubRawHtml — on* event handlers stripped
# ----------------------------------------------------------------
for my $payload (
    qq(<div onclick="alert(1)">x</div>),
    qq(<a href="/" onmouseover="alert(1)">x</a>),
    qq(<img src="/x.png" onerror="alert(1)">),
    qq(<p onload="alert(1)">x</p>),
  )
{
    my $clean = HabitatEngine::ScrubRawHtml($payload);
    unlike( $clean, qr/onclick/i, "onclick stripped: $payload" )
      if $payload =~ /onclick/;
    unlike( $clean, qr/onmouseover/i, "onmouseover stripped: $payload" )
      if $payload =~ /onmouseover/;
    unlike( $clean, qr/onerror/i, "onerror stripped: $payload" )
      if $payload =~ /onerror/;
    unlike( $clean, qr/onload/i, "onload stripped: $payload" )
      if $payload =~ /onload/;
}

# ----------------------------------------------------------------
# ScrubRawHtml — javascript:/data: URL rejection on <a href>
# ----------------------------------------------------------------
my $js_anchor = HabitatEngine::ScrubRawHtml(qq(<a href="javascript:alert(1)">x</a>));
unlike( $js_anchor, qr/javascript:/i, "javascript: scheme stripped from href" );

my $data_anchor =
  HabitatEngine::ScrubRawHtml(qq(<a href="data:text/html,<script>alert(1)</script>">x</a>));
unlike( $data_anchor, qr/data:text\/html/i, "data:text/html stripped from href" );

# But normal hrefs survive
like(
    HabitatEngine::ScrubRawHtml(qq(<a href="https://example.com/">x</a>)),
    qr|href="https://example.com/"|,
    "https href survives"
);
like( HabitatEngine::ScrubRawHtml(qq(<a href="/relative/page">x</a>)),
    qr|href="/relative/page"|, "site-relative href survives" );
like( HabitatEngine::ScrubRawHtml(qq(<a href="#anchor">x</a>)),
    qr|href="#anchor"|, "fragment href survives" );

# ----------------------------------------------------------------
# ScrubRawHtml — img src restrictions
# ----------------------------------------------------------------
unlike( HabitatEngine::ScrubRawHtml(qq(<img src="javascript:alert(1)">)),
    qr/javascript:/i, "javascript: src stripped from img" );

# data:image/png is in the allow-list; arbitrary data: URLs are not
like( HabitatEngine::ScrubRawHtml(qq(<img src="data:image/png;base64,AAAA">)),
    qr/data:image\/png;base64/i, "data:image/png src kept" );
unlike( HabitatEngine::ScrubRawHtml(qq(<img src="data:text/html,...">)),
    qr/data:text\/html/i, "data:text/html src stripped from img" );

like(
    HabitatEngine::ScrubRawHtml(qq(<img src="https://example.com/x.png">)),
    qr|src="https://example.com/x.png"|,
    "https img src kept"
);

# ----------------------------------------------------------------
# ScrubRawHtml — non-list attributes are dropped silently
# ----------------------------------------------------------------
my $with_style = HabitatEngine::ScrubRawHtml(qq(<div style="color:red">x</div>));
unlike( $with_style, qr/style=/i, "inline style attribute dropped" );
like( $with_style, qr/<div/i, "but the <div> tag itself survives" );

# ----------------------------------------------------------------
# Empty / undef input
# ----------------------------------------------------------------
is( HabitatEngine::ScrubRawHtml(""), "", "empty input -> empty output" );

done_testing;
