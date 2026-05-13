package HabitatHarness;
#
# Shared bootstrap for the Habitat test suite.
#
# Loads index.cgi as a library: the script ends with
#   &DoWikiRequest() if ($RunCGI && $_ ne 'nocgi');
# so setting $_ to "nocgi" before `require` suppresses the auto-run
# and leaves every sub callable as HabitatEngine::FuncName.
#
# Tests use this module instead of an inline require so that:
#   - the chdir-to-habitat happens once per test process
#   - CGI::Carp's fatalsToBrowser noise is suppressed
#   - a fresh in-memory SQLite + known site secret can be set up
#     deterministically per test, avoiding cross-test bleed

use strict;
use warnings;
use FindBin qw($Bin);
use File::Spec ();

# Chdir to habitat/ at compile time so any subsequent `use Habitat::*`
# in the test file resolves against habitat/lib/. Done in BEGIN so it
# happens before module-load-time of test-file use statements.
BEGIN {
    my $habitat_dir = File::Spec->catdir( $Bin, File::Spec->updir );
    chdir $habitat_dir or die "HabitatHarness: cannot chdir to $habitat_dir: $!";
    unshift @INC, File::Spec->catdir( $habitat_dir, 'lib' );
}

sub load_wiki {
    # Idempotent: if a previous load (e.g. via app.psgi + CGI::Compile)
    # already defined the package, skip. Avoids "Subroutine redefined"
    # warnings when one test loads both the bare script and the PSGI
    # wrapper that compiles it itself.
    return 1 if defined &HabitatEngine::DoWikiRequest;

    # Pre-empt CGI::Carp::fatalsToBrowser so a test failure doesn't
    # render an HTML error page to STDOUT (which TAP would then choke on).
    $ENV{NO_FATALS_TO_BROWSER} = 1;

    {
        local $_ = 'nocgi';
        require "./index.cgi";
    }
    return 1;
}

# Replace the script-level $dbh with a fresh in-memory SQLite handle
# that has the schema applied. Returns the handle. Habitat::Store reads
# $HabitatEngine::dbh through its _dbh() accessor so this is all that's
# needed for the Store helpers to operate against the test DB.
sub fresh_test_db {
    require DBI;
    my $dbh = DBI->connect( 'dbi:SQLite:dbname=:memory:', '', '',
        { RaiseError => 1, AutoCommit => 1 } );
    $dbh->func(
        'regexp', 2,
        sub {
            my ( $regex, $string ) = @_;
            return $string =~ /$regex/;
        },
        'create_function'
    );
    apply_schema($dbh);

    # The store reads $HabitatEngine::dbh; expose ours there.
    no warnings 'once';
    $HabitatEngine::dbh = $dbh;
    return $dbh;
}

# Mirror of habitat/db/gendb.sql, kept here so tests don't depend on
# a file path that might move. Kept in sync by hand; if you change
# the production schema, change this too.
sub apply_schema {
    my ($dbh) = @_;
    my @stmts = split /;\s*\n/, <<'SQL';
CREATE TABLE page (
  id varchar(512), version integer,
  author varchar(32), revision integer, tupdate integer, tcreate integer,
  ip varchar(32), host varchar(64), summary varchar(128), text text,
  minor integer, newauthor integer, data varchar(32), tag varchar(32)
);
CREATE INDEX page_id ON page(id ASC);
CREATE TABLE deletedpage (
  id varchar(512), version integer,
  author varchar(32), revision integer, tupdate integer, tcreate integer,
  ip varchar(32), host varchar(64), summary varchar(128), text text,
  minor integer, newauthor integer, data varchar(32), tag varchar(32)
);
CREATE TABLE user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name varchar(32), pass varchar(255),
  randkey varchar(255), groupid varchar(255), lang varchar(8),
  email varchar(64), param varchar(32), createtime integer,
  stylesheet varchar(128), createip varchar(32), tzoffset integer,
  pagecreate varchar(512), pagemodify varchar(512)
);
CREATE TABLE html (
  id varchar(512) PRIMARY KEY, time integer, text text
);
CREATE TABLE rclog (
  time integer, id varchar(512), summary varchar(128),
  isedit integer, host varchar(64), kind varchar(8),
  userid integer, name varchar(32), revision integer, isadmin integer
);
CREATE TABLE lock (
  id varchar(512) PRIMARY KEY, tag varchar(32)
);
CREATE TABLE watch (
  page varchar(512), user varchar(32)
);
CREATE TABLE system (
  id varchar(64) PRIMARY KEY, data text, time integer
);
CREATE TABLE pagelog (
  id varchar(512) PRIMARY KEY, lastvisit integer, visit integer,
  x integer, y integer, z integer
);
CREATE TABLE userlog (
  id integer, time integer, ip varchar(32),
  action varchar(8), target varchar(255)
);
SQL
    for my $stmt (@stmts) {
        $stmt =~ s/^\s+|\s+$//g;
        next if $stmt eq '';
        $dbh->do($stmt);
    }
    return $dbh;
}

# Pin $Now and $SiteSecret to known values so HMAC-based tokens are
# reproducible. Tests that exercise token expiry should manage their
# own $Now via local().
sub freeze_time {
    my ($t) = @_;
    no warnings 'once';
    $HabitatEngine::Now = $t || 1_700_000_000;
}

sub set_test_secret {
    my $secret = "x" x 64;
    no warnings 'once';
    $HabitatEngine::SiteSecret = $secret;
    return $secret;
}

1;
