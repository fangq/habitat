#!/usr/bin/env perl
# $DBTablePrefix: a second wiki shares one database by prefixing every
# table name. The schema, page saves, login throttle and migrate.pl
# --dest-prefix all use the prefixed tables and never touch the
# unprefixed ones of the other wiki.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use File::Temp qw(tempfile);
use DBI;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::freeze_time(1_700_000_000);
HabitatEngine::InitLinkPatterns();
no warnings 'once';

sub tables {
    my ($dbh) = @_;
    return [ sort map { $_->[0] }
          @{ $dbh->selectall_arrayref("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") } ];
}

# The other wiki: unprefixed schema with one page.
my $dbh = HabitatHarness::fresh_test_db();
$dbh->do( "INSERT INTO page (id, revision, text) VALUES (?,?,?)", undef, 'Home', 1, 'main wiki' );
my $main_tables = tables($dbh);

# Second wiki in the same database.
$HabitatEngine::DBTablePrefix = 'dev_';
$Habitat::Store::TablePrefix  = 'dev_';
is( Habitat::Store::T('page'),           'dev_page',           'T(page)' );
is( Habitat::Store::T('page_revisions'), 'dev_page_revisions', 'T(page_revisions)' );
is( Habitat::Store::T('deletedpage'),    'deleteddev_page',    'T(deletedpage) follows the engine "deleted$pagedb" rule' );
is( HabitatEngine::DBTable($HabitatEngine::UserDir), 'dev_users', 'DBTable($UserDir)' );
is( HabitatEngine::DBTable('/data/temp/lock'),     'dev_pagelock', 'old $LockDir ".../lock" maps to pagelock' );
is( HabitatEngine::DBTable('/data/temp/pagelock'), 'dev_pagelock', 'new $LockDir ".../pagelock"' );
is( HabitatEngine::GetPageDB('Home'),   'dev_page', 'GetPageDB uses the prefix' );

Habitat::Store::init_schema($dbh);
my %all = map { $_ => 1 } @{ tables($dbh) };
my @want = map { Habitat::Store::T($_) } qw(page page_revisions deletedpage users html rclog pagelock watch system pagelog userlog login_attempts pagemeta);
is( scalar( grep { !$all{$_} } @want ), 0, 'init_schema created every prefixed table' ) or diag join ' ', sort keys %all;
is( scalar( keys %all ), 2 * @$main_tables, 'and nothing else (same number as the unprefixed set)' );
ok( $dbh->selectrow_array("SELECT data FROM dev_system WHERE id='schema_version'"), 'schema fingerprint stored in dev_system' );
is( Habitat::Store::ensure_schema($dbh), 0, 'ensure_schema finds the prefixed schema current' );

# Page save lands in dev_page / dev_page_revisions only.
{
    package FakeCGI;
    sub new   { bless {}, shift }
    sub param { return; }
}
$HabitatEngine::q            = FakeCGI->new;
$HabitatEngine::OpenPageName = '';
$HabitatEngine::UserID       = 1001;
$HabitatEngine::UserData{'id'}       = 1001;
$HabitatEngine::UserData{'username'} = 'alice';
for my $text ( "dev v1\n", "dev v2\n" ) {
    my $P = \%{ $HabitatEngine::Pages{'Home'}{'page'} };
    my $S = \%{ $HabitatEngine::Pages{'Home'}{'section'} };
    my $T = \%{ $HabitatEngine::Pages{'Home'}{'text'} };
    %$P = ( name => 'Home', version => 3, tscreate => $HabitatEngine::Now );
    %$S = ( name => 'text_default', ip => '127.0.0.1', host => 'localhost' );
    %$T = ( text => $text, summary => '', minor => 0, newauthor => 0 );
    HabitatEngine::SavePageDB('Home');
    $HabitatEngine::Now += 100;
}
is( $dbh->selectrow_array("SELECT text FROM dev_page WHERE id='Home'"), "dev v2\n", 'save wrote dev_page' );
is( $dbh->selectrow_array("SELECT text FROM dev_page_revisions WHERE page_id='Home'"), "dev v1\n", 'history in dev_page_revisions' );
is( $dbh->selectrow_array("SELECT text FROM page WHERE id='Home'"), 'main wiki', 'other wiki page untouched' );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM page_revisions"), 0, 'other wiki history untouched' );

# Login throttle uses dev_login_attempts.
Habitat::Auth::LoginThrottleHit('name:alice');
is( $dbh->selectrow_array("SELECT attempts FROM dev_login_attempts WHERE attempt_key='name:alice'"), 1, 'throttle in dev_login_attempts' );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM login_attempts"), 0, 'other wiki throttle untouched' );

# Site-wide edit lock lives in dev_system, not in the other wiki's system.
$dbh->do("INSERT INTO dev_system (id, data, time) VALUES ('lockstate', '1', 0)");
is( HabitatEngine::GetLockState(), 1, 'edit lock read from dev_system' );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM system WHERE id='lockstate'"), 0, 'other wiki not locked' );

ok( !eval { local $Habitat::Store::TablePrefix = 'x; drop'; Habitat::Store::T('page'); 1 }, 'unsafe prefix refused' );

$HabitatEngine::DBTablePrefix = '';
$Habitat::Store::TablePrefix  = '';
is( HabitatEngine::GetPageDB('Home'), 'page', 'no prefix: plain table names' );

# migrate.pl --dest-prefix: legacy source into prefixed tables.
SKIP: {
    eval { require DBD::SQLite; 1 } or skip 'DBD::SQLite not available', 6;
    my ( undef, $src_path ) = tempfile( 'habitat-src-XXXX', SUFFIX => '.db', UNLINK => 1, OPEN => 0, TMPDIR => 1 );
    my ( undef, $dst_path ) = tempfile( 'habitat-dst-XXXX', SUFFIX => '.db', UNLINK => 1, OPEN => 0, TMPDIR => 1 );
    my $s = DBI->connect( "dbi:SQLite:dbname=$src_path", '', '', { RaiseError => 1 } );
    $s->do( 'CREATE TABLE page (id varchar(512), version integer, author varchar(32), revision integer, tupdate integer, '
          . 'tcreate integer, ip varchar(32), host varchar(64), summary varchar(128), text text, minor integer, '
          . 'newauthor integer, data varchar(32), tag varchar(32))' );
    $s->do( 'CREATE TABLE user (id INTEGER PRIMARY KEY, name varchar(32), pass varchar(255), stylesheet varchar(128))' );
    $s->do( 'CREATE TABLE talk (id varchar(512), version integer, author varchar(32), revision integer, tupdate integer, '
          . 'tcreate integer, ip varchar(32), host varchar(64), summary varchar(128), text text, minor integer, '
          . 'newauthor integer, data varchar(32), tag varchar(32))' );
    $s->do( "INSERT INTO page (id, revision, text) VALUES ('Home',1,'a'),('Home',2,'b')" );
    $s->do( "INSERT INTO talk (id, revision, text) VALUES ('Home..discuss',1,'t')" );
    $s->do( "INSERT INTO user (id, name, pass) VALUES (1001,'alice','x')" );
    $s->disconnect;
    my $d = DBI->connect( "dbi:SQLite:dbname=$dst_path", '', '', { RaiseError => 1 } );
    $d->do("CREATE TABLE page (id varchar(512), revision integer, text text)");    # the other wiki
    $d->do("INSERT INTO page VALUES ('Home', 7, 'main wiki')");
    $d->disconnect;

    my $out = `perl $Bin/../utils/migrate.pl --source dbi:SQLite:dbname=$src_path --dest dbi:SQLite:dbname=$dst_path --dest-prefix dev_ --page-table talk 2>&1`;
    is( $? >> 8, 0, 'migrate --dest-prefix exit 0' ) or diag $out;
    $d = DBI->connect( "dbi:SQLite:dbname=$dst_path", '', '', { RaiseError => 1 } );
    is( $d->selectrow_array("SELECT text FROM dev_page WHERE id='Home'"), 'b', 'current revision in dev_page' );
    is( $d->selectrow_array("SELECT COUNT(*) FROM dev_page_revisions"), 1, 'older revision in dev_page_revisions' );
    is( $d->selectrow_array("SELECT name FROM dev_users WHERE id=1001"), 'alice', 'accounts in dev_users' );
    is( $d->selectrow_array("SELECT text FROM dev_talk WHERE id='Home..discuss'"), 't', '--page-table talk -> dev_talk' );
    is_deeply( $d->selectrow_arrayref("SELECT revision, text FROM page"), [ 7, 'main wiki' ], 'unprefixed page table untouched' );
}

done_testing;
