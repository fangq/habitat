#!/usr/bin/env perl
# $AdminPass / $EditPass may hold "{bcrypt}<hash>" instead of the token
# (utils/hashpass.pl writes them). Tests that:
#   - a typed token is checked against the hash (preferences, registration)
#   - a user who typed a hashed token keeps a role code keyed with the site
#     secret, and only that code gives the rights: neither the config hash
#     nor a bcrypt hash of the token works as a stored value
#   - plain tokens keep working as before
#   - hashpass.pl converts a config in place, keeps users' rights, and
#     --set/--random/--grant replace a token

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use File::Temp qw(tempdir);
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::set_test_secret();
no warnings 'once';

my $ahash = '{bcrypt}' . HabitatEngine::HashPassword('adminTokenAAA');
my $ehash = '{bcrypt}' . HabitatEngine::HashPassword('editTokenEEE');
$HabitatEngine::AdminPass = "$ahash";
$HabitatEngine::EditPass  = "plainEditPPP $ehash";

sub rights {
    my ($stored) = @_;
    %HabitatEngine::UserData = ( adminpw => $stored );
    return ( HabitatEngine::UserIsAdmin() ? 'admin' : HabitatEngine::UserIsEditor() ? 'editor' : 'none' );
}

ok( HabitatEngine::IsHashedToken($ahash),          "{bcrypt} token is hashed" );
ok( !HabitatEngine::IsHashedToken('plainEditPPP'), "plain token is not" );
ok( HabitatEngine::TokenMatches( $ahash, 'adminTokenAAA' ),  "typed token matches its hash" );
ok( !HabitatEngine::TokenMatches( $ahash, 'adminTokenAAB' ), "  ... a wrong one does not" );
ok( !HabitatEngine::TokenMatches( $ahash, $ahash ),          "  ... nor the hash itself" );

my $acode = HabitatEngine::AdminTokenValue('adminTokenAAA');
like( $acode, qr/^\{role\}[0-9a-f]{64}$/, "typing a hashed admin token stores a role code" );
is( rights($acode), 'admin', "  ... which makes an admin" );
is( rights( HabitatEngine::AdminTokenValue('editTokenEEE') ), 'editor', "hashed editor token: editor" );
is( rights( HabitatEngine::AdminTokenValue('plainEditPPP') ), 'editor', "plain editor token still works" );
is( rights( HabitatEngine::AdminTokenValue('guess') ),        'none',   "wrong token: nothing" );
is( rights($ahash),                                           'none',   "the config hash as stored value: nothing" );
is( rights( substr( $ahash, 8 ) ),                            'none',   "  ... nor without {bcrypt}" );
is( rights( HabitatEngine::HashPassword('adminTokenAAA') ),   'none',   "a bcrypt hash of the token: nothing" );
{
    local $HabitatEngine::SiteSecret = 'y' x 64;
    is( rights($acode), 'none', "a role code from another site secret: nothing" );
}
{
    local $HabitatEngine::RegistrationPermission = 'admin';
    ok( HabitatEngine::RegistrationTokenOK('adminTokenAAA'), "registration accepts the hashed admin token" );
    ok( !HabitatEngine::RegistrationTokenOK($ahash),         "  ... not the hash" );
    local $HabitatEngine::RegistrationPermission = 'editor';
    ok( HabitatEngine::RegistrationTokenOK('editTokenEEE'), "  ... and the hashed editor token at editor level" );
}

# ----------------------------------------------------------------
# utils/hashpass.pl
# ----------------------------------------------------------------
eval { require DBD::SQLite; 1 } or do { done_testing(); exit 0; };

my $dir = tempdir( CLEANUP => 1 );
{
    open( my $fh, '>', "$dir/secret" ) or die;
    print $fh 's' x 64;
    close($fh);
}
my $dbh = DBI->connect( "dbi:SQLite:dbname=$dir/w.db", '', '', { RaiseError => 1, AutoCommit => 1 } );
Habitat::Store::init_schema($dbh);
my $ins = $dbh->prepare("INSERT INTO users (id, name, pass, groupid) VALUES (?,?,'',?)");
$ins->execute( 1001, 'alice', HabitatEngine::HashPassword('adm1nTokenX') );
$ins->execute( 1002, 'bob',   HabitatEngine::HashPassword('ed1tTokenY') );
$ins->execute( 1003, 'carol', HabitatEngine::HashPassword('notAToken') );
$ins->execute( 1004, 'dave',  '' );

my $conf = <<'C';
$AdminPass = "adm1nTokenX";    # admin token
$EditPass  = 'ed1tTokenY';
$DBName    = "dbi:SQLite:dbname=$DataDir/w.db";
1;
C
{
    open( my $fh, '>', "$dir/config" ) or die;
    print $fh $conf;
    close($fh);
    chmod 0640, "$dir/config";
}

sub hp { my $out = `$^X utils/hashpass.pl $dir/config @_ 2>&1`; return ( $? >> 8, $out ); }

sub site {    # the values the site would read, and its users' rights
    package HabitatEngine;
    our ( $AdminPass, $EditPass, $DataDir, $DBName, $SecretFile, $SiteSecret );
    $DataDir    = $dir;
    $SecretFile = "$dir/secret";
    undef $SiteSecret;
    do "$dir/config" or die $@;
    my %r;
    foreach my $row ( @{ $dbh->selectall_arrayref("SELECT name, groupid FROM users") } ) {
        $r{ $row->[0] } = main::rights( $row->[1] // '' );
    }
    return \%r;
}

my $before = site();
is_deeply( $before, { alice => 'admin', bob => 'editor', carol => 'none', dave => 'none' }, "rights before" );

my ( $rc, $out ) = hp('--dry-run');
is( $rc, 0, "dry run" ) or diag $out;
like( $out, qr/1 keep admin, 1 keep editor/, "  ... counts the users" );
is( do { local ( @ARGV, $/ ) = ("$dir/config"); <> }, $conf, "  ... and changes nothing" );

( $rc, $out ) = hp();
is( $rc, 0, "convert" ) or diag $out;
unlike( $out, qr/adm1nTokenX|ed1tTokenY|\$2b\$/, "  ... prints no token or hash" );
my $text = do { local ( @ARGV, $/ ) = ("$dir/config"); <> };
unlike( $text, qr/adm1nTokenX|ed1tTokenY/, "  ... no plain token left in the config" );
like( $text, qr/^\$AdminPass = '\{bcrypt\}\$2b\$12\$[^']+';    # admin token$/m, "  ... comment kept" );
is( ( stat("$dir/config") )[2] & 07777, 0640, "  ... permissions kept" );
is_deeply( site(), $before, "  ... everybody keeps their rights" );
ok( HabitatEngine::TokenMatches( $HabitatEngine::AdminPass, 'adm1nTokenX' ), "  ... the admin token still works" );

( $rc, $out ) = hp();
like( $out, qr/nothing to change/, "running it again changes nothing" );

( $rc, $out ) = hp( '--set', 'admin', '--random', "$dir/new.txt", '--grant', 'dave' );
is( $rc, 0, "--set admin --random --grant" ) or diag $out;
is( ( stat("$dir/new.txt") )[2] & 07777, 0600, "  ... token file readable only by its owner" );
my ($tok) = do { local ( @ARGV, $/ ) = ("$dir/new.txt"); <> } =~ /\$AdminPass: (\S+)/;
like( $tok // '', qr/^[A-Za-z0-9]{32}$/, "  ... 32 random letters and digits" );
unlike( $out, qr/\Q$tok\E/, "  ... not printed" );
is_deeply( site(), { alice => 'none', bob => 'editor', carol => 'none', dave => 'admin' },
    "  ... old admin loses the token, editor kept, dave granted" );
ok( HabitatEngine::TokenMatches( $HabitatEngine::AdminPass,  $tok ),          "  ... new token works" );
ok( !HabitatEngine::TokenMatches( $HabitatEngine::AdminPass, 'adm1nTokenX' ), "  ... old one does not" );

( $rc, $out ) = hp( '--grant', 'dave' );
isnt( $rc, 0, "--grant without --set is refused" );

done_testing();
