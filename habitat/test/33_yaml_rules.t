#!/usr/bin/env perl
# Rule pages (.v0/.v1/.e0/.e1) may be written as a YAML list instead of
# the line-oriented from/to form. Tests that:
#   - YAML is recognised only by its first line ("---" or "- ")
#   - from/to/opt, grep, head, tail run in order
#   - literal blocks ("to: |") keep indentation and blank lines, which
#     the core parser (CPAN::Meta::YAML) would otherwise lose
#   - bad YAML / bad regex fail with an inline error, and YAML tags never
#     build objects or run code
#   - ApplyRegExp mixes YAML and line-format ancestor pages in order

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
no warnings 'once';

sub yaml { return HabitatEngine::ApplyYamlRules( $_[0], $_[1] ); }
sub isy  { return HabitatEngine::IsYamlRules( $_[0] ); }

# ----------------------------------------------------------------
# Format detection
# ----------------------------------------------------------------
ok( isy("- from: a\n  to: b\n"),               "list item is YAML" );
ok( isy("---\n- from: a\n  to: b\n"),          "document marker is YAML" );
ok( isy("# rules\n\n- from: a\n  to: b\n"),    "leading comments and blank lines are skipped" );
ok( !isy("foo/bar\n"),                         "from/to line is not YAML" );
ok( !isy("GREP x\nHEAD 3\n"),                  "GREP/HEAD lines are not YAML" );
ok( !isy("-x-/y/\n"),                          "a rule starting with '-' but no space is not YAML" );
ok( !isy(""),                                  "empty is not YAML" );
ok( !isy(undef),                               "undef is not YAML" );

# ----------------------------------------------------------------
# Substitutions
# ----------------------------------------------------------------
is( yaml( "- from: foo\n  to: BAR\n", "foo and foo" ), "BAR and BAR", "global by default" );
is( yaml( "- from: foo\n  to: BAR\n  opt: ''\n", "foo and foo" ), "BAR and foo", "opt '' replaces once" );
is( yaml( "- from: 'HELLO'\n  to: hi\n  opt: gi\n", "hello Hello" ), "hi hi", "i flag" );
is( yaml( "- from: '(\\d+)x(\\d+)'\n  to: '\\1 by \$2'\n", "3x4" ),
    "3 by 4", "single quotes keep backslashes; \\1 and \$2 expand" );
is( yaml( "- from: a\n  to: b\n- from: b\n  to: c\n", "a" ), "c", "steps run in order" );
is( yaml( "- from: '.*'\n  to: whole\n", "x\ny" ), "whole", "from '.*' replaces the whole text" );
is( yaml( "- from: '^'\n  to: 'top '\n", "" ), "top ", "'^' on empty text (an .e0 template)" );
is( yaml( "# comment\n- from: a  # trailing comment\n  to: b\n", "a" ), "b", "comments" );

# ----------------------------------------------------------------
# grep / head / tail
# ----------------------------------------------------------------
my $lines = "one\ntwo\nthree\nfour";
is( yaml( "- grep: 'o'\n",  $lines ), "one\ntwo\nfour", "grep keeps matching lines" );
is( yaml( "- head: 2\n",    $lines ), "one\ntwo",       "head N" );
is( yaml( "- tail: 2\n",    $lines ), "three\nfour",    "tail N (no leading blank lines)" );
is( yaml( "- tail: 9\n",    $lines ), $lines,           "tail longer than text" );
is( yaml( "- grep: e\n- head: 1\n", $lines ), "one", "grep then head" );

is( yaml( "- prepend: 'top '\n- append: ' end'\n", "mid" ), "top mid end", "prepend and append" );
is( yaml( "- prepend: '\\1 \$1'\n", "x" ), '\1 $1x', "prepend text is not expanded" );
is( yaml( "- prepend: |\n    <pre>\n- append: |-\n\n    </pre>\n", "code" ),
    "<pre>\ncode\n</pre>", "prepend/append take blocks" );
is( yaml( "- prepend: x\n", "" ), "x", "prepend on empty text (an .e0 template)" );
is( HabitatEngine::EvalLocalRules( '[{"append":"!"}]', "hi", 0 ), "hi!", "JSON config rules accept append too" );

# ----------------------------------------------------------------
# Literal blocks
# ----------------------------------------------------------------
my $nested = <<'Y';
- from: '^(.*)$'
  to: |-
    <ul>
      <li>\1</li>
    </ul>
  opt: s
Y
is( yaml( $nested, "item" ), "<ul>\n  <li>item</li>\n</ul>", "deeper indentation inside a block is kept" );

my $blank = <<'Y';
- from: X
  to: |-
    para one

    para two
Y
is( yaml( $blank, "X" ), "para one\n\npara two", "blank lines inside a block are kept" );

is( yaml( "- from: X\n  to: |\n    a\n    b\n- from: Z\n  to: z\n", "X" ),
    "a\nb\n", "'|' keeps one final newline; the next entry still parses" );
is( yaml( "- from: X\n  to: |+\n    a\n\n\n- from: Z\n  to: z\n", "X" ),
    "a\n\n\n", "'|+' keeps all final newlines" );
is( yaml( "- from: X\n  to: |2-\n      code\n    text\n", "X" ),
    "  code\ntext", "'|2-' sets the indent, so the first line may be deeper" );
is( yaml( "- from: X\n  to: |-\n   one space\n", "X" ), "one space", "one space deeper is enough" );
is( yaml( "- to: |-\n    first\n  from: X\n", "X" ), "first", "block before from: in the same entry" );
is( yaml( "- from: 'x: \\|'\n  to: b\n", "x: |" ), "b", "'key: |' inside a quoted value is not a block" );

# ----------------------------------------------------------------
# Errors and safety
# ----------------------------------------------------------------
like( yaml( "- from: X\n  to: |-\n  same column\n", "X" ), qr/Local rule error/, "block text not indented deeper than to: is an error" );
like( yaml( "from: a\nto: b\n", "t" ),           qr/Local rule error/, "a mapping instead of a list is an error" );
like( yaml( "- from: '(unclosed'\n  to: x\n", "t" ), qr/^t<hr><b>Local rule error/, "bad regex: text kept, error appended" );
like( yaml( "- from: X\n  to: '<script>'\n- from: '(('\n  to: y\n", "X" ),
    qr/^<script><hr>/, "errors are appended after the text, which the renderer still scrubs" );
unlike( yaml( "- from: '(('\n  to: y\n", "t" ), qr/<script>/, "error text is quoted" );

our $ran = 0;
my $code = yaml( "- from: a\n  to: '\@{[ \$main::ran = 1 ]}'\n", "a" );
is( $main::ran, 0, "replacement text is never evaluated" );
is( $code, '@{[ $main::ran = 1 ]}', "  ... it is inserted literally" );
is( yaml( "- from: a\n  to: !!perl/code '{ \$main::ran = 1 }'\n", "a" ) =~ /Local rule error|^a$|perl\/code/ ? 1 : 0,
    1, "YAML tags do not build objects" );
is( $main::ran, 0, "  ... nor run code" );
is( yaml( "- from: '(?{ \$main::ran = 1 })a'\n  to: b\n", "a" ) =~ /Local rule error/ ? 1 : 0,
    1, "code blocks in the regex are refused" );
is( $main::ran, 0, "  ... and not run" );

# ----------------------------------------------------------------
# ApplyRegExp: ancestor rule pages in both formats
# ----------------------------------------------------------------
is( HabitatEngine::ApplyRegExp( 'A/B', 'abc', {}, [ "a/x\n", "- from: x\n  to: y\n", "b/z\n" ] ),
    'yzc', "line, YAML, line pages apply in order" );
is( HabitatEngine::ApplyRegExp( 'A/B', 'abc', {}, [ "a/x\n", "b/y\n" ] ),
    'xyc', "consecutive line-format pages still run as one list" );
is( HabitatEngine::ApplyRegExp( 'A/B', 'abc', { '^A/' => "- from: c\n  to: C\n" }, [] ),
    'abC', "namespace rule text may be YAML" );

done_testing();
