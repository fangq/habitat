#!/usr/bin/env perl
# Page locks live in the "pagelock" table. Site configs written before
# the rename set $LockDir = "$TempDir/lock"; "lock" is a reserved word in
# MariaDB, so every lock query failed and locked pages stayed editable.
# DBTable now maps that old name to pagelock.

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

    package FakeCGI35;
    sub new   { bless {}, shift }
    sub param { return }
}
$HabitatEngine::q               = FakeCGI35->new;
$HabitatEngine::AdminPass       = "topsecret";
$HabitatEngine::EditPass        = "editorpw";
$HabitatEngine::PermEditAllowed = 0;

for my $lockdir ( '/old/temp/lock', '/new/temp/pagelock' ) {
    $HabitatEngine::LockDir = $lockdir;
    $dbh->do('DELETE FROM pagelock');
    is( HabitatEngine::IsPageLocked('Locked'), 0, "$lockdir: nothing locked yet" );
    HabitatEngine::WriteDBItems( HabitatEngine::DBTable($lockdir), 'id,tag', 1, ( 'Locked', 'L' ) );
    my ($n) = $dbh->selectrow_array("SELECT count(*) FROM pagelock WHERE id='Locked'");
    is( $n, 1, "$lockdir: the lock is stored in pagelock" );
    is( HabitatEngine::IsPageLocked('Locked'), 1, "$lockdir: page is locked" );
    is( HabitatEngine::IsPageLocked('Other'),  0, "$lockdir: other pages are not" );

    %HabitatEngine::UserData = ( id => 1001 );
    $HabitatEngine::UserID   = 1001;
    $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("editorpw");
    is( HabitatEngine::UserCanEdit( 'Locked', 1 ) ? 1 : 0, 0, "$lockdir: an editor may not edit a locked page" );
    ok( HabitatEngine::UserCanEdit( 'Other', 1 ), "$lockdir: ... but may edit others" );
    %HabitatEngine::UserData = ( id => 1001, adminpw => HabitatEngine::HashPassword("topsecret") );    # clearance is cached
    ok( HabitatEngine::UserCanEdit( 'Locked', 1 ), "$lockdir: an admin may" );
}

done_testing();
