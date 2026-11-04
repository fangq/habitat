#!/usr/bin/env perl
# Modules that an ordinary page view does not need are loaded on demand.
# Under plain CGI every `use` is paid on every request (~14 ms for these
# on the NeuroJSON host), so a top-level `use` of any of them is a
# performance regression. Each feature must still load what it needs.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

my @lazy = qw(Text/Diff.pm Text/Patch.pm HTML/Scrubber.pm JSON/PP.pm Crypt/Bcrypt.pm);

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once', 'redefine';
HabitatEngine::InitLinkPatterns();
{

    package FakeCGI18;
    sub new     { bless {}, shift }
    sub param   { return }
    sub charset { return }
    sub url     { return '' }
}
$HabitatEngine::q       = FakeCGI18->new;
$HabitatEngine::RawHtml = 1;

ok( !$INC{$_}, "not loaded by compiling the engine: $_" ) for @lazy;

# A trusted page with raw HTML: the common NeuroJSON page view.
$HabitatEngine::Pages{'Trusted'}{'page'}{'admin_saved'} = 1;
$HabitatEngine::Pages{'Trusted'}{'rules'}               = 1;
my $out = HabitatEngine::WikiToHTML( 'Trusted', "= T =\n<html><script>x()</script></html>\n" );
like( $out, qr/<script>x\(\)/, "trusted page rendered" );
ok( !$INC{$_}, "not loaded by rendering a trusted page: $_" ) for @lazy;

# Each feature still loads what it needs.
$HabitatEngine::Pages{'Untrusted'}{'page'}{'admin_saved'} = 0;
$HabitatEngine::Pages{'Untrusted'}{'rules'}               = 1;
$out = HabitatEngine::WikiToHTML( 'Untrusted', "<html><script>x()</script><b>ok</b></html>\n" );
unlike( $out, qr/<script/, "untrusted page scrubbed" );
ok( $INC{'HTML/Scrubber.pm'}, "  ... HTML::Scrubber loaded on demand" );

like( HabitatEngine::GetDiff( "a\n", "b\n" ), qr/^< a$/m, "diff works" );
ok( $INC{'Text/Diff.pm'}, "  ... Text::Diff loaded on demand" );

is( HabitatEngine::PatchText( "a\n", "1c1\n< a\n---\n> b\n" ), "b\n", "patch works" );
ok( $INC{'Text/Patch.pm'}, "  ... Text::Patch loaded on demand" );

like( HabitatEngine::HashPassword('pw12345678'), qr/\S/, "password hashing works" );
ok( $INC{'Crypt/Bcrypt.pm'}, "  ... Crypt::Bcrypt loaded on demand" );

is( HabitatEngine::EvalLocalRules( '[{"from":"a","to":"b"}]', "aaa", 0 ), "bbb", "JSON local rules work" );
ok( $INC{'JSON/PP.pm'}, "  ... JSON::PP loaded on demand" );

done_testing;
