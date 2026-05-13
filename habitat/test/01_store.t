#!/usr/bin/env perl
# Characterization tests for Habitat::Store — the DB helper module
# extracted in stage3.  Uses an in-memory SQLite handle so each test
# starts from a blank schema with no cross-test bleed.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();

use Habitat::Store qw(SafeIdent ReadDBItems WriteDBItems DeleteDBItems CopyDBItems);

# ----------------------------------------------------------------
# SafeIdent
# ----------------------------------------------------------------
ok(  SafeIdent("page"),         "lowercase ident accepted" );
ok(  SafeIdent("RcLog_2"),      "mixed case + digit + underscore accepted" );
ok(  SafeIdent("_under"),       "leading underscore accepted" );
ok( !SafeIdent(""),             "empty rejected" );
ok( !SafeIdent(undef),          "undef rejected" );
ok( !SafeIdent("1page"),        "leading digit rejected" );
ok( !SafeIdent("page;drop"),    "semicolon rejected" );
ok( !SafeIdent("page-1"),       "hyphen rejected" );
ok( !SafeIdent("page name"),    "space rejected" );
ok( !SafeIdent("page'"),        "quote rejected" );
ok( !SafeIdent("page\nrow"),    "newline rejected" );

# ----------------------------------------------------------------
# WriteDBItems — insert and replace
# ----------------------------------------------------------------
WriteDBItems( "system", "id,data,time", 0, ( "k1", "v1", 1000 ) );
my $row = $dbh->selectrow_arrayref("SELECT data, time FROM system WHERE id='k1'");
is_deeply( $row, [ "v1", 1000 ], "insert wrote row" );

# Reject unsafe table name
eval { WriteDBItems( "system; drop table page; --", "id", 0, ("x") ) };
like( $@, qr/unsafe table name/, "WriteDBItems rejects unsafe table name" );

# Reject unsafe field name
eval { WriteDBItems( "system", "id,da;ta,time", 0, ( "k2", "v2", 1 ) ) };
like( $@, qr/unsafe field name/, "WriteDBItems rejects unsafe field name" );

# Replace overwrites
WriteDBItems( "system", "id,data,time", 1, ( "k1", "v2", 2000 ) );
$row = $dbh->selectrow_arrayref("SELECT data, time FROM system WHERE id='k1'");
is_deeply( $row, [ "v2", 2000 ], "replace overwrote row" );

# Values are bind-bound, never interpolated — quote in value is harmless
WriteDBItems( "system", "id,data,time", 0, ( "quote_test", "it's ok", 3 ) );
my $got = $dbh->selectrow_array("SELECT data FROM system WHERE id='quote_test'");
is( $got, "it's ok", "single quote in value passes through unescaped" );

# ----------------------------------------------------------------
# ReadDBItems
# ----------------------------------------------------------------
$dbh->do("DELETE FROM system");
WriteDBItems( "system", "id,data,time", 0, ( "a", "1", 10 ) );
WriteDBItems( "system", "id,data,time", 0, ( "b", "2", 20 ) );
WriteDBItems( "system", "id,data,time", 0, ( "c", "3", 30 ) );

is( ReadDBItems( "system", "data", "", "", "id=?", "a" ),
    "1", "single value lookup with bind" );

is( ReadDBItems( "system", "data", ",", "", "" ),
    "1,2,3", "no where clause, no glue, glue1 only" );

is( ReadDBItems( "system", "id,data", "\n", "=", "" ),
    "a=1\nb=2\nc=3", "multi-column with both glues" );

is( ReadDBItems( "system", "data", "", "", "id=?", "missing" ),
    "", "lookup miss returns empty string" );

# Bind values prevent injection
my $payload = "a' OR '1'='1";
is( ReadDBItems( "system", "data", "", "", "id=?", $payload ),
    "", "SQLi attempt in bind value matches no row (proper binding)" );

# Unsafe identifiers are rejected
eval { ReadDBItems( "system; drop table page; --", "*", "", "", "" ) };
like( $@, qr/unsafe table name/, "ReadDBItems rejects unsafe table name" );

# ----------------------------------------------------------------
# DeleteDBItems
# ----------------------------------------------------------------
my $n_before = $dbh->selectrow_array("SELECT COUNT(*) FROM system");
DeleteDBItems( "system", "" );
my $n_after = $dbh->selectrow_array("SELECT COUNT(*) FROM system");
is( $n_after, $n_before,
    "empty conditions intentionally refuses to wipe table (safety guard)" );

DeleteDBItems( "system", "id=?", "b" );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM system"), 2, "delete with bind removed one row" );
is( $dbh->selectrow_array("SELECT data FROM system WHERE id='b'"), undef, "specific row gone" );
is( $dbh->selectrow_array("SELECT data FROM system WHERE id='a'"), "1", "other rows intact" );

eval { DeleteDBItems( "drop table page; --", "id=?", "x" ) };
like( $@, qr/unsafe table name/, "DeleteDBItems rejects unsafe table name" );

# ----------------------------------------------------------------
# CopyDBItems
# ----------------------------------------------------------------
$dbh->do("DELETE FROM page");
$dbh->do("DELETE FROM deletedpage");
$dbh->do( "INSERT INTO page (id, revision, text) VALUES ('PageA', 1, 'hello')" );
$dbh->do( "INSERT INTO page (id, revision, text) VALUES ('PageB', 1, 'world')" );

CopyDBItems( "page", "deletedpage", "id=?", "PageA" );
my $copied = $dbh->selectrow_array("SELECT text FROM deletedpage WHERE id='PageA'");
is( $copied, "hello", "CopyDBItems copied matching row" );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM deletedpage"),
    1, "CopyDBItems copied exactly one row" );

# Empty conditions is a no-op (refuses to copy entire table)
$dbh->do("DELETE FROM deletedpage");
my $result = CopyDBItems( "page", "deletedpage", "" );
is( $result, 0, "CopyDBItems returns 0 for empty conditions" );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM deletedpage"),
    0, "CopyDBItems with empty conditions copied nothing" );

eval { CopyDBItems( "page; drop", "deletedpage", "id=?", "x" ) };
like( $@, qr/unsafe table name/, "CopyDBItems rejects unsafe source table" );

eval { CopyDBItems( "page", "deleted; drop", "id=?", "x" ) };
like( $@, qr/unsafe table name/, "CopyDBItems rejects unsafe destination table" );

# ----------------------------------------------------------------
# Error handling: uninitialized DB
# ----------------------------------------------------------------
{
    local $HabitatEngine::dbh = undef;
    eval { ReadDBItems( "system", "*", "", "", "" ) };
    like( $@, qr/database uninitialized/, "uninitialized DB triggers descriptive die" );
}

done_testing;
