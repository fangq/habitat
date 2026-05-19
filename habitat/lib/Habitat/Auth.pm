package Habitat::Auth;
#
# Stage 1 authentication primitives, extracted into a module in Stage 5.
# Covers:
#
#   - CSPRNG: RandomBytes, RandomHex
#   - Site secret bootstrap: GetSiteSecret (auto-creates $DataDir/secret)
#   - HMAC + constant-time compare: Hmac, ConstantEq
#   - Signed session cookies: SignSessionToken, VerifySessionToken,
#     BuildSessionCookie, IsRequestSecure
#   - CSRF tokens: GenCSRFToken, VerifyCSRFToken, CSRFCheckOrDie
#   - HMAC captcha: PrintCaptcha, VerifyCaptcha
#   - Login throttle: EnsureLoginThrottleTable, LoginThrottleBlocked,
#     LoginThrottleHit, LoginThrottleClear
#   - Bcrypt passwords + legacy crypt() migration: HashPassword,
#     VerifyPassword, IsLegacyPasswordHash, UpgradePasswordHashDB
#
# All cross-module state lives in the HabitatEngine package (the main
# script). This module reads/writes those globals through fully-
# qualified names — no copy, so PSGI reconnects / config reloads
# propagate automatically. The same wiring trick as Habitat::Store.

use strict;
use warnings;
use Exporter qw(import);
use Digest::SHA ();
use Crypt::Bcrypt qw(bcrypt bcrypt_check);
use Habitat::Store ();

our @EXPORT_OK = qw(
  RandomBytes RandomHex GetSiteSecret Hmac ConstantEq
  SignSessionToken VerifySessionToken BuildSessionCookie IsRequestSecure
  GenCSRFToken VerifyCSRFToken CSRFCheckOrDie
  PrintCaptcha VerifyCaptcha
  EnsureLoginThrottleTable LoginThrottleBlocked LoginThrottleHit LoginThrottleClear
  HashPassword VerifyPassword IsLegacyPasswordHash UpgradePasswordHashDB
);

# ----------------------------------------------------------------
# CSPRNG + secret bootstrap
# ----------------------------------------------------------------

sub RandomBytes {
    my ($n) = @_;
    $n = 32 if ( !defined($n) || $n <= 0 );
    my $bytes;
    eval { require Crypt::URandom; $bytes = Crypt::URandom::urandom($n); };
    if ( !defined($bytes) || length($bytes) != $n ) {
        if ( open( my $fh, '<', '/dev/urandom' ) ) {
            binmode $fh;
            my $got = read( $fh, $bytes, $n );
            close $fh;
            die("RandomBytes: short read from /dev/urandom")
              if ( !defined($got) || $got != $n );
        } else {
            die("RandomBytes: no CSPRNG available (install Crypt::URandom or provide /dev/urandom)"
            );
        }
    }
    return $bytes;
}

sub RandomHex {
    my ($n) = @_;
    return unpack( 'H*', RandomBytes($n) );
}

sub GetSiteSecret {
    no warnings 'once';
    return $HabitatEngine::SiteSecret
      if ( defined($HabitatEngine::SiteSecret)
        && length($HabitatEngine::SiteSecret) >= 32 );

    my $path = $HabitatEngine::SecretFile;
    if ( defined($path) && -f $path ) {
        if ( open( my $fh, '<', $path ) ) {
            binmode $fh;
            local $/;
            $HabitatEngine::SiteSecret = <$fh>;
            close $fh;
            return $HabitatEngine::SiteSecret
              if ( defined($HabitatEngine::SiteSecret)
                && length($HabitatEngine::SiteSecret) >= 32 );
        }
    }
    $HabitatEngine::SiteSecret = RandomBytes(64);
    my $tmp = "$path.tmp.$$";
    if ( open( my $fh, '>', $tmp ) ) {
        binmode $fh;
        print $fh $HabitatEngine::SiteSecret;
        close $fh;
        chmod 0600, $tmp;
        rename( $tmp, $path ) or die("GetSiteSecret: rename failed: $!");
    } else {
        die("GetSiteSecret: cannot write $path: $!");
    }
    return $HabitatEngine::SiteSecret;
}

sub Hmac {
    my ($msg) = @_;
    return Digest::SHA::hmac_sha256_hex( $msg, GetSiteSecret() );
}

sub ConstantEq {
    my ( $a, $b ) = @_;
    return 0 if ( !defined($a) || !defined($b) || length($a) != length($b) );
    my $diff = 0;
    for ( my $i = 0 ; $i < length($a) ; $i++ ) {
        $diff |= ord( substr( $a, $i, 1 ) ) ^ ord( substr( $b, $i, 1 ) );
    }
    return $diff == 0 ? 1 : 0;
}

# ----------------------------------------------------------------
# Session cookies
# ----------------------------------------------------------------

sub SignSessionToken {
    my ( $uid, $ttl ) = @_;
    return '' if ( !defined($uid) || $uid !~ /\A\d+\z/ || $uid <= 0 );
    $ttl = 30 * 86400 if ( !defined($ttl) || $ttl <= 0 );
    no warnings 'once';
    my $exp = $HabitatEngine::Now + $ttl;
    my $sig = Hmac("$uid|$exp");
    return "$uid|$exp|$sig";
}

sub VerifySessionToken {
    my ($tok) = @_;
    return 0 if ( !defined($tok) || ref($tok) );
    return 0 unless ( $tok =~ /\A(\d+)\|(\d+)\|([0-9a-f]+)\z/ );
    my ( $uid, $exp, $sig ) = ( $1, $2, $3 );
    no warnings 'once';
    return 0 if ( $exp < $HabitatEngine::Now );
    return 0 unless ConstantEq( $sig, Hmac("$uid|$exp") );
    return $uid;
}

sub IsRequestSecure {
    return 1 if ( defined $ENV{HTTPS}       && $ENV{HTTPS} =~ /^on$/i );
    return 1 if ( defined $ENV{SERVER_PORT} && $ENV{SERVER_PORT} == 443 );
    no warnings 'once';
    my $tp = $HabitatEngine::TrustedProxies;
    if ( defined($tp) && $tp ne '' && defined $ENV{HTTP_X_FORWARDED_PROTO} ) {
        my $remote = $ENV{REMOTE_ADDR} || '';
        foreach my $entry ( split( /\s*,\s*/, $tp ) ) {
            next if ( $entry eq '' );
            return 1
              if ( ( $remote eq $entry || index( $remote, $entry ) == 0 )
                && $ENV{HTTP_X_FORWARDED_PROTO} =~ /^https$/i );
        }
    }
    return 0;
}

sub BuildSessionCookie {
    my ( $value, $ttl ) = @_;
    no warnings 'once';
    my %args = (
        -name     => $HabitatEngine::CookieName,
        -value    => defined($value) ? $value : '',
        -path     => '/',
        -httponly => 1,
        -samesite => 'Lax',
    );
    if ( defined($ttl) ) {
        if ( $ttl <= 0 ) {
            $args{-expires} = 'Thu, 01-Jan-1970 00:00:00 GMT';
        } else {
            $args{-expires} = '+' . int( $ttl / 86400 ) . 'd';
        }
    }
    $args{-secure} = 1 if IsRequestSecure();
    return \%args;
}

# ----------------------------------------------------------------
# CSRF
# ----------------------------------------------------------------

sub GenCSRFToken {
    no warnings 'once';
    my $exp = $HabitatEngine::Now + 86400;
    my $uid = defined($HabitatEngine::UserID) ? $HabitatEngine::UserID : 0;
    my $sig = Hmac("csrf|$uid|$exp");
    return "$exp|$sig";
}

sub VerifyCSRFToken {
    my ($tok) = @_;
    return 0 if ( !defined($tok) || ref($tok) );
    return 0 unless ( $tok =~ /\A(\d+)\|([0-9a-f]+)\z/ );
    my ( $exp, $sig ) = ( $1, $2 );
    no warnings 'once';
    return 0 if ( $exp < $HabitatEngine::Now );
    my $uid = defined($HabitatEngine::UserID) ? $HabitatEngine::UserID : 0;
    return ConstantEq( $sig, Hmac("csrf|$uid|$exp") ) ? 1 : 0;
}

# Reads the inbound csrf_token, validates it, and on failure prints a
# 403 error page and exits the request. Uses exit (not die) so the
# error rides out cleanly under both plain CGI and PSGI (CGI::Emulate::PSGI
# traps exit). Calls back into HabitatEngine::T / GetParam for i18n +
# parameter access; those stay in the main script.
sub CSRFCheckOrDie {
    return if ( VerifyCSRFToken( HabitatEngine::GetParam( 'csrf_token', '' ) ) );
    no warnings 'once';
    print $HabitatEngine::q->header( -status => '403 Forbidden' );
    print "<h2>", HabitatEngine::T('CSRF token missing or invalid'), "</h2>";
    print "<p>",
      HabitatEngine::T(
        'The form you submitted is missing a valid CSRF token. Reload the page and try again.'),
      "</p>";
    warn( "CSRF check failed for action: " . HabitatEngine::GetParam( 'action', '?' ) );
    exit 0;
}

# ----------------------------------------------------------------
# Captcha
# ----------------------------------------------------------------

sub PrintCaptcha {
    no warnings 'once';
    my $a   = unpack( 'N', RandomBytes(4) ) % 24 + 1;
    my $b   = unpack( 'N', RandomBytes(4) ) % 24 + 1;
    my $ans = $a + $b;
    my $exp = $HabitatEngine::Now + 600;
    my $sig = Hmac("captcha|$ans|$exp");
    my $tok = "$ans|$exp|$sig";
    return
"<span class='wikicaptcha'>$a+$b=<input type='text' id='captchaans' size='4' name='captchaans' "
      . "title='type your answer here'/> "
      . qq(<input type="hidden" name="captchaopt" id="captchaopt" value="$tok" /></span>\n);
}

sub VerifyCaptcha {
    my ( $userans, $tok ) = @_;
    return 0 if ( !defined($tok) || !defined($userans) );
    return 0 unless ( $tok =~ /\A(\d+)\|(\d+)\|([0-9a-f]+)\z/ );
    my ( $ans, $exp, $sig ) = ( $1, $2, $3 );
    no warnings 'once';
    return 0 if ( $exp < $HabitatEngine::Now );
    return 0 unless ConstantEq( $sig, Hmac("captcha|$ans|$exp") );
    return 0 unless ( $userans =~ /\A\s*-?\d+\s*\z/ );
    return ( int($userans) == $ans ) ? 1 : 0;
}

# ----------------------------------------------------------------
# Login throttle
# ----------------------------------------------------------------

sub _dbh {
    no warnings 'once';
    return $HabitatEngine::dbh;
}

sub EnsureLoginThrottleTable {
    my $dbh = _dbh();
    return if ( !$dbh );

    # Columns renamed from key/count (both MariaDB reserved words)
    # to attempt_key/attempts. init_schema creates the table with
    # the new shape; this lazy-create is a safety net for code
    # paths that bypass init_schema.
    #
    # varchar(255) (not TEXT) for the PK so MariaDB/InnoDB accepts
    # it without an explicit key prefix length.
    eval {
        $dbh->do( 'CREATE TABLE IF NOT EXISTS login_attempts ('
              . 'attempt_key varchar(255) PRIMARY KEY,'
              . 'attempts INTEGER NOT NULL,'
              . 'first_ts INTEGER NOT NULL,'
              . 'last_ts INTEGER NOT NULL'
              . ')' );
    };
}

sub LoginThrottleBlocked {
    my ($key) = @_;
    my $dbh = _dbh();
    return 0 if ( !defined($key) || $key eq '' || !$dbh );
    EnsureLoginThrottleTable();
    my $row =
      $dbh->selectrow_arrayref( 'SELECT attempts, first_ts FROM login_attempts WHERE attempt_key=?',
        undef, $key );
    return 0 if ( !$row );
    my ( $count, $first ) = @$row;
    no warnings 'once';
    return 0 if ( $HabitatEngine::Now - $first > $HabitatEngine::LoginThrottleWindow );
    return ( $count >= $HabitatEngine::LoginMaxAttempts ) ? 1 : 0;
}

sub LoginThrottleHit {
    my ($key) = @_;
    my $dbh = _dbh();
    return if ( !defined($key) || $key eq '' || !$dbh );
    EnsureLoginThrottleTable();
    my $row =
      $dbh->selectrow_arrayref( 'SELECT attempts, first_ts FROM login_attempts WHERE attempt_key=?',
        undef, $key );
    no warnings 'once';
    my $now = $HabitatEngine::Now;
    my $win = $HabitatEngine::LoginThrottleWindow;

    if ( !$row || $now - $row->[1] > $win ) {

        # Portable upsert: REPLACE INTO works on SQLite + MariaDB;
        # Habitat::Store::WriteDBItems handles the Postgres ON
        # CONFLICT dialect.
        Habitat::Store::WriteDBItems( 'login_attempts', 'attempt_key,attempts,first_ts,last_ts',
            1, $key, 1, $now, $now );
    } else {
        $dbh->do( 'UPDATE login_attempts SET attempts=attempts+1, last_ts=? WHERE attempt_key=?',
            undef, $now, $key );
    }
}

sub LoginThrottleClear {
    my ($key) = @_;
    my $dbh = _dbh();
    return if ( !defined($key) || $key eq '' || !$dbh );
    eval { $dbh->do( 'DELETE FROM login_attempts WHERE attempt_key=?', undef, $key ); };
}

# ----------------------------------------------------------------
# Passwords (bcrypt + legacy crypt fallback)
# ----------------------------------------------------------------

sub HashPassword {
    my ($pw) = @_;
    return '' if ( !defined($pw) || $pw eq '' );
    my $salt = RandomBytes(16);
    return bcrypt( $pw, '2b', 12, $salt );
}

sub VerifyPassword {
    my ( $pw, $stored ) = @_;
    return 0 if ( !defined($pw) || !defined($stored) || $stored eq '' );
    if ( $stored =~ /\A\$2[abxy]\$/ ) {
        return bcrypt_check( $pw, $stored ) ? 1 : 0;
    }
    my $h = crypt( $pw, $stored );
    return 0 if ( !defined($h) );
    return ConstantEq( $h, $stored );
}

sub IsLegacyPasswordHash {
    my ($stored) = @_;
    return 0 if ( !defined($stored) || $stored eq '' );
    return ( $stored !~ /\A\$2[abxy]\$/ );
}

sub UpgradePasswordHashDB {
    my ( $username, $newhash ) = @_;
    return if ( !defined($username) || $username eq '' );
    return if ( !defined($newhash)  || $newhash eq '' );
    my $dbh = _dbh();
    return if ( !$dbh );
    no warnings 'once';
    my $userdb = ( split( /\//, $HabitatEngine::UserDir ) )[-1];
    return if ( $userdb eq '' || !Habitat::Store::SafeIdent($userdb) );
    my $sth = $dbh->prepare("update $userdb set pass=? where name=?");
    $sth->execute( $newhash, $username );
}

1;
