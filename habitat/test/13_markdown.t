#!/usr/bin/env perl
# Stage 6: per-page Markdown rendering via Text::Markdown::Discount.
# A page whose first line is `<!-- markdown -->` is rendered as
# Markdown, skipping the wiki rule pipeline. Output passes through
# ScrubRawHtml so Markdown's raw-HTML passthrough can't inject scripts.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

BEGIN {
    eval { require Text::Markdown::Discount; 1 }
      or plan skip_all => "Text::Markdown::Discount not installed";
}

HabitatHarness::load_wiki();
HabitatHarness::fresh_test_db();
HabitatEngine::InitLinkPatterns();

# Fake $q stub; required by some code paths reached from WikiToHTML.
{
    package FakeCGI13;
    sub new { bless {}, shift }
    sub param { return }
}
no warnings 'once';
$HabitatEngine::q = FakeCGI13->new;
$HabitatEngine::OpenPageName = 'MdPage';

# Stage out a tiny page record so WikiToHTML doesn't trip over missing
# permission rules / section data.
$HabitatEngine::Pages{'MdPage'} = {
    page    => { name => 'MdPage', version => 3, tscreate => 0, ts => 0 },
    section => { name => 'text_default', revision => 1 },
    text    => { text => '', minor => 0, newauthor => 0, summary => '' },
    rules   => 1,   # short-circuit BuildRuleStack
};

# ----------------------------------------------------------------
# Page without the marker: wiki pipeline (unchanged).
# ----------------------------------------------------------------
my $wiki_in  = "== Wiki Heading ==\n\nplain paragraph\n";
my $wiki_out = HabitatEngine::WikiToHTML( 'MdPage', $wiki_in );
unlike( $wiki_out, qr|<h1>Wiki Heading</h1>|i,
    "without marker: not rendered as Markdown" );

# ----------------------------------------------------------------
# Page with the marker: Markdown pipeline.
# ----------------------------------------------------------------
my $md_in = <<'MD';
<!-- markdown -->
# Hello

This is **bold** and this is *italic*.

- item 1
- item 2

```
verbatim
```
MD

my $md_out = HabitatEngine::WikiToHTML( 'MdPage', $md_in );

like( $md_out, qr|<h1[^>]*>Hello</h1>|i,        "# Hello -> <h1>" );
like( $md_out, qr|<strong>bold</strong>|,        "**bold** -> <strong>" );
like( $md_out, qr|<em>italic</em>|,              "*italic* -> <em>" );
like( $md_out, qr|<ul>.*<li>item 1</li>|is,      "bulleted list rendered" );
like( $md_out, qr|<code>|i,                       "code block rendered" );

# ----------------------------------------------------------------
# Marker tolerates whitespace variations and case.
# ----------------------------------------------------------------
for my $marker (
    "<!-- markdown -->\n",
    "<!--markdown-->\n",
    "<!-- Markdown -->\n",
    "  <!-- markdown -->  \n",
) {
    my $out = HabitatEngine::WikiToHTML( 'MdPage', $marker . "# H\n" );
    like( $out, qr|<h1[^>]*>H</h1>|i,
        sprintf("marker variant %s recognized", $marker =~ s/\n.*//rs ) );
}

# ----------------------------------------------------------------
# Security: the scrub pass strips dangerous tags even if they survive
# the Markdown pass via raw-HTML inlines.
# ----------------------------------------------------------------
my $xss_in = <<'MD';
<!-- markdown -->
# Heading

<script>alert(1)</script>

[link](javascript:alert(1))
MD

my $xss_out = HabitatEngine::WikiToHTML( 'MdPage', $xss_in );
unlike( $xss_out, qr|<script|i,        "<script> tag stripped from Markdown output" );
unlike( $xss_out, qr|javascript:|i,     "javascript: URLs stripped from Markdown links" );
like(   $xss_out, qr|<h1[^>]*>Heading</h1>|i, "safe markup survives the scrub" );

done_testing;
