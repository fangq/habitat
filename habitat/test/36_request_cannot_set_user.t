#!/usr/bin/env perl
# A request must not be able to supply fields of the logged-in user's
# record. GetParam() falls back to %UserData, so a field read through it
# can also be set from the URL or a form:
#   - ?adminpw=<an admin's stored hash> made an anonymous visitor an
#     administrator (the stored hash worked as the password);
#   - username=<someone> on a save put that name on the revision.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use CGI;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
no warnings 'once';

$HabitatEngine::AdminPass       = "topsecret";
$HabitatEngine::EditPass        = "editorpw";
$HabitatEngine::PermEditAllowed = 1;

my $adminhash  = HabitatEngine::HashPassword("topsecret");
my $editorhash = HabitatEngine::HashPassword("editorpw");

sub req {
    my ( $params, %user ) = @_;
    $HabitatEngine::q        = CGI->new($params);
    %HabitatEngine::UserData = %user;
    $HabitatEngine::UserID   = $user{id} // 111;
}

# ---- adminpw from the request is ignored ----
req( { adminpw => $adminhash } );
is( HabitatEngine::UserIsAdmin(),     0,  "anonymous + ?adminpw=<admin hash>: not admin" );
is( HabitatEngine::UserIsEditor(),    0,  "  ... not editor" );
is( HabitatEngine::UserPermission(),  -1, "  ... clearance stays anonymous" );

req( { adminpw => $editorhash } );
is( HabitatEngine::UserIsEditor(), 0, "anonymous + ?adminpw=<editor hash>: not editor" );

req( { adminpw => $adminhash }, id => 1001, username => 'Bob' );
is( HabitatEngine::UserIsAdmin(), 0, "logged-in user without rights + ?adminpw=<admin hash>: not admin" );

req( { adminpw => 'x' }, id => 1001, username => 'Root', adminpw => $adminhash );
is( HabitatEngine::UserIsAdmin(), 1, "a real admin stays admin whatever ?adminpw= says" );

req( {}, id => 1002, username => 'Ed', adminpw => $editorhash );
is( HabitatEngine::UserIsAdmin(),  0, "editor token in the record: not admin" );
is( HabitatEngine::UserIsEditor(), 1, "  ... but editor" );

# ---- username from the request is ignored ----
req( { username => 'FakeAuthor' }, id => 1001, username => 'Bob' );
%HabitatEngine::Pages = ();
HabitatEngine::OpenNewSection( 'SomePage', 'text_default', '' );
is( $HabitatEngine::Pages{SomePage}{section}{username}, 'Bob', "a new revision carries the logged-in name, not ?username=" );

req( { username => 'FakeAuthor' } );
%HabitatEngine::Pages = ();
HabitatEngine::OpenNewSection( 'SomePage', 'text_default', '' );
is( $HabitatEngine::Pages{SomePage}{section}{username}, '', "anonymous edits carry no name, not ?username=" );

done_testing();
