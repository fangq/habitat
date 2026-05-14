#!/usr/bin/env perl
# Bcrypt round-trips and the transparent legacy-crypt() fallback that
# DoLogin uses to migrate old hashes on the user's next successful sign-in.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::fresh_test_db();

# ----------------------------------------------------------------
# HashPassword / VerifyPassword round-trip
# ----------------------------------------------------------------
my $h1 = HabitatEngine::HashPassword("hello world");
like( $h1, qr/^\$2[abxy]\$/, "HashPassword returns a \$2b\$/\$2a\$/... prefix" );
cmp_ok( length($h1), '>=', 59, "bcrypt hash is at least 59 chars" );

ok( HabitatEngine::VerifyPassword( "hello world", $h1 ), "correct password verifies" );
ok( !HabitatEngine::VerifyPassword( "wrong",      $h1 ), "wrong password rejected" );
ok( !HabitatEngine::VerifyPassword( "",           $h1 ), "empty password rejected" );

# Same plaintext hashed twice gives different ciphertexts (per-account salt)
my $h2 = HabitatEngine::HashPassword("hello world");
isnt( $h1, $h2, "two HashPassword calls on same input yield different hashes (random salt)" );
ok( HabitatEngine::VerifyPassword( "hello world", $h2 ),
    "second hash also verifies its plaintext" );
ok( !HabitatEngine::VerifyPassword( "hello world", $h1 . "x" ),
    "tampered bcrypt hash fails verification" );

# Empty / undef inputs
is( HabitatEngine::HashPassword(""),    "", "HashPassword empty returns empty" );
is( HabitatEngine::HashPassword(undef), "", "HashPassword undef returns empty" );
ok( !HabitatEngine::VerifyPassword( "any", "" ),    "VerifyPassword against empty hash is false" );
ok( !HabitatEngine::VerifyPassword( "any", undef ), "VerifyPassword against undef hash is false" );
ok( !HabitatEngine::VerifyPassword( undef, $h1 ),   "VerifyPassword with undef pw is false" );

# ----------------------------------------------------------------
# IsLegacyPasswordHash
# ----------------------------------------------------------------
ok( !HabitatEngine::IsLegacyPasswordHash($h1), "bcrypt hash is NOT flagged as legacy" );
ok( !HabitatEngine::IsLegacyPasswordHash(''),
    "empty hash is NOT flagged as legacy (nothing to migrate)" );
ok( !HabitatEngine::IsLegacyPasswordHash(undef), "undef hash is NOT flagged as legacy" );

# crypt() classic 13-char DES output is legacy
my $legacy_des = crypt( "hello", "ab" );    # 13 chars on glibc, '$1$' on some platforms
ok( HabitatEngine::IsLegacyPasswordHash($legacy_des), "plain crypt() output IS flagged as legacy" )
  or diag("platform crypt() format: $legacy_des");

# ----------------------------------------------------------------
# VerifyPassword against legacy crypt() hashes
# ----------------------------------------------------------------
SKIP: {
    skip "platform crypt() produced unexpectedly short output", 2
      if length($legacy_des) < 13;

    ok(
        HabitatEngine::VerifyPassword( "hello", $legacy_des ),
        "correct password verifies against legacy crypt() hash"
    );
    ok(
        !HabitatEngine::VerifyPassword( "nope", $legacy_des ),
        "wrong password rejected against legacy crypt() hash"
    );
}

# ----------------------------------------------------------------
# UpgradePasswordHashDB — bcrypt-after-legacy-login migration
# ----------------------------------------------------------------
my $dbh = $HabitatEngine::dbh;
$dbh->do( "INSERT INTO users (id, name, pass) VALUES (1001, 'alice', ?)", undef, $legacy_des );

# Confirm the row is present with the legacy hash
my ($pass_before) = $dbh->selectrow_array("SELECT pass FROM users WHERE name='alice'");
is( $pass_before, $legacy_des, "user row seeded with legacy crypt() hash" );

# Pretend DoLogin succeeded and is now rehashing
my $new_hash = HabitatEngine::HashPassword("hello");
HabitatEngine::UpgradePasswordHashDB( "alice", $new_hash );

my ($pass_after) = $dbh->selectrow_array("SELECT pass FROM users WHERE name='alice'");
isnt( $pass_after, $legacy_des, "user row was updated" );
ok( $pass_after =~ /^\$2[abxy]\$/, "row now stores a bcrypt hash" );
ok(
    HabitatEngine::VerifyPassword( "hello", $pass_after ),
    "the rehashed value verifies the original cleartext password"
);

# Calling with empty values is safe
my $count_before = $dbh->selectrow_array("SELECT COUNT(*) FROM users");
HabitatEngine::UpgradePasswordHashDB( "",    $new_hash );
HabitatEngine::UpgradePasswordHashDB( "bob", "" );
my $count_after = $dbh->selectrow_array("SELECT COUNT(*) FROM users");
is( $count_before, $count_after, "UpgradePasswordHashDB no-ops on empty args" );

done_testing;
