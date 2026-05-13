#!/usr/bin/env perl
# ValidId is the page-name gatekeeper that runs before any handler
# touches a page. FreeToNormal canonicalizes a free-link title (with
# spaces) to its on-disk form.
#
# These pieces aren't Stage 0+ additions, but they sit on the critical
# security path: a broken ValidId would undo the Stage 0 SQL
# parameterization for any caller that still concatenates IDs into
# raw SQL.
#
# Behavior depends on three config flags ($FreeLinks / $UpperFirst /
# $FreeUpper). The test explicitly sets them so it's reproducible
# regardless of whether the test harness has loaded a config file.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();

# Pin config to a known mode for these tests (matches the in-script
# defaults: free links on, both case-folds on). InitLinkPatterns must
# run AFTER setting these so the pattern globals see the current state.
no warnings 'once';
local $HabitatEngine::FreeLinks  = 1;
local $HabitatEngine::UseSubpage = 1;
local $HabitatEngine::UpperFirst = 1;
local $HabitatEngine::FreeUpper  = 1;
HabitatEngine::InitLinkPatterns();

# ----------------------------------------------------------------
# ValidId — accepted shapes
# ----------------------------------------------------------------
is( HabitatEngine::ValidId("Home"),             "", "simple page name accepted" );
is( HabitatEngine::ValidId("RecentChanges"),    "", "CamelCase accepted" );
is( HabitatEngine::ValidId("Wiki_Page"),        "", "underscore accepted" );
is( HabitatEngine::ValidId("Parent/Child"),     "", "subpage accepted" );
is( HabitatEngine::ValidId("Parent/Child/Grand"), "", "deep subpage accepted" );
is( HabitatEngine::ValidId("Page-1.2(beta)"),   "", "punctuation in free-link allowed" );

# ----------------------------------------------------------------
# ValidId — rejected shapes
# ----------------------------------------------------------------
isnt( HabitatEngine::ValidId(""),            "", "empty name rejected" );
isnt( HabitatEngine::ValidId("/leading"),    "", "leading slash rejected" );
isnt( HabitatEngine::ValidId("trailing/"),   "", "trailing slash rejected" );
isnt( HabitatEngine::ValidId("Has Space"),   "", "space rejected" );
isnt( HabitatEngine::ValidId("Has!Bang"),    "", "exclamation rejected (not in free-link charset)" );
isnt( HabitatEngine::ValidId("Has?Q"),       "", "question mark rejected" );
isnt( HabitatEngine::ValidId("Has\@At"),     "", "at sign rejected" );
isnt( HabitatEngine::ValidId("page.db"),     "", "*.db reserved (DB filename)" );
isnt( HabitatEngine::ValidId("page.lck"),    "", "*.lck reserved (lock filename)" );

# Length cap (>120 chars)
my $too_long = "A" x 130;
isnt( HabitatEngine::ValidId($too_long), "", "name >120 chars rejected" );

# ----------------------------------------------------------------
# SQL-injection-shaped names — the line of defense behind ValidId
# ----------------------------------------------------------------
my @injections = (
    "Home' OR 1=1--",
    "Home; DROP TABLE page",
    "Home\" --",
    "Home`",
    "Home\nUNION SELECT",
);
for my $inj (@injections) {
    isnt( HabitatEngine::ValidId($inj), "",
        "SQLi-shaped name rejected by ValidId: " . substr( $inj, 0, 20 ) );
}

# Path-traversal-shaped names. NOTE: `.` and `/` are both in the
# free-link character set ($AnyLetter), so ValidId by itself accepts
# "../etc/passwd". This is NOT exploitable because:
#   - page names are stored in DB rows, not used as filesystem paths,
#   - the page-on-disk lookup goes through Habitat::Store with bound
#     parameters,
#   - and (?:^/|/$|//) leading/trailing/double slashes are still rejected.
# These tests document the actual surface, not the lay assumption.
is(   HabitatEngine::ValidId("../etc/passwd"),     "",
    "ValidId accepts '../etc/passwd' as a literal page name (no filesystem semantics)" );
is(   HabitatEngine::ValidId("Home/../Other"),     "",
    "ValidId accepts '..' as a subpage segment" );
isnt( HabitatEngine::ValidId("..\\windows\\system32"), "",
    "Windows-style backslash path rejected (\\ not in charset)" );

# ----------------------------------------------------------------
# FreeToNormal — canonicalization with FreeUpper / UpperFirst on
# ----------------------------------------------------------------
# Empty input
is( HabitatEngine::FreeToNormal(""), "", "empty string" );

# Spaces -> underscores; first letter capitalized; FreeUpper caps
# letters after each delimiter [-_.,()/]
is( HabitatEngine::FreeToNormal("hello world"),  "Hello_World",
    "spaces collapsed, first letter and post-underscore caps" );
is( HabitatEngine::FreeToNormal("Hello_World"),  "Hello_World", "already normalized" );
is( HabitatEngine::FreeToNormal("Parent / Child"), "Parent/Child",
    "subpage separator preserved, surrounding spaces dropped" );
is( HabitatEngine::FreeToNormal("Mixed_Case Stuff"), "Mixed_Case_Stuff",
    "mixed case preserved, trailing word capped" );

# Underscore-vs-slash collapsing (subpage on)
is( HabitatEngine::FreeToNormal("a_/b"),   "A/B",  "_/ collapses to /, post-/ cap" );
is( HabitatEngine::FreeToNormal("a/_b"),   "A/B",  "/_ collapses to /, post-/ cap" );
is( HabitatEngine::FreeToNormal("a__b"),   "A_B",  "runs of underscores collapsed; post-_ cap" );

# Leading/trailing underscores stripped. ucfirst runs BEFORE the
# strip, on the bare "_" which is unchanged — so the stripped result
# stays lowercase. (Documenting the surprising-but-stable behavior;
# this matters because internal links rely on it being deterministic.)
is( HabitatEngine::FreeToNormal("__foo__"), "foo",
    "leading underscores stripped; first letter NOT recapped after strip" );
is( HabitatEngine::FreeToNormal("foo__"),   "Foo",
    "trailing-only underscores stripped; ucfirst applied first" );

# Post-punctuation capitalization for various delimiters
is( HabitatEngine::FreeToNormal("foo-bar"),  "Foo-Bar", "hyphen triggers post-cap" );
is( HabitatEngine::FreeToNormal("foo.bar"),  "Foo.Bar", "dot triggers post-cap" );
is( HabitatEngine::FreeToNormal("foo,bar"),  "Foo,Bar", "comma triggers post-cap" );
is( HabitatEngine::FreeToNormal("foo(bar)"), "Foo(Bar)","paren triggers post-cap" );

# ----------------------------------------------------------------
# Property: every FreeToNormal output that contains only the allowed
# character set should pass ValidId
# ----------------------------------------------------------------
for my $input (
    "Some Topic",
    "alpha/beta",
    "Hello, World",      # no exclamation (rejected charset)
    "Page (with parens)",
    "Mixed_Case Stuff",
    "a/b/c/d",
) {
    my $norm = HabitatEngine::FreeToNormal($input);
    is( HabitatEngine::ValidId($norm), "",
        "FreeToNormal('$input') = '$norm' passes ValidId" );
}

# ----------------------------------------------------------------
# Same checks under your production config ($UpperFirst=0,
# $FreeUpper=0): case folding is suppressed but everything else still
# works. This block reproduces what the deployed wiki actually sees.
# ----------------------------------------------------------------
{
    local $HabitatEngine::UpperFirst = 0;
    local $HabitatEngine::FreeUpper  = 0;
    HabitatEngine::InitLinkPatterns();

    is( HabitatEngine::FreeToNormal("hello world"),     "hello_world",
        "no case fold: spaces only" );
    is( HabitatEngine::FreeToNormal("Mixed_Case Stuff"), "Mixed_Case_Stuff",
        "existing case preserved" );
    is( HabitatEngine::ValidId("hello_world"), "", "lowercase IDs still valid" );
    isnt( HabitatEngine::ValidId("Home' OR 1=1--"), "",
        "SQLi shape still rejected with case folding off" );
}

# Restore for any remaining tests
HabitatEngine::InitLinkPatterns();

done_testing;
