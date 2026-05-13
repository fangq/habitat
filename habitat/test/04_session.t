#!/usr/bin/env perl
# HMAC-signed session cookie tokens introduced in stage1. The token
# format is "<uid>|<expires>|<sig>" and the verification path is what
# replaces the legacy per-IP randkey scheme in InitCookie.

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
# Sign / verify round-trip
# ----------------------------------------------------------------
my $tok = HabitatEngine::SignSessionToken(1001);
like( $tok, qr/\A\d+\|\d+\|[0-9a-f]{64}\z/,
    "token shape: <uid>|<exp>|<64-hex sig>" );
is( HabitatEngine::VerifySessionToken($tok), 1001,
    "fresh token verifies and returns the uid" );

# Default lifetime is 30 days
my ( $uid, $exp, $sig ) = split /\|/, $tok;
is( $uid, 1001, "uid component" );
is( $exp, 1_700_000_000 + 30 * 86400, "expiry is now + 30d by default" );

# Custom TTL
my $short = HabitatEngine::SignSessionToken( 1001, 60 );
my (undef, $exp_short) = split /\|/, $short;
is( $exp_short, 1_700_000_000 + 60, "custom TTL honored" );

# ----------------------------------------------------------------
# Rejection cases
# ----------------------------------------------------------------
is( HabitatEngine::VerifySessionToken(undef),     0, "undef rejected" );
is( HabitatEngine::VerifySessionToken(""),        0, "empty rejected" );
is( HabitatEngine::VerifySessionToken("garbage"), 0, "garbage rejected" );
is( HabitatEngine::VerifySessionToken({}),        0, "hashref rejected" );

# Old-style cookie format (rev&id&randkey&lang) must NOT verify
is( HabitatEngine::VerifySessionToken("rev&1&id&1001&randkey&abc&lang&en"),
    0, "legacy multi-field cookie format rejected" );

# Tampered uid -- signature mismatch
my $tampered = $tok;
$tampered =~ s/^1001/1002/;
is( HabitatEngine::VerifySessionToken($tampered), 0,
    "uid tampering invalidates token" );

# Tampered signature
my $bad_sig = $tok;
substr( $bad_sig, -1 ) = ( substr( $bad_sig, -1 ) eq 'a' ) ? 'b' : 'a';
is( HabitatEngine::VerifySessionToken($bad_sig), 0,
    "signature tampering invalidates token" );

# Tampered expiry -- changes signed content
my $bad_exp = "$uid|" . ( $exp + 1 ) . "|$sig";
is( HabitatEngine::VerifySessionToken($bad_exp), 0,
    "expiry tampering invalidates token" );

# Invalid uid input
is( HabitatEngine::SignSessionToken( "", 60 ),       "", "empty uid -> empty token" );
is( HabitatEngine::SignSessionToken( "abc", 60 ),    "", "non-numeric uid -> empty token" );
is( HabitatEngine::SignSessionToken( 0, 60 ),        "", "zero uid -> empty token" );
is( HabitatEngine::SignSessionToken( -5, 60 ),       "", "negative uid -> empty token" );

# ----------------------------------------------------------------
# Expiry
# ----------------------------------------------------------------
my $tok_short = HabitatEngine::SignSessionToken( 1001, 60 );
{
    HabitatHarness::freeze_time(1_700_000_000 + 59);
    is( HabitatEngine::VerifySessionToken($tok_short), 1001,
        "token valid 1s before expiry" );
}
{
    HabitatHarness::freeze_time(1_700_000_000 + 61);
    is( HabitatEngine::VerifySessionToken($tok_short), 0,
        "token rejected 1s after expiry" );
}
HabitatHarness::freeze_time(1_700_000_000);    # restore

# ----------------------------------------------------------------
# Secret rotation
# ----------------------------------------------------------------
my $tok_old_secret = HabitatEngine::SignSessionToken(1001);
{
    no warnings 'once';
    local $HabitatEngine::SiteSecret = "rotated" x 10;
    is( HabitatEngine::VerifySessionToken($tok_old_secret), 0,
        "rotating the site secret invalidates pre-rotation tokens" );
}

# ----------------------------------------------------------------
# IsRequestSecure
# ----------------------------------------------------------------
{
    local %ENV = ( HTTPS => "on" );
    is( HabitatEngine::IsRequestSecure(), 1, "HTTPS=on detected" );
}
{
    local %ENV = ( SERVER_PORT => 443 );
    is( HabitatEngine::IsRequestSecure(), 1, "SERVER_PORT=443 detected" );
}
{
    local %ENV = ( SERVER_PORT => 80 );
    is( HabitatEngine::IsRequestSecure(), 0, "port 80 is not secure" );
}
{
    # X-Forwarded-Proto is only honored when the upstream is in $TrustedProxies
    no warnings 'once';
    local $HabitatEngine::TrustedProxies = '';
    local %ENV = ( REMOTE_ADDR => "127.0.0.1", HTTP_X_FORWARDED_PROTO => "https" );
    is( HabitatEngine::IsRequestSecure(), 0,
        "X-Forwarded-Proto ignored when no trusted proxies configured" );

    local $HabitatEngine::TrustedProxies = '127.0.0.1';
    is( HabitatEngine::IsRequestSecure(), 1,
        "X-Forwarded-Proto honored when REMOTE_ADDR is in TrustedProxies" );
}

done_testing;
