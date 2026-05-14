#!/usr/bin/env perl
# Stage 0 replaced the legacy eval(STRING) $LateRules / $EarlyRules
# Perl hook with a JSON regex pipeline. Tests that:
#   - the pipeline runs each rule in order
#   - it never evals user-supplied Perl
#   - bad JSON / bad regex / unknown flags fail safely with an inline
#     error rather than crashing the request

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();

sub eval_rules { return HabitatEngine::EvalLocalRules( $_[0], $_[1], 0 ); }

# ----------------------------------------------------------------
# Empty / undef rules: no-op
# ----------------------------------------------------------------
is( eval_rules( "",    "untouched" ), "untouched", "empty rules pass text through" );
is( eval_rules( undef, "untouched" ), "untouched", "undef rules pass text through" );

# ----------------------------------------------------------------
# Single substitution
# ----------------------------------------------------------------
is(
    eval_rules( '[{"from":"foo","to":"BAR","opt":"g"}]', "foo and foo and food" ),
    "BAR and BAR and BARd",
    "global substitution applied"
);

# Default opt is 'g'
is( eval_rules( '[{"from":"foo","to":"BAR"}]', "foo and foo" ),
    "BAR and BAR", "default behavior is global" );

# ----------------------------------------------------------------
# Backreferences in replacement
# ----------------------------------------------------------------
is(
    eval_rules( '[{"from":"(\\\\d+)x(\\\\d+)","to":"$1 by $2"}]', "100x200 and 30x40" ),
    "100 by 200 and 30 by 40",
    "dollar-style backrefs in replacement work"
);

is( eval_rules( '[{"from":"(\\\\d+)x(\\\\d+)","to":"\\\\1 by \\\\2"}]', "100x200" ),
    "100 by 200", "backslash-style backrefs in replacement work" );

# ----------------------------------------------------------------
# Flags
# ----------------------------------------------------------------
is( eval_rules( '[{"from":"hello","to":"hi","opt":"gi"}]', "Hello HELLO hello" ),
    "hi hi hi", "case-insensitive flag" );

# Non-global single replacement
is( eval_rules( '[{"from":"foo","to":"BAR","opt":""}]', "foo foo foo" ),
    "BAR foo foo", "empty opt replaces only first occurrence" );

# Unknown flag chars are stripped silently
is( eval_rules( '[{"from":"foo","to":"BAR","opt":"gx!@#"}]', "foo foo" ),
    "BAR BAR", "unknown flag chars stripped, valid flags still applied" );

# ----------------------------------------------------------------
# Rule ordering: rules apply sequentially
# ----------------------------------------------------------------
is( eval_rules( '[{"from":"a","to":"b","opt":"g"},{"from":"b","to":"c","opt":"g"}]', "a" ),
    "c", "rules apply in order; output of one feeds the next" );

# ----------------------------------------------------------------
# Failure modes — never throws, returns text + inline error message
# ----------------------------------------------------------------
my $r = eval_rules( "not json", "test" );
like( $r, qr/\bLocal rule error\b/i, "invalid JSON reports inline error" );
like( $r, qr/^test/,                 "original text preserved on JSON parse fail" );

# Rule structure must be an array
$r = eval_rules( '{"from":"a","to":"b"}', "test" );
like( $r, qr/\bLocal rule error\b/i, "non-array rules input reports error" );

# Bad regex doesn't crash
$r = eval_rules( '[{"from":"(unclosed","to":"x"}]', "test" );
like( $r, qr/\bLocal rule error\b/i, "bad regex reported, request not crashed" );

# Rules missing "from" or "to" silently skip rather than crashing
is( eval_rules( '[{"to":"x"}]',   "abc" ), "abc", "rule missing 'from' is skipped" );
is( eval_rules( '[{"from":"a"}]', "abc" ), "abc", "rule missing 'to' is skipped" );

# ----------------------------------------------------------------
# Critical: no Perl evaluation of user data
# Shell-metacharacters and Perl operators in `to` are treated as literals.
# ----------------------------------------------------------------
is(
    eval_rules( '[{"from":"x","to":"`echo PWN`"}]', "x marks the spot" ),
    "`echo PWN` marks the spot",
    "backticks in replacement are literal (no shell)"
);

is( eval_rules( '[{"from":"x","to":"@{[system(\\"id\\")]}"}]', "x" ),
    '@{[system("id")]}', 'Perl array-deref-with-system in "to" is literal (no Perl eval)' );

is( eval_rules( '[{"from":"x","to":"$ENV{PATH}"}]', "x" ),
    '$ENV{PATH}', '$ENV access in "to" is literal' );

done_testing;
