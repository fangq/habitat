#!/usr/bin/env perl
# Direct unit tests for Habitat::Render. Phase 1 extraction covers
# pure utilities — no %Pages, no link resolution. Exercise them
# without the WikiToHTML harness so a regression is pinpointed to
# the actual function rather than the rendering pipeline as a whole.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::fresh_test_db();

no warnings 'once';

# Required engine globals the renderer subs read. InitLinkPatterns
# (re)derives most of them; we set the inputs first.
$HabitatEngine::NewFS        = 0;
$HabitatEngine::NonEnglish   = 0;
$HabitatEngine::SimpleLinks  = 0;
$HabitatEngine::UseSubpage   = 1;
$HabitatEngine::FreeLinks    = 1;
$HabitatEngine::NamedAnchors = 0;
$HabitatEngine::NetworkFile  = 0;
$HabitatEngine::LimitFileUrl = 1;

HabitatEngine::InitLinkPatterns();

# ----------------------------------------------------------------
# InitLinkPatterns derives the pattern set the wiki syntax pipeline
# matches against.
# ----------------------------------------------------------------
isnt( $HabitatEngine::FS,              '', "InitLinkPatterns sets \$FS" );
isnt( $HabitatEngine::LinkPattern,     '', "InitLinkPatterns sets \$LinkPattern" );
isnt( $HabitatEngine::FreeLinkPattern, '', "InitLinkPatterns sets \$FreeLinkPattern" );
isnt( $HabitatEngine::UrlPattern,      '', "InitLinkPatterns sets \$UrlPattern" );
like( "HomePage", qr/^$HabitatEngine::LinkPattern$/, "CamelCase string matches \$LinkPattern" );
unlike( "lowercase", qr/^$HabitatEngine::LinkPattern$/, "all-lowercase rejected by \$LinkPattern" );

# ----------------------------------------------------------------
# StoreRaw / RestoreSavedText round-trip. The pipeline stashes raw
# strings in %$SaveUrl and gets back FS-bracketed sentinels; the
# restore pass expands them back.
# ----------------------------------------------------------------
my %save;
my $idx = 0;
local $HabitatEngine::SaveUrl      = \%save;
local $HabitatEngine::SaveUrlIndex = \$idx;

my $sentinel = HabitatEngine::StoreRaw('<b>hello</b>');
like(
    $sentinel,
    qr/\Q$HabitatEngine::FS\E\d+\Q$HabitatEngine::FS\E/,
    "StoreRaw returns FS<n>FS sentinel"
);
is( $save{0}, '<b>hello</b>', "StoreRaw stashed the html under index 0" );

my $restored = HabitatEngine::RestoreSavedText("before $sentinel after");
is( $restored, "before <b>hello</b> after", "RestoreSavedText round-trips a stored value" );

# StorePre wraps in tags and stores.
my $pre_sent = HabitatEngine::StorePre( "code body", "pre" );
is(
    HabitatEngine::RestoreSavedText($pre_sent),
    "<pre>code body</pre>",
    "StorePre wraps in <tag>...</tag> and stores"
);

# StoreHref wraps an anchor attribute set inside an <a>...</a>.
my $href = HabitatEngine::StoreHref( ' href="x"', 'click' );
is(
    HabitatEngine::RestoreSavedText($href),
    '<a href="x">click</a>',
    "StoreHref builds <a ...>text</a> and stores the attrs"
);

# ----------------------------------------------------------------
# GetBracketUrlIndex hands out monotonic 1-based ids per unique key.
# ----------------------------------------------------------------
my %save_num;
my $num_idx = 0;
local $HabitatEngine::SaveNumUrl      = \%save_num;
local $HabitatEngine::SaveNumUrlIndex = \$num_idx;

is( HabitatEngine::GetBracketUrlIndex("first"),  1, "first lookup -> id 1" );
is( HabitatEngine::GetBracketUrlIndex("second"), 2, "second unique lookup -> id 2" );
is( HabitatEngine::GetBracketUrlIndex("first"),  1, "repeat first -> still id 1" );

# ----------------------------------------------------------------
# QuoteHtml escapes the three significant chars but preserves
# entity-style references.
# ----------------------------------------------------------------
is( HabitatEngine::QuoteHtml('<b>&"</b>'),
    '&lt;b&gt;&amp;"&lt;/b&gt;',
    "QuoteHtml: < > & escaped, double-quote left alone (legacy behavior)" );
is(
    HabitatEngine::QuoteHtml('hello &amp; goodbye'),
    'hello &amp; goodbye',
    "QuoteHtml: existing entities preserved as-is"
);
is( HabitatEngine::QuoteHtml('&#x2014;'),
    '&#x2014;', "QuoteHtml: numeric character references preserved" );

# ----------------------------------------------------------------
# ScrubRawHtml strips dangerous markup. The full security matrix
# is in 14_admin_html.t; the cases here pin the scrubber's direct
# behavior so a regression in the rule list is caught at this layer.
# ----------------------------------------------------------------
unlike( HabitatEngine::ScrubRawHtml('<script>alert(1)</script>'),
    qr/script/i, "ScrubRawHtml strips <script>" );
unlike( HabitatEngine::ScrubRawHtml('<a href="javascript:x()">x</a>'),
    qr/javascript:/i, "ScrubRawHtml strips javascript: URLs in href" );
unlike( HabitatEngine::ScrubRawHtml('<img src="javascript:x()">'),
    qr/javascript:/i, "ScrubRawHtml strips javascript: URLs in img src" );
like( HabitatEngine::ScrubRawHtml('<b>bold</b>'),
    qr|<b>bold</b>|, "ScrubRawHtml preserves safe inline tags" );
like(
    HabitatEngine::ScrubRawHtml('<a href="https://example.com">x</a>'),
    qr|<a href="https://example\.com">x</a>|,
    "ScrubRawHtml preserves https: anchors"
);

# ----------------------------------------------------------------
# ApplyRegExpRules: line-oriented `from/to/opt` rewrite syntax.
# Each line is `pattern/replacement/flags`.
# ----------------------------------------------------------------
# `foo/bar` form: replace pattern=foo with text=bar. The parser is
# greedy on slashes, so a literal trailing /g is itself absorbed into
# the `to` capture (a known quirk); the default global flag fires
# regardless when opt is empty.
is( HabitatEngine::ApplyRegExpRules( "foo/bar\n", "foo and foo", 0 ),
    "bar and bar", "ApplyRegExpRules: foo/bar -> default global replace" );
is( HabitatEngine::ApplyRegExpRules( "GREP needle\n", "hay\nneedle\nstraw\n", 0 ),
    "needle", "ApplyRegExpRules: GREP keeps only matching lines" );
is( HabitatEngine::ApplyRegExpRules( "HEAD 2\n", "a\nb\nc\nd\n", 0 ),
    "a\nb", "ApplyRegExpRules: HEAD keeps first N lines" );

# ----------------------------------------------------------------
# EvalLocalRules: JSON-array variant; never evals user-supplied
# Perl, reports errors inline.
# ----------------------------------------------------------------
my $rules = '[{"from":"hello","to":"goodbye"},{"from":"WORLD","to":"earth","opt":"gi"}]';
is(
    HabitatEngine::EvalLocalRules( $rules, "hello WORLD", 0 ),
    "goodbye earth",
    "EvalLocalRules: sequential JSON rules; case-insensitive flag honored"
);

my $bad_json = '{not valid';
my $out      = HabitatEngine::EvalLocalRules( $bad_json, "any text", 0 );
like( $out, qr/Local rule error/, "EvalLocalRules: malformed JSON -> inline error, no die" );
like( $out, qr/^any text/,        "EvalLocalRules: original text returned with error appended" );

my $bad_regex = '[{"from":"(unclosed","to":"x"}]';
$out = HabitatEngine::EvalLocalRules( $bad_regex, "any text", 0 );
like( $out, qr/Local rule error/, "EvalLocalRules: bad regex -> inline error, no die" );

is( HabitatEngine::EvalLocalRules( "", "untouched", 0 ),
    "untouched", "EvalLocalRules: empty rules -> input passes through" );

# ----------------------------------------------------------------
# RemoveFS clears any leftover sentinels (last-resort cleanup if a
# StoreRaw/RestoreSavedText round trip didn't pair).
# ----------------------------------------------------------------
my $with_fs = "before " . $HabitatEngine::FS . "5 after";
is( HabitatEngine::RemoveFS($with_fs),
    "before 5 after", "RemoveFS strips lone FS-digit sequences" );

done_testing;
