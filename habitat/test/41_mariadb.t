#!/usr/bin/env perl
# End-to-end MySQL/MariaDB tests: schema bootstrap, dialect helpers,
# Habitat::Store CRUD, and a SQLite -> MariaDB migration via
# utils/migrate.pl.
#
# Skipped if DBD::mysql / DBD::MariaDB isn't installed or no server
# is reachable. Operators with a local MariaDB can opt in by setting
# HABITAT_MARIADB_DSN to the connect string (e.g.
# "dbi:mysql:database=habitat_test;host=127.0.0.1") plus
# HABITAT_MARIADB_USER and HABITAT_MARIADB_PASS. Default tries the
# common "root@localhost / habitat_test" combination and skips
# cleanly if that fails — keeps `prove` green on workstations
# without a server.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

# Prefer DBD::MariaDB (modern, maintained) but fall back to DBD::mysql.
# Both register the same dialect token via Habitat::Store::dialect().
my $driver;

BEGIN {
    for my $d (qw(DBD::MariaDB DBD::mysql)) {
        my $m = $d;
        $m =~ s|::|/|g;
        eval { require "$m.pm"; 1 } and do { $driver = $d; last };
    }
    plan skip_all => "Neither DBD::MariaDB nor DBD::mysql installed"
      unless $driver;
}

my $dsn_default =
  ( $driver eq 'DBD::MariaDB' )
  ? "dbi:MariaDB:database=habitat_test;host=127.0.0.1"
  : "dbi:mysql:database=habitat_test;host=127.0.0.1";

my $dsn  = $ENV{HABITAT_MARIADB_DSN}  || $dsn_default;
my $user = $ENV{HABITAT_MARIADB_USER} || "root";
my $pass = $ENV{HABITAT_MARIADB_PASS} // "";

require DBI;
my $dbh = DBI->connect( $dsn, $user, $pass, { RaiseError => 0, PrintError => 0, AutoCommit => 1 } );
plan skip_all => "MariaDB/MySQL not reachable at $dsn: $DBI::errstr"
  if !$dbh;

local $SIG{__WARN__} = sub {
    return if $_[0] =~ /Use of uninitialized value/;
    return if $_[0] =~ /Duplicate key name/;
    warn $_[0];
};

# Reset any tables a previous test run left behind so we start
# from a known-clean state.
sub _reset_tables {
    my ($h) = @_;
    my @t = qw(
      login_attempts userlog pagelog system watch lock rclog html users
      deletedpage page_revisions page
    );
    eval { $h->do("SET FOREIGN_KEY_CHECKS=0") };
    for my $tbl (@t) {
        eval { $h->do("DROP TABLE IF EXISTS $tbl") };
    }
    eval { $h->do("SET FOREIGN_KEY_CHECKS=1") };
}
_reset_tables($dbh);

HabitatHarness::load_wiki();
require Habitat::Store;
no warnings 'once';
$HabitatEngine::dbh = $dbh;

# ----------------------------------------------------------------
# Dialect detection
# ----------------------------------------------------------------
is( Habitat::Store::dialect($dbh),
    'mysql', "dialect() reports mysql on the live MariaDB handle ($driver)" );
is( Habitat::Store::regex_op(), 'REGEXP', "regex_op() returns REGEXP for mysql" );
is( Habitat::Store::json_column_type('mysql'),
    'JSON', "json_column_type returns JSON for mysql dialect" );

# ----------------------------------------------------------------
# init_schema bootstraps every table; re-runs cleanly
# ----------------------------------------------------------------
Habitat::Store::init_schema($dbh);
Habitat::Store::init_schema($dbh);    # idempotency check

my @expected = qw(
  page page_revisions deletedpage users html rclog lock watch
  system pagelog userlog login_attempts
);
for my $tbl (@expected) {
    my ($ok) = $dbh->selectrow_array(
        "SELECT 1 FROM information_schema.tables
         WHERE table_schema=DATABASE() AND table_name=?", undef, $tbl
    );
    ok( $ok, "init_schema created table $tbl in mariadb" );
}

# ----------------------------------------------------------------
# Habitat::Store helpers work against MariaDB
# ----------------------------------------------------------------
use Habitat::Store qw(SafeIdent ReadDBItems WriteDBItems DeleteDBItems);

WriteDBItems( "system", "id,data,time", 0, ( "k1", "v1", 1000 ) );
is( ReadDBItems( "system", "data", "", "", "id=?", "k1" ),
    "v1", "WriteDBItems insert -> ReadDBItems on MariaDB" );

# REPLACE INTO upsert; same key, different value
WriteDBItems( "system", "id,data,time", 1, ( "k1", "v2", 2000 ) );
is( ReadDBItems( "system", "data,time", "", "|", "id=?", "k1" ),
    "v2|2000", "WriteDBItems upsert (REPLACE INTO) on MariaDB" );

WriteDBItems( "system", "id,data,time", 0, ( "k2", "v3", 3000 ) );
is( ReadDBItems( "system", "data", "", "", "id=?", "k2" ), "v3", "second row visible" );
DeleteDBItems( "system", "id=?", "k2" );
is( ReadDBItems( "system", "data", "", "", "id=?", "k2" ), "", "DeleteDBItems on MariaDB" );

# ----------------------------------------------------------------
# REGEXP filter via regex_op('REGEXP') on MariaDB
# ----------------------------------------------------------------
$dbh->do("INSERT INTO page (id, revision, text) VALUES ('Topic/Sub/01', 1, 'a')");
$dbh->do("INSERT INTO page (id, revision, text) VALUES ('Topic/Sub/02', 1, 'b')");
$dbh->do("INSERT INTO page (id, revision, text) VALUES ('Topic/Other',  1, 'c')");

my $op    = Habitat::Store::regex_op();
my $hits  = ReadDBItems( "page", "id", "\n", '', "id $op ? group by id", '^Topic/Sub/[0-9]+$' );
my @found = split /\n/, $hits;
is_deeply(
    [ sort @found ],
    [ 'Topic/Sub/01', 'Topic/Sub/02' ],
    "regex_op('REGEXP') filters subpages on MariaDB"
);

# ----------------------------------------------------------------
# Migration: SQLite -> MariaDB via utils/migrate.pl as a subprocess.
# ----------------------------------------------------------------
use File::Temp qw(tempfile);
my ( undef, $sqlite_src ) = tempfile(
    "habitat-mdbtest-XXXX",
    SUFFIX => '.db',
    UNLINK => 1,
    OPEN   => 0,
    TMPDIR => 1
);

{
    my $s =
      DBI->connect( "dbi:SQLite:dbname=$sqlite_src", "", "", { RaiseError => 1, AutoCommit => 1 } );
    $s->do(
        q{CREATE TABLE page (
        id varchar(512), version integer, author varchar(32), revision integer,
        tupdate integer, tcreate integer, ip varchar(32), host varchar(64),
        summary varchar(128), text text, minor integer, newauthor integer,
        data varchar(32), tag varchar(32)
    )}
    );
    $s->do(
        q{CREATE TABLE user (
        id integer PRIMARY KEY, name varchar(32), pass varchar(255),
        randkey varchar(255), groupid varchar(255), lang varchar(8),
        email varchar(64), param varchar(32), createtime integer,
        stylesheet varchar(128), createip varchar(32), tzoffset integer,
        pagecreate varchar(512), pagemodify varchar(512)
    )}
    );
    $s->do("CREATE TABLE watch (page varchar(512), user varchar(32))");
    $s->do( "INSERT INTO page (id, revision, author, text) VALUES (?,?,?,?)",
        undef, "MigratedPage", 1, "alice", "from sqlite" );
    $s->do( "INSERT INTO user (id, name, email) VALUES (?,?,?)", undef, 1001, "alice", 'a\@x' );
    $s->do( "INSERT INTO watch (page, user) VALUES (?,?)", undef, "MigratedPage", "alice" );
    $s->disconnect;
}

_reset_tables($dbh);

my $migrate = "$Bin/../utils/migrate.pl";
my $cmd     = qq{perl $migrate --source 'dbi:SQLite:dbname=$sqlite_src' --dest '$dsn'};
$cmd .= qq{ --dest-user '$user'} if length($user);
$cmd .= qq{ --dest-pass '$pass'} if length($pass);
$cmd .= qq{ 2>/dev/null};
my $out = `$cmd`;
is( $? >> 8, 0, "migrate.pl SQLite -> MariaDB exit code 0" );
like( $out, qr/--- migration summary ---/, "summary block printed" );

is( $dbh->selectrow_array("SELECT COUNT(*) FROM page"), 1, "page row migrated to MariaDB" );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM users"),
    1, "user -> users row migrated to MariaDB" );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM watch"), 1, "watch row migrated to MariaDB" );

my $r =
  $dbh->selectrow_arrayref("SELECT id, revision, author, text FROM page WHERE id='MigratedPage'");
is_deeply(
    $r,
    [ "MigratedPage", 1, "alice", "from sqlite" ],
    "page row data byte-equal after cross-dialect migration"
);

my $w = $dbh->selectrow_arrayref("SELECT page, username FROM watch WHERE page='MigratedPage'");
is_deeply(
    $w,
    [ "MigratedPage", "alice" ],
    "watch.user -> watch.username rename applied during SQLite -> MariaDB migration"
);

$dbh->disconnect;

done_testing;
