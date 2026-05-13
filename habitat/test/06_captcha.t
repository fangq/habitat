#!/usr/bin/env perl
# Stage 1 HMAC captcha. Replaces the original DES-encrypted challenge
# with a signed "<answer>|<expires>|<sig>" token; PrintCaptcha embeds
# the token in a hidden form field and the visible question for the user.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

# ----------------------------------------------------------------
# PrintCaptcha output shape
# ----------------------------------------------------------------
my $html = HabitatEngine::PrintCaptcha();
like( $html, qr/<input[^>]+name=['"]captchaans['"]/,
    "PrintCaptcha emits the visible answer textbox" );
like( $html, qr/<input[^>]+name=['"]captchaopt['"][^>]+value="([^"]+)"/,
    "PrintCaptcha emits the hidden token" );

# Extract the visible operands and the hidden token from the rendered HTML
my ($a, $b) = $html =~ />(\d+)\+(\d+)=/;
ok( defined $a && defined $b, "rendered HTML shows the addition: $a + $b" );

my ($tok) = $html =~ /name=['"]captchaopt['"][^>]+value="([^"]+)"/;
ok( $tok, "captured hidden token: $tok" );
like( $tok, qr/\A\d+\|\d+\|[0-9a-f]{64}\z/,
    "token shape: <answer>|<exp>|<64-hex sig>" );

# The embedded answer must equal a+b
my ($ans) = split /\|/, $tok;
is( $ans, $a + $b, "embedded answer equals the visible sum" );

# Operands are in the documented range 1..24
cmp_ok( $a, '>=', 1,  "operand A >= 1" );
cmp_ok( $a, '<=', 24, "operand A <= 24" );
cmp_ok( $b, '>=', 1,  "operand B >= 1" );
cmp_ok( $b, '<=', 24, "operand B <= 24" );

# ----------------------------------------------------------------
# VerifyCaptcha
# ----------------------------------------------------------------
ok(  HabitatEngine::VerifyCaptcha( $ans,    $tok ), "correct answer verifies" );
ok( !HabitatEngine::VerifyCaptcha( $ans + 1, $tok ), "wrong answer rejected" );
ok( !HabitatEngine::VerifyCaptcha( $ans - 1, $tok ), "off-by-one rejected" );
ok(  HabitatEngine::VerifyCaptcha( "  $ans  ", $tok ),
    "whitespace around numeric answer accepted (trimmed)" );

# Non-numeric user input never matches
ok( !HabitatEngine::VerifyCaptcha("abc",   $tok ), "alpha answer rejected" );
ok( !HabitatEngine::VerifyCaptcha("1; --", $tok ), "SQL-injection-shaped answer rejected" );

# Missing inputs
ok( !HabitatEngine::VerifyCaptcha( undef, $tok ),  "undef answer rejected" );
ok( !HabitatEngine::VerifyCaptcha( $ans,  undef ), "undef token rejected" );
ok( !HabitatEngine::VerifyCaptcha( $ans,  "" ),    "empty token rejected" );
ok( !HabitatEngine::VerifyCaptcha( $ans,  "junk" ),"garbage token rejected" );

# ----------------------------------------------------------------
# Tampering
# ----------------------------------------------------------------
# Change the answer field but keep the original sig — should fail
my ( $orig_ans, $exp, $sig ) = split /\|/, $tok;
my $tampered = ( $orig_ans + 1 ) . "|$exp|$sig";
ok( !HabitatEngine::VerifyCaptcha( $orig_ans + 1, $tampered ),
    "answer tampering breaks signature" );

# Change the signature
my $bad_sig = $tok;
substr( $bad_sig, -1 ) = ( substr( $bad_sig, -1 ) eq 'a' ) ? 'b' : 'a';
ok( !HabitatEngine::VerifyCaptcha( $ans, $bad_sig ),
    "signature tampering rejected" );

# ----------------------------------------------------------------
# Expiry
# ----------------------------------------------------------------
# Token issued at $Now expires at $Now + 600
HabitatHarness::freeze_time(1_700_000_000 + 599);
ok(  HabitatEngine::VerifyCaptcha( $ans, $tok ),
    "token still valid 1s before expiry" );

HabitatHarness::freeze_time(1_700_000_000 + 601);
ok( !HabitatEngine::VerifyCaptcha( $ans, $tok ),
    "token rejected 1s after expiry" );
HabitatHarness::freeze_time(1_700_000_000);

# ----------------------------------------------------------------
# Two PrintCaptcha calls produce distinct tokens (CSPRNG operands)
# ----------------------------------------------------------------
my %distinct;
for ( 1 .. 20 ) {
    my $h = HabitatEngine::PrintCaptcha();
    my ($t) = $h =~ /name=['"]captchaopt['"][^>]+value="([^"]+)"/;
    $distinct{$t}++;
}
cmp_ok( scalar(keys %distinct), '>', 1,
    "20 PrintCaptcha calls produce more than one distinct token (operands varied)" );

done_testing;
