#!/usr/bin/env perl
# Registration profile + account hardening (ported from the NeuroJSON
# production wiki, with its bugs fixed):
#   - first/last name + institute required to register; interests
#     optional; stored in users.prefs as fn/sn/inst/area
#   - names fixed once set, and an existing user can still save prefs
#     without re-sending them (the production version rejected that)
#   - stored names are HTML-quoted on the preferences page
#   - user names unique case-insensitively; login lookup is a
#     case-insensitive exact match (no LIKE wildcards)
#   - email addresses validated; SendEmail never goes through a shell
#     and refuses addresses that could inject headers or options

use strict;
use warnings;

# Turn the engine's exit() calls (ErrMsg/PrintMsg with exitflag) into
# a catchable die. Must be in place before index.cgi is compiled.
BEGIN { *CORE::GLOBAL::exit = sub { die "EXIT\n" }; }

use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use File::Temp qw(tempdir);
use CGI;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once', 'redefine';
HabitatEngine::InitLinkPatterns();
*HabitatEngine::CSRFCheckOrDie = sub { 1 };
$HabitatEngine::UseActivation = 0;
$HabitatEngine::AdminPass     = 'adm1nPass';
$HabitatEngine::LangID        = '';

# Run a prefs action with the given form fields; returns (output, exited).
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

sub as_user {
    my ($id) = @_;
    $HabitatEngine::UserID = $id;
    HabitatEngine::LoadUserDataDB($id);
}

sub prefs_of {
    my ($name) = @_;
    my ($json) = $dbh->selectrow_array( "SELECT prefs FROM users WHERE name=?", undef, $name );
    return defined $json ? JSON::PP::decode_json($json) : undef;
}

my %reg = (
    p_username      => 'Alice',
    p_password      => 'secretpw1',
    p_password2     => 'secretpw1',
    p_email         => 'alice@example.org',
    p_reg_firstname => 'Alice',
    p_reg_lastname  => 'Liddell',
    p_reg_inst      => 'Wonderland U',
    p_reg_research  => 'rabbit holes',
);

# ----------------------------------------------------------------
# Registration requires first name, last name and institute.
# ----------------------------------------------------------------
for my $missing (qw(p_reg_firstname p_reg_lastname p_reg_inst)) {
    as_anonymous();
    my %f = %reg;
    delete $f{$missing};
    my ( $out, $exited ) = run_action( \&HabitatEngine::DoUpdatePrefs, %f );
    ok( $exited, "registration without $missing is rejected" );
    like( $out, qr/first name, last name and institute/, "  ... with the profile error message" );
}
is( $dbh->selectrow_array("SELECT COUNT(*) FROM users"), 0, "no account created by rejected registrations" );

# ----------------------------------------------------------------
# Complete registration stores the profile under the legacy keys.
# ----------------------------------------------------------------
as_anonymous();
{
    my ( $out, $exited ) = run_action( \&HabitatEngine::DoUpdatePrefs, %reg );
    ok( !$exited, "complete registration succeeds" ) or diag($out);
    like( $out, qr/User settings updated\./, "success message ported" );
}
my $p = prefs_of('Alice');
is_deeply(
    [ @{$p}{qw(fn sn inst area)} ],
    [ 'Alice', 'Liddell', 'Wonderland U', 'rabbit holes' ],
    "profile stored in users.prefs as fn/sn/inst/area"
);
my ($alice_id) = $dbh->selectrow_array("SELECT id FROM users WHERE name='Alice'");

# ----------------------------------------------------------------
# Existing user: prefs page shows names as fixed text, and saving
# without re-sending them keeps them (production rejected this save).
# ----------------------------------------------------------------
as_user($alice_id);
{
    my ( $out, $exited ) = run_action( \&HabitatEngine::DoEditPrefs );
    unlike( $out, qr/name="p_reg_firstname"/, "prefs page: first name no longer editable once set" );
    like( $out, qr/name="p_reg_inst"[^>]*value="Wonderland U"/, "prefs page: institute prefilled" );
    like( $out, qr/Administrator token/, "prefs page: 'Administrator token' label ported" );
}
as_user($alice_id);
{
    my ( $out, $exited ) = run_action(
        \&HabitatEngine::DoUpdatePrefs,
        p_username     => 'Alice',
        p_password     => 'secretpw1',
        p_email        => 'alice@example.org',
        p_reg_inst     => 'Looking-Glass Institute',
        p_reg_research => '',
        p_adminpw      => '*',
    );
    ok( !$exited, "existing user saves prefs without re-sending names" ) or diag($out);
}
$p = prefs_of('Alice');
is( $p->{fn},   'Alice',                   "  first name kept" );
is( $p->{sn},   'Liddell',                 "  last name kept" );
is( $p->{inst}, 'Looking-Glass Institute', "  institute updated" );
is( $p->{area}, '',                        "  interests cleared" );

# ----------------------------------------------------------------
# Stored names are quoted on the prefs page (production printed raw).
# ----------------------------------------------------------------
$dbh->do( "UPDATE users SET prefs=? WHERE id=?",
    undef, JSON::PP::encode_json( { fn => '<script>x()</script>', sn => 'L', inst => 'I' } ), $alice_id );
as_user($alice_id);
{
    my ($out) = run_action( \&HabitatEngine::DoEditPrefs );
    unlike( $out, qr/<script>x\(\)/, "stored first name is not emitted as markup" );
    like( $out, qr/&lt;script&gt;x\(\)/, "  ... it is HTML-quoted" );
}

# ----------------------------------------------------------------
# User names are unique case-insensitively; login lookup is a
# case-insensitive exact match.
# ----------------------------------------------------------------
as_anonymous();
{
    my ( $out, $exited ) =
      run_action( \&HabitatEngine::DoUpdatePrefs, %reg, p_username => 'alice', p_email => 'other@example.org' );
    ok( $exited, "registering 'alice' when 'Alice' exists is rejected" );
    like( $out, qr/has already been taken/, "  ... as already taken" );
}
is( $dbh->selectrow_array("SELECT COUNT(*) FROM users"), 1, "  no second account created" );
{
    %HabitatEngine::UserData = ();
    HabitatEngine::LoadUserDataDB( 0, 'aLiCe' );
    is( $HabitatEngine::UserData{username}, 'Alice', "login lookup is case-insensitive" );
    %HabitatEngine::UserData = ();
    $HabitatEngine::UserID   = 1001;
    HabitatEngine::LoadUserDataDB( 0, 'Al%' );
    ok( !$HabitatEngine::UserData{username}, "login lookup treats % literally (no LIKE wildcard)" );
}

# ----------------------------------------------------------------
# Email validation and a shell-free mailer.
# ----------------------------------------------------------------
ok( HabitatEngine::ValidEmail('alice@example.org'),        "ValidEmail: plain address" );
ok( HabitatEngine::ValidEmail('a.b+tag@sub.example.co'),   "ValidEmail: dots, plus, subdomain" );
ok( !HabitatEngine::ValidEmail($_), "ValidEmail rejects: " . ( $_ =~ s/\n/\\n/gr ) )
  for (
    'x"; touch /tmp/pwned; "@a.b',    # production's shell injection
    "a\@b.org\nBcc: victim\@x.org",   # header injection
    '-oQ/tmp/x@a.b',                  # option injection
    "o'brien\@a.b", 'a b@c.d', 'a@b', '@b.org', 'a@-b.org',
  );

as_anonymous();
{
    my ( $out, $exited ) =
      run_action( \&HabitatEngine::DoUpdatePrefs, %reg, p_username => 'Bob', p_email => 'x"; id; "@a.b' );
    ok( $exited, "registration with a shell-metacharacter email is rejected" );
    like( $out, qr/valid email address/, "  ... with the email error message" );
}

# SendEmail runs the mailer without a shell, recipient as one argument.
{
    # Not under /tmp: shared hosts often mount it noexec.
    my $dir = tempdir( "fakemail-XXXX", DIR => $Bin, CLEANUP => 1 );
    my $log = "$dir/argv";
    my $fake = "$dir/fakesendmail";
    open( my $fh, '>', $fake ) or die;
    # Absolute /bin/cat: the engine sets $ENV{PATH} = "/usr/bin/".
    print $fh "#!/bin/sh\nfor a in \"\$\@\"; do printf '%s\\n' \"\$a\"; done > '$log'\n/bin/cat >> '$log'\n";
    close $fh;
    chmod 0755, $fake;
    local $HabitatEngine::SendMail = $fake;

    HabitatEngine::SendEmail( 'alice@example.org', 'wiki@x.org', 'alice@example.org',
        "Hello\nBcc: victim\@x.org", "body\n" );
    open( my $in, '<', $log ) or die "fake sendmail did not run";
    my @lines = <$in>;
    close $in;
    is( join( '', @lines[ 0, 1 ] ), "-oi\nalice\@example.org\n", "sendmail argv: -oi <recipient>" );
    my $sent = join( '', @lines );
    like( $sent, qr/^Subject: Hello Bcc: victim\@x\.org$/m, "newline in subject cannot add a header" );
    unlike( $sent, qr/^Bcc:/m, "  ... no Bcc header" );

    unlink $log;
    HabitatEngine::SendEmail( 'x"; touch ' . "$dir/pwned" . '; "@a.b', 'w@x.org', 'w@x.org', 's', 'b' );
    ok( !-e $log,          "invalid recipient: mailer not invoked" );
    ok( !-e "$dir/pwned", "invalid recipient: no command executed" );
}

done_testing;
