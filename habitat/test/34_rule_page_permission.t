#!/usr/bin/env perl
# Rule pages (Page/.v0, .v1, .e0, .e1) change how other pages render and
# .v1 output is not scrubbed, so only administrators may edit them: a
# user, an editor (EditPass) or a page-specific grant is never enough.

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

    package FakeCGI34;
    sub new   { bless {}, shift }
    sub param { return }
}
$HabitatEngine::q               = FakeCGI34->new;
$HabitatEngine::AdminPass       = "topsecret";
$HabitatEngine::EditPass        = "editorpw";
$HabitatEngine::PermEditAllowed = 0;    # everyone may edit ordinary pages
%HabitatEngine::EditPermissions = ();

sub as {
    my ($who) = @_;
    %HabitatEngine::UserData = ();
    $HabitatEngine::UserID   = $who eq 'anon' ? 111 : 1001;
    $HabitatEngine::UserData{id} = 1001 if ( $who ne 'anon' );
    $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("editorpw")  if ( $who eq 'editor' );
    $HabitatEngine::UserData{adminpw} = HabitatEngine::HashPassword("topsecret") if ( $who eq 'admin' );
}

for my $who (qw(anon user editor admin)) {
    as($who);
    ok( HabitatEngine::UserCanEdit( 'Notes/Page', 1 ), "$who may edit an ordinary page" ) if ( $who ne 'anon' );
    for my $rule (qw(Notes/.v0 Notes/.v1 Notes/.e0 Notes/.e1 A/B/.v1)) {
        my $can = HabitatEngine::UserCanEdit( $rule, 1 ) ? 1 : 0;
        is( $can, $who eq 'admin' ? 1 : 0, "$who " . ( $who eq 'admin' ? 'may' : 'may not' ) . " edit $rule" );
    }
}

# A page-name grant does not open rule pages to editors.
%HabitatEngine::Permissions = ( '^Notes' => 50 );
as('editor');
is( HabitatEngine::UserCanEdit( 'Notes/.v1', 1 ) ? 1 : 0, 0, "a %Permissions grant does not open rule pages" );

done_testing();
