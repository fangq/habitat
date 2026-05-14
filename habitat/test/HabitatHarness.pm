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
    require Habitat::Store;
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

    # Single source of truth for the schema lives in Habitat::Store —
    # the test harness and the production wiki bootstrap go through
    # the same code path.
    Habitat::Store::init_schema($dbh);

    # The store reads $HabitatEngine::dbh; expose ours there.
    no warnings 'once';
    $HabitatEngine::dbh = $dbh;
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
