#!/usr/bin/env perl
# "Forgot password?" flow:
#   - same answer whether or not the account exists; mail only for real
#     accounts with a valid address, at most one per $PasswordResetMailGap
#   - the emailed link is an HMAC over uid, expiry, password hash and
#     param: tampered, expired or already-used links are refused
#   - a reset sets a bcrypt hash and unlocks an account imported locked
#     (param "R...", empty password), after which login works
#   - captcha and per-IP throttle on the request form

use strict;
use warnings;

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
$HabitatEngine::UseCaptcha       = 0;
$HabitatEngine::UsePasswordReset = 1;
$HabitatEngine::LangID           = '';
$HabitatEngine::SiteBase         = 'https://wiki.example.org/index.cgi';
$HabitatEngine::SiteName         = 'TestWiki';
$HabitatEngine::EmailFrom        = 'noreply@example.org';
$ENV{REMOTE_ADDR}                = '192.0.2.10';

# Fake mailer: records each message in its own file.
my $dir  = tempdir( "fakemail-XXXX", DIR => $Bin, CLEANUP => 1 );
my $fake = "$dir/fakesendmail";
open( my $fh, '>', $fake ) or die;
print $fh "#!/bin/sh\nn=\$(ls '$dir' | grep -c '^msg') ; /bin/cat > '$dir/msg'\$n\n";
close $fh;
chmod 0755, $fake;
$HabitatEngine::SendMail = $fake;
sub mails { [ map { local $/; open my $m, '<', $_ or die; scalar <$m> } sort glob("$dir/msg*") ] }
sub clear_mails { unlink glob("$dir/msg*") }

sub run_action {
    my ( $sub, %form ) = @_;
    $HabitatEngine::q = CGI->new( \%form );
    %HabitatEngine::UserData = ();
    $HabitatEngine::UserID   = 111;
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

sub user { $dbh->selectrow_hashref( "SELECT * FROM users WHERE id=?", undef, $_[0] ) }
sub link_of {
    my ($mail) = @_;
    my ($l) = $mail =~ m{(https://wiki\.example\.org/index\.cgi\?action=resetpw\S+)} or return;
    my %p = map { split /=/, $_, 2 } split /&/, ( split /\?/, $l, 2 )[1];
    return \%p;
}

# A locked imported account (no usable password) and a normal one.
$dbh->do( "INSERT INTO users (id,name,pass,email,param) VALUES (?,?,?,?,?)",
    undef, 1002, 'Carol', '', 'carol@example.org', 'R' . ( 'a' x 30 ) );
$dbh->do( "INSERT INTO users (id,name,pass,email,param) VALUES (?,?,?,?,?)",
    undef, 1003, 'Dave', HabitatEngine::HashPassword('oldpassword'), 'dave@example.org', '' );
$dbh->do( "INSERT INTO users (id,name,pass,email,param) VALUES (?,?,?,?,?)",
    undef, 1004, 'NoMail', '', 'not-an-address', 'R' . ( 'b' x 30 ) );

# ----------------------------------------------------------------
# Login page links to the form; the form renders.
# ----------------------------------------------------------------
{
    my ($out) = run_action( \&HabitatEngine::DoEnterLogin );
    like( $out, qr/action=forgotpw/, "login page links to the reset form" );
    ($out) = run_action( \&HabitatEngine::DoForgotPasswordForm );
    like( $out, qr/name="forgot_pw"/, "reset request form renders" );
    local $HabitatEngine::UsePasswordReset = 0;
    ($out) = run_action( \&HabitatEngine::DoEnterLogin );
    unlike( $out, qr/action=forgotpw/, "no link when \$UsePasswordReset is off" );
}

# ----------------------------------------------------------------
# Locked account cannot log in before the reset.
# ----------------------------------------------------------------
{
    my ($out) = run_action( \&HabitatEngine::DoLogin, p_username => 'Carol', p_password => 'anything' );
    like( $out, qr/Login failed/, "locked imported account cannot log in" );
}

# ----------------------------------------------------------------
# Same answer for unknown, unmailable and real accounts; mail only for real.
# ----------------------------------------------------------------
my ( $unknown, $nomail, $real );
( $unknown ) = run_action( \&HabitatEngine::DoForgotPassword, forgot_pw => 1, p_account => 'nobody' );
( $nomail )  = run_action( \&HabitatEngine::DoForgotPassword, forgot_pw => 1, p_account => 'NoMail' );
is( scalar @{ mails() }, 0, "no mail for an unknown account or an invalid address" );
$HabitatEngine::dbh->do("DELETE FROM login_attempts");    # reset per-IP counter
( $real ) = run_action( \&HabitatEngine::DoForgotPassword, forgot_pw => 1, p_account => 'carol' );
s/<[^>]+>//g for ( $unknown, $real );
my ($msg_u) = $unknown =~ /(If that user name.*?24 hours\.)/s;
my ($msg_r) = $real =~ /(If that user name.*?24 hours\.)/s;
ok( defined $msg_u, "generic confirmation shown" );
is( $msg_r, $msg_u, "identical answer for a real account (no account enumeration)" );
my $m = mails();
is( scalar @$m, 1, "one mail for the real account (name lookup is case-insensitive)" );
like( $m->[0], qr/^To: carol\@example\.org$/m, "  sent to the address on file" );
like( $m->[0], qr/^From: noreply\@example\.org$/m, "  from \$EmailFrom" );
my $link = link_of( $m->[0] );
ok( $link && $link->{uid} == 1002, "  contains a reset link for the account" );
is( $link->{exp} - $HabitatEngine::Now, 86400, "  link expires after \$PasswordResetTTL" );

# Second request inside the mail gap: same answer, no second mail.
run_action( \&HabitatEngine::DoForgotPassword, forgot_pw => 1, p_account => 'carol@EXAMPLE.org' );
is( scalar @{ mails() }, 1, "no second mail within \$PasswordResetMailGap (lookup by email)" );

# ----------------------------------------------------------------
# Link validation.
# ----------------------------------------------------------------
{
    my ($out) = run_action( \&HabitatEngine::DoResetPasswordForm, action => 'resetpw', %$link );
    like( $out, qr/name="p_newpass"/, "valid link shows the new-password form" );
    like( $out, qr/Carol/,            "  naming the account" );

    my %bad = ( %$link, sig => ( $link->{sig} =~ s/^(.)/$1 eq 'a' ? 'b' : 'a'/er ) );
    ($out) = run_action( \&HabitatEngine::DoResetPasswordForm, %bad );
    like( $out, qr/invalid, has expired/, "tampered signature refused" );

    ($out) = run_action( \&HabitatEngine::DoResetPasswordForm, %$link, uid => 1003 );
    like( $out, qr/invalid, has expired/, "link cannot be moved to another account" );

    local $HabitatEngine::Now = $link->{exp} + 1;
    ($out) = run_action( \&HabitatEngine::DoResetPasswordForm, %$link );
    like( $out, qr/invalid, has expired/, "expired link refused" );
}

# ----------------------------------------------------------------
# Setting the password.
# ----------------------------------------------------------------
{
    my ( $out, $exited ) =
      run_action( \&HabitatEngine::DoResetPassword, reset_pw => 1, %$link, p_newpass => 'short', p_newpass2 => 'short' );
    ok( $exited, "password shorter than 8 characters rejected" );
    ( $out, $exited ) = run_action( \&HabitatEngine::DoResetPassword,
        reset_pw => 1, %$link, p_newpass => 'longenough1', p_newpass2 => 'longenough2' );
    ok( $exited, "mismatched passwords rejected" );
    is( user(1002)->{param}, 'R' . ( 'a' x 30 ), "  account still locked after rejected attempts" );

    ($out) = run_action( \&HabitatEngine::DoResetPassword,
        reset_pw => 1, %$link, p_newpass => 'new-secret-9', p_newpass2 => 'new-secret-9' );
    like( $out, qr/password has been changed/, "reset succeeds" );
    my $u = user(1002);
    like( $u->{pass}, qr/^\$2[aby]\$/, "  new password stored as bcrypt" );
    is( $u->{param}, '', "  locked account unlocked" );

    ($out) = run_action( \&HabitatEngine::DoResetPasswordForm, %$link );
    like( $out, qr/invalid, has expired/, "link cannot be used twice" );
    ($out) = run_action( \&HabitatEngine::DoResetPassword,
        reset_pw => 1, %$link, p_newpass => 'other-secret-9', p_newpass2 => 'other-secret-9' );
    like( $out, qr/invalid, has expired/, "  not even by posting the form again" );

    ($out) = run_action( \&HabitatEngine::DoLogin, p_username => 'Carol', p_password => 'new-secret-9' );
    like( $out, qr/Login for user Carol complete/, "login works with the new password" );
}

# ----------------------------------------------------------------
# A normal account: the link dies once the user changes the password.
# ----------------------------------------------------------------
{
    clear_mails();
    $HabitatEngine::dbh->do("DELETE FROM login_attempts");
    run_action( \&HabitatEngine::DoForgotPassword, forgot_pw => 1, p_account => 'Dave' );
    my $l = link_of( mails()->[0] );
    ok( $l, "reset link mailed for an active account" );
    $dbh->do( "UPDATE users SET pass=? WHERE id=1003", undef, HabitatEngine::HashPassword('changed-meanwhile') );
    my ($out) = run_action( \&HabitatEngine::DoResetPasswordForm, %$l );
    like( $out, qr/invalid, has expired/, "link invalid after the password changed some other way" );
}

# ----------------------------------------------------------------
# Captcha and per-IP throttle on the request form.
# ----------------------------------------------------------------
{
    clear_mails();
    $HabitatEngine::dbh->do("DELETE FROM login_attempts");
    local $HabitatEngine::UseCaptcha = 1;
    my ( $out, $exited ) = run_action( \&HabitatEngine::DoForgotPassword,
        forgot_pw => 1, p_account => 'Dave', captchaans => '1', captchaopt => 'bogus' );
    ok( $exited, "wrong captcha rejected" );
    is( scalar @{ mails() }, 0, "  no mail sent" );
}
{
    $HabitatEngine::dbh->do("DELETE FROM login_attempts");
    my $blocked = 0;
    for ( 1 .. $HabitatEngine::LoginMaxAttempts + 1 ) {
        my ( $out, $exited ) = run_action( \&HabitatEngine::DoForgotPassword, forgot_pw => 1, p_account => 'nobody' );
        $blocked++ if ( $exited && $out =~ /Too many requests/ );
    }
    is( $blocked, 1, "requests from one IP throttled after \$LoginMaxAttempts" );
}

done_testing;
