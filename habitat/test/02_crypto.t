#!/usr/bin/env perl
# Stage 1 cryptographic primitives: CSPRNG byte source, HMAC, and the
# constant-time comparator used by every token verification path.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::set_test_secret();

# ----------------------------------------------------------------
# RandomBytes / RandomHex
# ----------------------------------------------------------------
my $a = HabitatEngine::RandomBytes(16);
my $b = HabitatEngine::RandomBytes(16);
is( length($a), 16, "RandomBytes(16) returns 16 bytes" );
is( length($b), 16, "RandomBytes(16) returns 16 bytes (2nd call)" );
isnt( $a, $b, "two RandomBytes calls return different data (probabilistic)" );

is( length( HabitatEngine::RandomBytes(1) ),  1,  "RandomBytes(1)" );
is( length( HabitatEngine::RandomBytes(64) ), 64, "RandomBytes(64)" );

# Defaults to 32 when n is missing / zero / negative
is( length( HabitatEngine::RandomBytes() ),    32, "default length is 32" );
is( length( HabitatEngine::RandomBytes(0) ),   32, "0 falls back to default 32" );
is( length( HabitatEngine::RandomBytes(-1) ),  32, "negative falls back to default 32" );

my $hex = HabitatEngine::RandomHex(8);
is( length($hex), 16, "RandomHex(8) -> 16 hex chars" );
like( $hex, qr/\A[0-9a-f]+\z/, "RandomHex output is lowercase hex" );

# Tiny statistical sanity: 1000 bytes should have reasonable entropy.
my $bulk    = HabitatEngine::RandomBytes(1000);
my %seen    = map { $_ => 1 } split //, $bulk;
cmp_ok( scalar(keys %seen), '>', 50,
    "1000 random bytes hit more than 50 distinct byte values (not all-zero)" );

# ----------------------------------------------------------------
# Hmac
# ----------------------------------------------------------------
my $h1 = HabitatEngine::Hmac("foo");
my $h2 = HabitatEngine::Hmac("foo");
my $h3 = HabitatEngine::Hmac("bar");

is( length($h1), 64, "HMAC-SHA256 hex output is 64 chars" );
like( $h1, qr/\A[0-9a-f]+\z/, "HMAC output is lowercase hex" );
is(   $h1, $h2,  "HMAC is deterministic for same input + same secret" );
isnt( $h1, $h3,  "HMAC differs for different input" );

# Different secret => different HMAC (rotate secret, recompute, restore)
my $old_secret = $HabitatEngine::SiteSecret;
{
    no warnings 'once';
    $HabitatEngine::SiteSecret = "y" x 64;
}
my $h4 = HabitatEngine::Hmac("foo");
isnt( $h1, $h4, "HMAC changes when secret rotates (invalidates old tokens)" );
{
    no warnings 'once';
    $HabitatEngine::SiteSecret = $old_secret;
}

# Long input doesn't blow up
my $big = HabitatEngine::Hmac( "x" x 100_000 );
is( length($big), 64, "HMAC of 100 KB still 64 hex chars" );

# ----------------------------------------------------------------
# ConstantEq
# ----------------------------------------------------------------
ok(  HabitatEngine::ConstantEq( "abc",       "abc" ),       "equal strings" );
ok( !HabitatEngine::ConstantEq( "abc",       "abd" ),       "diff last char" );
ok( !HabitatEngine::ConstantEq( "abc",       "Abc" ),       "case-sensitive" );
ok( !HabitatEngine::ConstantEq( "abc",       "abcd" ),      "different lengths" );
ok( !HabitatEngine::ConstantEq( "abcd",      "abc" ),       "different lengths reversed" );
ok( !HabitatEngine::ConstantEq( undef,       "abc" ),       "undef LHS" );
ok( !HabitatEngine::ConstantEq( "abc",       undef ),       "undef RHS" );
ok( !HabitatEngine::ConstantEq( undef,       undef ),       "both undef" );
ok(  HabitatEngine::ConstantEq( "",          "" ),          "empty == empty" );
ok( !HabitatEngine::ConstantEq( "",          "x" ),         "empty != nonempty" );

# Multi-byte and binary content
ok(  HabitatEngine::ConstantEq( "\x00\xff",  "\x00\xff" ),  "binary equal" );
ok( !HabitatEngine::ConstantEq( "\x00\xff",  "\x00\xfe" ),  "binary diff" );

# Comparing two 64-char hex strings (the realistic HMAC case)
my $sig = HabitatEngine::Hmac("token");
ok( HabitatEngine::ConstantEq( $sig, HabitatEngine::Hmac("token") ),
    "fresh HMAC compares equal" );
ok( !HabitatEngine::ConstantEq( $sig, HabitatEngine::Hmac("token2") ),
    "different HMACs compare unequal" );

done_testing;
