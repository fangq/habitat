#!/usr/bin/env perl
# $RegistrationPermission: who may create an account.
#   'user'   - anyone
#   'editor' - (default) only with a registration token from $EditPass or $AdminPass
#   'admin'  - only with a registration token from $AdminPass
# A refused registration is aborted before any account is set up, so no
# user row is written; failures are throttled per IP. The registration
# token only unlocks sign-up: it is never stored, and the new account is
# an ordinary user. Existing users' preference saves are not affected.

use strict;
use warnings;

BEGIN { *CORE::GLOBAL::exit = sub { die "EXIT\n" }; }

use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use CGI;
use JSON::PP ();
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once', 'redefine';
HabitatEngine::InitLinkPatterns();
*HabitatEngine::CSRFCheckOrDie = sub { 1 };
$HabitatEngine::UseActivation = 0;
$HabitatEngine::UseCaptcha    = 0;
$HabitatEngine::LangID        = '';
$HabitatEngine::AdminPass     = 'adm1nTok';
$HabitatEngine::EditPass      = 'edTokA edTokB';

is( $HabitatEngine::RegistrationPermission, 'editor', 'default: editor-level registration' );

sub run_action {
    my ( $sub, %form ) = @_;
    $HabitatEngine::q = CGI->new( \%form );
    my $out = '';
    my $exited;
    {
        local *STDOUT;
        open( STDOUT, '>', \$out ) or die;
        eval { $sub->(); 1 } or do { $exited = ( $@ eq "EXIT\n" ); die $@ unless $exited };
        close STDOUT;
    }
    return ( $out, $exited ? 1 : 0 );
}
sub as_anonymous { %HabitatEngine::UserData = (); $HabitatEngine::UserID = 111; }
sub users { scalar $dbh->selectrow_array("SELECT COUNT(*) FROM users") }
my $seq = 0;
sub reg {
    my (%extra) = @_;
    as_anonymous();
    $dbh->do("DELETE FROM login_attempts") unless ( delete $extra{keep_throttle} );
    my $name = delete $extra{name} // ( 'User' . ++$seq );
    my @r    = run_action(
        \&HabitatEngine::DoUpdatePrefs,
        p_username      => $name,
        p_password      => 'secretpw1',
        p_email         => lc($name) . '@example.org',
        p_reg_firstname => 'F',
        p_reg_lastname  => 'L',
        p_reg_inst      => 'U',
        p_adminpw       => '*',    # the form's untouched admin-token field
        %extra
    );
    return ( @r, $name );
}
sub row_of { $dbh->selectrow_array( "SELECT id FROM users WHERE name=?", undef, $_[0] ) }

# Rights of a stored account, as the engine computes them after login.
sub clearance_of {
    my ($name) = @_;
    my $id = row_of($name) or return;
    %HabitatEngine::UserData = ();
    $HabitatEngine::UserID   = $id;
    HabitatEngine::LoadUserDataDB($id);
    $HabitatEngine::q = CGI->new( {} );
    return HabitatEngine::UserPermission();
}

sub refused {
    my ( $label, $re, %f ) = @_;
    my $before = users();
    my ( $out, $exited, $name ) = reg(%f);
    ok( $exited, "$label: registration aborted" );
    like( $out, $re, "  ... with the token error" );
    is( users(), $before, "  ... and no user row written" );
}

sub accepted {
    my ( $label, %f ) = @_;
    my ( $out, $exited, $name ) = reg(%f);
    ok( !$exited, "$label: registration succeeds" ) or diag($out);
    ok( row_of($name), "  ... user row written" );
    is( clearance_of($name), 1, "  ... as an ordinary user (no editor/admin rights from the token)" );
}

my $ed_err  = qr/requires a valid editor or administrator token/;
my $adm_err = qr/requires a valid administrator token/;

# ---------------- 'editor' (default) ----------------
as_anonymous();
{
    my ($form) = run_action( \&HabitatEngine::DoEditPrefs );
    like( $form, qr/Registration token/,   'editor level: sign-up form has a registration token field' );
    like( $form, qr/name="p_regtoken"/,    '  ... named p_regtoken' );
    like( $form, qr/editor or administrator/, '  ... saying whose token is needed' );
}
refused( 'editor level, no token',          $ed_err );
refused( 'editor level, wrong token',       $ed_err, p_regtoken => 'nope' );
refused( 'editor level, prefix of a token', $ed_err, p_regtoken => 'edTok' );
refused( 'editor level, tokens joined',     $ed_err, p_regtoken => 'edTokA edTokB' );
refused( 'editor level, token in the admin-token field only', $ed_err, p_adminpw => 'edTokA' );
accepted( 'editor level, editor token',          p_regtoken => 'edTokB' );
accepted( 'editor level, admin token',           p_regtoken => 'adm1nTok' );

# The separate admin-token field still works as before: an editor token
# typed there (in addition to the registration token) grants editor.
{
    my ( $out, $exited, $name ) = reg( p_regtoken => 'edTokA', p_adminpw => 'edTokA' );
    ok( !$exited, 'registration token + admin-token field: succeeds' ) or diag($out);
    is( clearance_of($name), 50, '  ... editor rights come only from the admin-token field' );
}

# ---------------- 'admin' ----------------
{
    local $HabitatEngine::RegistrationPermission = 'admin';
    as_anonymous();
    my ($form) = run_action( \&HabitatEngine::DoEditPrefs );
    like( $form, qr/token from the wiki administrator/, 'admin level: form asks for the administrator token' );
    refused( 'admin level, no token',     $adm_err );
    refused( 'admin level, editor token', $adm_err, p_regtoken => 'edTokA' );
    accepted( 'admin level, admin token', p_regtoken => 'adm1nTok' );
}

# Unknown value counts as 'admin'.
{
    local $HabitatEngine::RegistrationPermission = 'nobody';
    refused( 'unknown level, editor token', $adm_err, p_regtoken => 'edTokA' );
}

# ---------------- 'user' ----------------
{
    local $HabitatEngine::RegistrationPermission = 'user';
    as_anonymous();
    my ($form) = run_action( \&HabitatEngine::DoEditPrefs );
    unlike( $form, qr/Registration token/, 'user level: no registration token field' );
    accepted('user level, no token');
}

# ---------------- no tokens configured ----------------
{
    local $HabitatEngine::AdminPass = '';
    local $HabitatEngine::EditPass  = '';
    refused( 'editor level, no tokens configured', $ed_err, p_regtoken => 'anything' );
}
{
    local $HabitatEngine::EditPass = '';
    accepted( 'editor level, only $AdminPass set, admin token', p_regtoken => 'adm1nTok' );
}

# ---------------- throttle ----------------
my $have = users();
reg( p_regtoken => "guess$_", keep_throttle => ( $_ > 1 ) ) for 1 .. $HabitatEngine::LoginMaxAttempts;
{
    my ( $out, $exited ) = reg( p_regtoken => 'edTokA', keep_throttle => 1 );
    ok( $exited, 'after too many bad tokens the IP is throttled' );
    like( $out, qr/Too many requests/, '  ... with the throttle message' );
    is( users(), $have, '  ... and no user row written' );
}
{
    local $HabitatEngine::Now = $HabitatEngine::Now + $HabitatEngine::LoginThrottleWindow + 1;
    my ( $out, $exited ) = reg( p_regtoken => 'edTokA', keep_throttle => 1 );
    ok( !$exited, 'after the throttle window a valid token works again' ) or diag($out);
}

# ---------------- existing users ----------------
{
    my ($name) = $dbh->selectrow_array("SELECT name FROM users ORDER BY id LIMIT 1");
    my $id = row_of($name);
    %HabitatEngine::UserData = ();
    $HabitatEngine::UserID   = $id;
    HabitatEngine::LoadUserDataDB($id);
    my ($form) = run_action( \&HabitatEngine::DoEditPrefs );
    unlike( $form, qr/Registration token/, 'existing user: prefs page has no registration token field' );
    my ( $out, $exited ) = run_action(
        \&HabitatEngine::DoUpdatePrefs,
        p_username => $name,
        p_password => 'secretpw1',
        p_email    => lc($name) . '@example.org',
        p_reg_inst => 'U2',
        p_adminpw  => '*',
    );
    ok( !$exited, 'existing user saves prefs without a registration token' ) or diag($out);
}

done_testing;
