#!/usr/bin/env perl
# Tests for utils/migrate.pl. Spins up two on-disk SQLite files, the
# source carrying the legacy schema (with watch.user not watch.username
# and no login_attempts table) and the destination empty. Runs the
# real migrate.pl as a subprocess and verifies:
#   - destination schema gets provisioned via init_schema
#   - row counts match per table
#   - watch.user -> watch.username column rename applied
#   - tables missing from source are silently skipped (no error)
#   - dry-run mode doesn't write to destination

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use File::Temp qw(tempfile);
use DBI;
use HabitatHarness;

HabitatHarness::load_wiki();    # for the script's lib path setup

# Pre-flight: is sqlite3 driver available?
eval { require DBD::SQLite; } or plan skip_all => "DBD::SQLite not available";

# Two temp SQLite files (auto-removed when the test process exits)
my ( undef, $src_path ) = tempfile( "habitat-src-XXXX", SUFFIX => '.db',
    UNLINK => 1, OPEN => 0, TMPDIR => 1 );
my ( undef, $dst_path ) = tempfile( "habitat-dst-XXXX", SUFFIX => '.db',
    UNLINK => 1, OPEN => 0, TMPDIR => 1 );
unlink $dst_path;   # tempfile creates it; migrate.pl creates fresh

# ----------------------------------------------------------------
# Build a legacy source DB with the pre-Stage-4 schema
# ----------------------------------------------------------------
{
    my $dbh = DBI->connect( "dbi:SQLite:dbname=$src_path", "", "",
        { RaiseError => 1, AutoCommit => 1 } );
    $dbh->do(q{CREATE TABLE page (
        id varchar(512), version integer,
        author varchar(32), revision integer, tupdate integer, tcreate integer,
        ip varchar(32), host varchar(64), summary varchar(128), text text,
        minor integer, newauthor integer, data varchar(32), tag varchar(32)
    )});
    $dbh->do("CREATE INDEX page_id ON page(id ASC)");
    $dbh->do(q{CREATE TABLE user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name varchar(32), pass varchar(255), randkey varchar(255),
        groupid varchar(255), lang varchar(8), email varchar(64),
        param varchar(32), createtime integer, stylesheet varchar(128),
        createip varchar(32), tzoffset integer,
        pagecreate varchar(512), pagemodify varchar(512)
    )});
    $dbh->do("CREATE TABLE watch (page varchar(512), user varchar(32))");
    $dbh->do("CREATE TABLE system (id varchar(64) PRIMARY KEY, data text, time integer)");

    $dbh->do("INSERT INTO page (id, revision, author, text) VALUES (?,?,?,?)",
        undef, 'Home', 1, 'alice', 'hello v1');
    $dbh->do("INSERT INTO page (id, revision, author, text) VALUES (?,?,?,?)",
        undef, 'Home', 2, 'bob',   'hello v2');
    $dbh->do("INSERT INTO page (id, revision, author, text) VALUES (?,?,?,?)",
        undef, 'Other', 1, 'carol','another');

    $dbh->do("INSERT INTO user (name, email) VALUES (?,?)", undef, 'alice', 'a\@x');
    $dbh->do("INSERT INTO user (name, email) VALUES (?,?)", undef, 'bob',   'b\@x');

    $dbh->do("INSERT INTO watch (page, user) VALUES (?,?)", undef, 'Home',  'alice');
    $dbh->do("INSERT INTO watch (page, user) VALUES (?,?)", undef, 'Other', 'bob');

    $dbh->do("INSERT INTO system VALUES (?,?,?)", undef, 'lockstate', '0', 1700000000);
    $dbh->disconnect;
}

# ----------------------------------------------------------------
# Run the migration script as an out-of-process child so we exercise
# the same invocation path operators will use. STDERR captured via
# 2>&1 to /dev/null.
# ----------------------------------------------------------------
sub run_migrate {
    my @args = @_;
    my $script = "$Bin/../utils/migrate.pl";
    my $cmd = "perl $script @args 2>/dev/null";
    my $out = `$cmd`;
    my $rc  = $? >> 8;
    return ( $rc, $out );
}

# Dry run first — DBI's connect opens (and on SQLite creates) the
# file, but no schema and no rows should land in it.
{
    my ($rc, $out) = run_migrate(
        "--source", "dbi:SQLite:dbname=$src_path",
        "--dest",   "dbi:SQLite:dbname=$dst_path",
        "--dry-run",
    );
    is( $rc, 0, "dry-run exit code 0" );
    if ( -e $dst_path ) {
        my $d = DBI->connect( "dbi:SQLite:dbname=$dst_path", "", "",
            { RaiseError => 1, AutoCommit => 1 } );
        my ($tables) = $d->selectrow_array(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'" );
        is( $tables, 0, "dry-run leaves dest schema empty (no tables created)" );
        $d->disconnect;
        unlink $dst_path;
    } else {
        pass( "dry-run left no dest file at all" );
    }
}

# Real run
{
    my ($rc, $out) = run_migrate(
        "--source", "dbi:SQLite:dbname=$src_path",
        "--dest",   "dbi:SQLite:dbname=$dst_path",
    );
    is( $rc, 0, "migration exit code 0" );
    ok( -e $dst_path, "dest file created" );
    like( $out, qr/--- migration summary ---/, "summary block printed" );
}

# Verify destination schema and data
my $dst = DBI->connect( "dbi:SQLite:dbname=$dst_path", "", "",
    { RaiseError => 1, AutoCommit => 1 } );

# Schema: watch.username (not watch.user)
my $watch_sql = $dst->selectrow_array(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='watch'" );
like( $watch_sql, qr/\busername\b/i, "destination watch table has 'username' column" );
unlike( $watch_sql, qr/\buser\s+varchar/i, "destination watch table has no 'user' column" );

# Stage 5: page table now holds ONE row per id (the current revision).
# Historical revisions move to page_revisions. The legacy seed had
# Home/r1 + Home/r2 + Other/r1 = 3 source rows -> 2 current rows +
# 1 historical row.
is( $dst->selectrow_array("SELECT COUNT(*) FROM page"), 2,
    "page table has one row per id (current snapshot)" );
is( $dst->selectrow_array("SELECT COUNT(*) FROM page_revisions"), 1,
    "page_revisions has the older Home revision" );
is( $dst->selectrow_array("SELECT COUNT(*) FROM users"),  2, "user rows migrated" );
is( $dst->selectrow_array("SELECT COUNT(*) FROM watch"),  2, "watch rows migrated" );
is( $dst->selectrow_array("SELECT COUNT(*) FROM system"), 1, "system rows migrated" );

# Watch column data moved correctly to renamed column
my $rows = $dst->selectall_arrayref("SELECT page, username FROM watch ORDER BY page");
is_deeply( $rows,
    [ [ 'Home',  'alice' ], [ 'Other', 'bob' ] ],
    "watch.username data matches source watch.user" );

# Current page rows: just the latest revision per id.
my $pages = $dst->selectall_arrayref(
    "SELECT id, revision, author, text FROM page ORDER BY id" );
is_deeply(
    $pages,
    [
        [ 'Home',  2, 'bob',   'hello v2' ],
        [ 'Other', 1, 'carol', 'another' ],
    ],
    "page table contains only the current revision per id"
);

# Historical revisions: older Home/r1 lands in page_revisions.
my $revs = $dst->selectall_arrayref(
    "SELECT page_id, revision, author, kind, text FROM page_revisions ORDER BY page_id, revision"
);
is_deeply(
    $revs,
    [ [ 'Home', 1, 'alice', 'snapshot', 'hello v1' ] ],
    "page_revisions holds older Home/r1 as a snapshot"
);

# init_schema created the tables that source didn't have
ok( $dst->selectrow_array(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='login_attempts'" ),
    "destination has login_attempts table (created by init_schema even though source lacked it)" );
ok( $dst->selectrow_array(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rclog'" ),
    "destination has rclog table (created by init_schema)" );

# Stage 5: page table now has PRIMARY KEY (id) instead of the old
# UNIQUE(id, revision) index. The page_id_rev index is gone; verify
# the new constraint instead.
my $page_sql = $dst->selectrow_array(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='page'" );
like( $page_sql, qr/PRIMARY KEY/i,
    "destination page table has a primary key" );

$dst->disconnect;
unlink $dst_path;

# ----------------------------------------------------------------
# Idempotence: running migrate again to a fresh dest produces the same
# state (no duplicate rows, no errors)
# ----------------------------------------------------------------
{
    my ($rc, $out) = run_migrate(
        "--source", "dbi:SQLite:dbname=$src_path",
        "--dest",   "dbi:SQLite:dbname=$dst_path",
    );
    is( $rc, 0, "second migration exit code 0" );
    my $d = DBI->connect( "dbi:SQLite:dbname=$dst_path", "", "",
        { RaiseError => 1, AutoCommit => 1 } );
    is( $d->selectrow_array("SELECT COUNT(*) FROM page"), 2,
        "fresh dest also has 2 current page rows (deterministic)" );
    $d->disconnect;
}

done_testing;
