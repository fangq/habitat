#!/usr/bin/env perl
# Regression test for an old UseModWiki-era bug: a user who set their
# pref-side admin/editor password to match $EditPass would still be
# denied edit permission on the next request. Root cause was that the
# pre-Stage-1 prefs code stored the password via crypt() with a fixed
# salt derived from $CaptchaKey, plus a DES round-trip whose 8-byte
# truncation broke any password longer than 8 chars (and silently lost
# the trust if $CaptchaKey was rotated).
#
# Post-Stage-1: HashPassword (bcrypt $2b$12$ + random salt) stores
# the proof, VerifyPassword (bcrypt_check) verifies it. This test
# pins the working behavior so a future refactor can't silently
# regress it.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();

no warnings 'once';

{

    package FakeCGI15;
    sub new   { bless {}, shift }
    sub param { return }
}
$HabitatEngine::q = FakeCGI15->new;

# Site policy: editors and admins both gated by password tokens.
$HabitatEngine::AdminPass       = "topsecret";
$HabitatEngine::EditPass        = "editorpw";
$HabitatEngine::PermEditAllowed = 1;

sub reset_user {
    %HabitatEngine::UserData = ();
    $HabitatEngine::UserID   = 1001;
}

# ----------------------------------------------------------------
# UserIsEditor / UserIsAdmin against the in-memory pref hash.
# ----------------------------------------------------------------
reset_user();
is( HabitatEngine::UserIsAdmin(),  0, "anon: not admin" );
is( HabitatEngine::UserIsEditor(), 0, "anon: not editor" );

reset_user();
$HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("editorpw");
is( HabitatEngine::UserIsAdmin(),  0, "editor-pw user: not admin" );
is( HabitatEngine::UserIsEditor(), 1, "editor-pw user: IS editor (the bug)" );

reset_user();
$HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("wrong");
is( HabitatEngine::UserIsAdmin(),  0, "wrong pw: not admin" );
is( HabitatEngine::UserIsEditor(), 0, "wrong pw: not editor" );

reset_user();
$HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("topsecret");
is( HabitatEngine::UserIsAdmin(),  1, "admin pw: is admin" );
is( HabitatEngine::UserIsEditor(), 1, "admin pw: admin includes editor" );

# ----------------------------------------------------------------
# Multi-token $EditPass: any one match grants editor.
# ----------------------------------------------------------------
{
    local $HabitatEngine::EditPass = "pwA pwB pwC";
    reset_user();
    $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("pwB");
    is( HabitatEngine::UserIsEditor(), 1, "multi-token EditPass: middle token matches" );

    reset_user();
    $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("pwZ");
    is( HabitatEngine::UserIsEditor(), 0, "multi-token EditPass: no token matches" );
}

# ----------------------------------------------------------------
# UserPermission and UserCanEdit observe the editor grant.
# ----------------------------------------------------------------
reset_user();
$HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("editorpw");
is( HabitatEngine::UserPermission(),             50, "editor pref maps to clearance 50" );
is( HabitatEngine::UserCanEdit( 'SomePage', 0 ), 1,  "editor can edit a normal page" );

reset_user();
$HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("wrong");
isnt( HabitatEngine::UserPermission(), 50, "wrong pw does NOT map to editor clearance" );

# ----------------------------------------------------------------
# Long passwords: pre-Stage-1 DES crypt truncated at 8 bytes, so two
# distinct long passwords sharing the first 8 chars were
# indistinguishable. Bcrypt has no such limit (up to 72 bytes).
# ----------------------------------------------------------------
{
    local $HabitatEngine::EditPass = "thisIsAReallyLongEditorPassword";
    reset_user();
    $HabitatEngine::UserData{adminpw} =
      HabitatEngine::HashPassword("thisIsAReallyLongEditorPassword");
    is( HabitatEngine::UserIsEditor(),
        1, "long password: full string matches (bcrypt, not 8-byte DES)" );

    reset_user();

    # Same first 8 chars, different tail — DES would have collided.
    $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("thisIsADifferentTail");
    is( HabitatEngine::UserIsEditor(), 0, "long password: first-8-char prefix collision rejected" );
}

# ----------------------------------------------------------------
# End-to-end persistence: write a user row with adminpw stored as a
# bcrypt hash in the `groupid` column, then LoadUserDataDB and check
# permission. This is the exact path that broke in the old wiki: the
# pref survived the save but failed verification on reload.
# ----------------------------------------------------------------
my $stored_hash = HabitatEngine::HashPassword("editorpw");
$dbh->do(
    "INSERT INTO users (id, name, pass, groupid, lang, email, param, "
      . "createtime, prefs, createip, tzoffset, pagecreate, pagemodify) "
      . "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
    undef,
    1001,
    "alice",
    "",
    $stored_hash,
    "en",
    "alice\@x",
    "",
    1_700_000_000,
    "{}",
    "127.0.0.1",
    0,
    "",
    ""
);

reset_user();
$HabitatEngine::UserDir = "users";    # so LoadUserDataDB hits the right table
HabitatEngine::LoadUserDataDB( 1001, "" );

is( $HabitatEngine::UserData{adminpw},
    $stored_hash, "LoadUserDataDB restores bcrypt hash byte-for-byte from groupid" );
is( HabitatEngine::UserIsEditor(), 1, "after DB round-trip: editor permission survives" );
is( HabitatEngine::UserCanEdit( 'AnyPage', 0 ), 1,
    "after DB round-trip: UserCanEdit returns true" );

done_testing;
