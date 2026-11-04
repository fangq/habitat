#!/usr/bin/env perl
# %EditPermissions restricts editing by page-name pattern without
# affecting reads: %Permissions (read clearance, and an edit grant)
# can open glyph pages to everyone for viewing while only admins edit.
# Also: UpdatePageLogDB (page visit counter, $UseDetailedLog) counts
# repeat visits instead of dying on a duplicate key / commit().
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

    package FakeCGI22;
    sub new   { bless {}, shift }
    sub param { return }
}
$HabitatEngine::q = FakeCGI22->new;

$HabitatEngine::AdminPass       = "topsecret";
$HabitatEngine::PermEditAllowed = 1;
%HabitatEngine::Permissions     = ( '_WQYS$' => -999 );
%HabitatEngine::EditPermissions = ( '_WQYS$' => 100, '_[0-9]+pt$' => 100 );

sub as {
    my ($who) = @_;
    %HabitatEngine::UserData = ();
    if ( $who eq 'anon' ) {
        $HabitatEngine::UserID = 111;
    } else {
        $HabitatEngine::UserID = 1001;
        $HabitatEngine::UserData{id} = 1001;
        $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("topsecret") if $who eq 'admin';
    }
}

as('anon');
is( HabitatEngine::UserCanEdit('U4E00_WQYS'), 0, 'anon: %Permissions -999 grant is overridden by %EditPermissions' );
is( HabitatEngine::UserCanEdit('Home'),       0, 'anon: ordinary page needs $PermEditAllowed' );
as('user');
is( HabitatEngine::UserCanEdit('U4E00_WQYS'), 0, 'registered: glyph page still admin-only' );
is( HabitatEngine::UserCanEdit('U4E00_12pt'), 0, 'registered: bitmap glyph admin-only' );
is( HabitatEngine::UserCanEdit('Home'),       1, 'registered: ordinary page editable' );
as('admin');
is( HabitatEngine::UserCanEdit('U4E00_WQYS'), 1, 'admin: glyph page editable' );
%HabitatEngine::EditPermissions = ();
as('anon');
is( HabitatEngine::UserCanEdit('U4E00_WQYS'), 1, 'without %EditPermissions the %Permissions grant applies' );

# UpdatePageLogDB
$HabitatEngine::UseDetailedLog = 1;
$HabitatEngine::Now            = 1000;
ok( eval { HabitatEngine::UpdatePageLogDB( 'pagelog', 'Home' ); 1 }, 'first visit logged' ) or diag $@;
$HabitatEngine::Now = 2000;
ok( eval { HabitatEngine::UpdatePageLogDB( 'pagelog', 'Home' ); 1 }, 'repeat visit does not die' ) or diag $@;
is_deeply( [ $dbh->selectrow_array("SELECT visit, lastvisit FROM pagelog WHERE id='Home'") ],
    [ 2, 2000 ], 'visit counted twice, lastvisit updated' );
is( $dbh->selectrow_array("SELECT COUNT(*) FROM pagelog"), 1, 'one row per page' );

done_testing;
