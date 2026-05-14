#!/usr/bin/env perl
# End-to-end Postgres tests: schema bootstrap, dialect helpers,
# Habitat::Store CRUD, and a SQLite -> Pg migration via migrate.pl.
#
# Skipped if DBD::Pg isn't installed or no PG instance is reachable
# under the test's DSN. Operators with a local PG can opt in by
# setting HABITAT_PG_DSN env var to the connect string (e.g.
# "dbi:Pg:dbname=habitat_test"); otherwise the test tries that exact
# default DSN and skips if it fails.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

BEGIN {
    eval { require DBD::Pg; 1 } or plan skip_all => "DBD::Pg not installed";
}

my $pg_dsn  = $ENV{HABITAT_PG_DSN}  || "dbi:Pg:dbname=habitat_test";
my $pg_user = $ENV{HABITAT_PG_USER} || "";
my $pg_pass = $ENV{HABITAT_PG_PASS} || "";

require DBI;
my $pg = DBI->connect(
    $pg_dsn, $pg_user, $pg_pass,
    { RaiseError => 0, PrintError => 0, AutoCommit => 1 }
);
plan skip_all => "Postgres instance not reachable at $pg_dsn: $DBI::errstr"
    if !$pg;

# Silence PG NOTICE chatter from CREATE TABLE IF NOT EXISTS when
# tables already exist — harmless and not relevant to assertions.
local $SIG{__WARN__} = sub {
    return if $_[0] =~ /relation .* already exists, skipping/;
    return if $_[0] =~ /Use of uninitialized value/;
    warn $_[0];
};

# Truncate any tables the wiki created on a previous run. Avoids
# the "DROP SCHEMA needs owner" rabbit hole and resets the wiki's
# tables specifically. init_schema below will re-create any that
# the previous run hadn't bootstrapped yet.
sub _reset_pg_tables {
    my ($dbh) = @_;
    my @t = qw(login_attempts userlog pagelog system watch lock rclog html users deletedpage page);
    for my $tbl (@t) {
        eval { $dbh->do("DROP TABLE IF EXISTS $tbl CASCADE") };
    }
}
_reset_pg_tables($pg);

HabitatHarness::load_wiki();
require Habitat::Store;
no warnings 'once';
$HabitatEngine::dbh = $pg;

# ----------------------------------------------------------------
# Dialect detection
# ----------------------------------------------------------------
is( Habitat::Store::dialect($pg), 'pg',  "dialect()  reports pg on the live PG handle" );
is( Habitat::Store::regex_op(),   '~',   "regex_op() returns '~' for pg" );

# ----------------------------------------------------------------
# init_schema on a fresh PG DB creates every table
# ----------------------------------------------------------------
Habitat::Store::init_schema($pg);

my @expected = qw(
    page deletedpage users html rclog lock watch system pagelog userlog login_attempts
);
for my $tbl (@expected) {
    my ($ok) = $pg->selectrow_array(
        "SELECT 1 FROM information_schema.tables
         WHERE table_schema=current_schema() AND table_name=?", undef, $tbl );
    ok( $ok, "init_schema created table $tbl in postgres" );
}

# ----------------------------------------------------------------
# Habitat::Store helpers work against PG
# ----------------------------------------------------------------
use Habitat::Store qw(SafeIdent ReadDBItems WriteDBItems DeleteDBItems);

# Insert through WriteDBItems (insert mode)
WriteDBItems( "system", "id,data,time", 0, ( "k1", "v1", 1000 ) );
is( ReadDBItems( "system", "data", "", "", "id=?", "k1" ), "v1", "WriteDBItems insert -> ReadDBItems on PG" );

# Replace through WriteDBItems (upsert path); same key, different value
WriteDBItems( "system", "id,data,time", 1, ( "k1", "v2", 2000 ) );
is( ReadDBItems( "system", "data,time", "", "|", "id=?", "k1" ), "v2|2000",
    "WriteDBItems upsert (ON CONFLICT DO UPDATE) on PG" );

# Insert a non-conflicting row, then delete it by bind
WriteDBItems( "system", "id,data,time", 0, ( "k2", "v3", 3000 ) );
is( ReadDBItems( "system", "data", "", "", "id=?", "k2" ), "v3", "second row visible" );
DeleteDBItems( "system", "id=?", "k2" );
is( ReadDBItems( "system", "data", "", "", "id=?", "k2" ), "", "DeleteDBItems on PG" );

# ----------------------------------------------------------------
# REGEXP fallback works via regex_op('~') on PG
# ----------------------------------------------------------------
$pg->do("INSERT INTO page (id, revision, text) VALUES ('Topic/Sub/01', 1, 'a')");
$pg->do("INSERT INTO page (id, revision, text) VALUES ('Topic/Sub/02', 1, 'b')");
$pg->do("INSERT INTO page (id, revision, text) VALUES ('Topic/Other',  1, 'c')");

my $op = Habitat::Store::regex_op();
my $hits = ReadDBItems( "page", "id", "\n", '', "id $op ? group by id",
    '^Topic/Sub/[0-9]+$' );
my @found = split /\n/, $hits;
is_deeply( [ sort @found ], [ 'Topic/Sub/01', 'Topic/Sub/02' ],
    "regex_op('~') filters subpages on PG" );

# ----------------------------------------------------------------
# Migration: SQLite -> Pg via utils/migrate.pl as a subprocess.
# Build a fresh sqlite source with a couple rows and then run the
# real migrate tool against this DB.
# ----------------------------------------------------------------
use File::Temp qw(tempfile);
my ( undef, $sqlite_src ) = tempfile( "habitat-pgtest-XXXX", SUFFIX => '.db',
    UNLINK => 1, OPEN => 0, TMPDIR => 1 );

{
    my $s = DBI->connect( "dbi:SQLite:dbname=$sqlite_src", "", "",
        { RaiseError => 1, AutoCommit => 1 } );
    $s->do(q{CREATE TABLE page (
        id varchar(512), version integer, author varchar(32), revision integer,
        tupdate integer, tcreate integer, ip varchar(32), host varchar(64),
        summary varchar(128), text text, minor integer, newauthor integer,
        data varchar(32), tag varchar(32)
    )});
    $s->do(q{CREATE TABLE user (
        id integer PRIMARY KEY, name varchar(32), pass varchar(255),
        randkey varchar(255), groupid varchar(255), lang varchar(8),
        email varchar(64), param varchar(32), createtime integer,
        stylesheet varchar(128), createip varchar(32), tzoffset integer,
        pagecreate varchar(512), pagemodify varchar(512)
    )});
    $s->do("CREATE TABLE watch (page varchar(512), user varchar(32))");
    $s->do("INSERT INTO page (id, revision, author, text) VALUES (?,?,?,?)",
        undef, "MigratedPage", 1, "alice", "from sqlite");
    $s->do("INSERT INTO user (id, name, email) VALUES (?,?,?)",
        undef, 1001, "alice", 'a\@x');
    $s->do("INSERT INTO watch (page, user) VALUES (?,?)",
        undef, "MigratedPage", "alice");
    $s->disconnect;
}

# Reset PG so the migration starts clean
_reset_pg_tables($pg);

my $migrate = "$Bin/../utils/migrate.pl";
my $cmd     = qq{perl $migrate --source 'dbi:SQLite:dbname=$sqlite_src' --dest '$pg_dsn' 2>/dev/null};
my $out     = `$cmd`;
is( $? >> 8, 0, "migrate.pl SQLite -> PG exit code 0" );
like( $out, qr/--- migration summary ---/, "summary block printed" );

# Re-read what landed in PG
is( $pg->selectrow_array("SELECT COUNT(*) FROM page"),  1, "page row migrated to PG" );
is( $pg->selectrow_array("SELECT COUNT(*) FROM users"), 1, "user -> users row migrated to PG" );
is( $pg->selectrow_array("SELECT COUNT(*) FROM watch"), 1, "watch row migrated to PG" );

my $r = $pg->selectrow_arrayref(
    "SELECT id, revision, author, text FROM page WHERE id='MigratedPage'" );
is_deeply( $r, [ "MigratedPage", 1, "alice", "from sqlite" ],
    "page row data byte-equal after cross-dialect migration" );

my $w = $pg->selectrow_arrayref(
    "SELECT page, username FROM watch WHERE page='MigratedPage'" );
is_deeply( $w, [ "MigratedPage", "alice" ],
    "watch.user -> watch.username rename applied during SQLite -> PG migration" );

$pg->disconnect;

done_testing;
