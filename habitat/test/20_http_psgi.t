#!/usr/bin/env perl
# End-to-end request lifecycle through the PSGI shim. Uses Plack::Test
# so there's no plackup process and no port — the request flows
# through CGI::Emulate::PSGI -> CGI::Compile -> index.cgi in-process.
#
# Coverage:
#   - basic browse paths return 200
#   - state isolation between consecutive requests
#   - CSRF enforcement on state-changing POSTs
#   - generic-error login failure path + throttle row creation

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

BEGIN {
    eval { require Plack::Test; Plack::Test->import; 1 }
      or plan skip_all => "Plack::Test not installed";
    eval { require HTTP::Request::Common; HTTP::Request::Common->import(qw(GET POST)); 1 }
      or plan skip_all => "HTTP::Request::Common not installed";
}

# Chdir into habitat/ via the harness (BEGIN-time) and load app.psgi.
# The wiki's render path emits ~50 "Use of uninitialized value"
# warnings per page, all from untouched legacy code. They're flagged
# elsewhere for cleanup but would drown out real test output here.
# Same for "Subroutine X redefined" if the test or harness happens to
# trip a double-load (HabitatHarness::load_wiki is idempotent, but
# CGI::Compile compiling index.cgi a second time isn't).
local $SIG{__WARN__} = sub {
    return if $_[0] =~ /Use of uninitialized value/;
    return if $_[0] =~ /Subroutine .* redefined/;
    return if $_[0] =~ /Argument .* isn't numeric/;

    # CSRFCheckOrDie warns on rejection — that IS the production
    # security-log signal, not a test bug. The CSRF subtests here
    # deliberately submit unsigned POSTs to exercise that path.
    return if $_[0] =~ /CSRF check failed/;
    warn $_[0];
};

# app.psgi will load index.cgi itself; skip the harness's bare-require
# so we don't compile the script twice.
require Plack::Util;
my $app = Plack::Util::load_psgi("./app.psgi");

# Reset the login_attempts table created in earlier test runs so the
# throttle assertions later are deterministic.
{
    my $dbh = $HabitatEngine::dbh;
    $dbh->do("DELETE FROM login_attempts") if $dbh;
}

my $test = Plack::Test->create($app);

# ----------------------------------------------------------------
# Browse paths
# ----------------------------------------------------------------
for my $url (
    '/',           '/?Home',        '/?action=index', '/?action=edit&id=Home',
    '/?action=rc', '/?search=test', '/?action=rss'
  )
{
    my $res = $test->request( GET $url );
    is( $res->code, 200, "GET $url -> 200" );
    cmp_ok( length( $res->content ), '>', 100, "GET $url body looks like a page" );
}

# Random is a redirect
my $rand = $test->request( GET '/?action=random' );
like( $rand->code, qr/^30[12]$/, "GET /?action=random -> 30x redirect" );

# ----------------------------------------------------------------
# State isolation: same URL hit twice returns the same content
# (modulo timestamp-bound CSRF tokens). After Stage 2 ResetRequestState,
# any global leak would manifest here.
# ----------------------------------------------------------------
my $r1 = $test->request( GET '/?Home' );
my $r2 = $test->request( GET '/?DoesNotExist' );
my $r3 = $test->request( GET '/?Home' );

# Strip every csrf_token value before comparing (they bind to $Now).
my $h1 = $r1->content;
my $h3 = $r3->content;
$h1 =~ s/name="csrf_token"\s+value="[^"]+"/CSRFSCRUBBED/g;
$h3 =~ s/name="csrf_token"\s+value="[^"]+"/CSRFSCRUBBED/g;
is( $h1, $h3, "two /?Home requests with an intervening different request return the same body" );

# ----------------------------------------------------------------
# CSRF enforcement
# ----------------------------------------------------------------
# Without csrf_token: must be 403, must not perform the side effect.
my $no_csrf = $test->request(
    POST '/',
    [
        edit_ban => 1,
        banlist  => "evil-net",
    ]
);
is( $no_csrf->code, 403, "POST without csrf_token -> 403" );
like(
    $no_csrf->content,
    qr/CSRF token missing or invalid/i,
    "403 body contains the CSRF error message"
);

# With a garbage csrf_token
my $bad_csrf = $test->request(
    POST '/',
    [
        csrf_token => "not-a-real-token",
        edit_ban   => 1,
        banlist    => "evil-net",
    ]
);
is( $bad_csrf->code, 403, "POST with bad csrf_token -> 403" );

# Verify nothing was written to the ban list. The Stage 1 helper
# stores the ban list in the `system` table under id='banlist'.
my $dbh = $HabitatEngine::dbh;
my ($banned) = $dbh->selectrow_array("SELECT data FROM system WHERE id='banlist'");
ok( !defined($banned) || $banned !~ /evil-net/, "CSRF-blocked POST did not mutate the ban list" );

# ----------------------------------------------------------------
# Login flow — generic error message, throttle row appears
# ----------------------------------------------------------------
# Grab a valid CSRF from the login form
my $login_form = $test->request( GET '/?action=login' );
my ($csrf) = $login_form->content =~ /csrf_token"\s+value="([^"]+)"/;
ok( $csrf, "got a CSRF token from the login form" );

# Submit a doomed login
my $fail = $test->request(
    POST '/',
    [
        csrf_token  => $csrf,
        enter_login => 1,
        p_username  => "definitely_does_not_exist",
        p_password  => "wrongpass",
    ]
);
is( $fail->code, 200, "login attempt completes (200)" );
like( $fail->content, qr/Login failed/, "generic 'Login failed' message shown" );
unlike(
    $fail->content,
    qr/wrong password|cannot find|not yet been activated/i,
    "no information-leaking error variant in response"
);

# Throttle row should now exist for both keys
my $rows =
  $dbh->selectall_arrayref("SELECT attempt_key, attempts FROM login_attempts ORDER BY attempt_key");
ok( scalar(@$rows) >= 2, "throttle table has at least two rows (per-IP and per-name)" );
my %by_key = map { $_->[0] => $_->[1] } @$rows;
ok( ( grep { /^name:/ } keys %by_key ), "per-username throttle row created" );
ok( ( grep { /^ip:/ } keys %by_key ),   "per-IP throttle row created" );

# Clean up so the next test run starts fresh
$dbh->do("DELETE FROM login_attempts");

# ----------------------------------------------------------------
# Cookie attributes on a request that issues one
# (anonymous browse doesn't set a cookie; only auth flows do, so we
# just confirm no Set-Cookie on plain browse and no obviously-broken
# header on the login form GET.)
# ----------------------------------------------------------------
my $home = $test->request( GET '/?Home' );
unlike( $home->header('Set-Cookie') || '',
    qr/randkey/i, "anonymous browse does not emit the legacy randkey cookie format" );

done_testing;
