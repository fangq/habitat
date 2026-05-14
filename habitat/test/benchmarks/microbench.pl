#!/usr/bin/env perl
# Microbenchmarks for the wiki's core paths. Reports timings for
# individual operations on an in-memory SQLite handle so the numbers
# reflect the application itself, not your storage or network.
#
# Run:
#   cd habitat/
#   perl test/benchmarks/microbench.pl                       # default 1000 iters
#   perl test/benchmarks/microbench.pl --iter=10000          # more samples
#   perl test/benchmarks/microbench.pl --filter render       # one bench only
#
# Each bench is timed with Time::HiRes; we report median +
# p10/p90 (over the requested iteration count) so a single GC
# pause doesn't skew the average.

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/..";    # so we can `use HabitatHarness;`
use Getopt::Long;
use Time::HiRes qw(gettimeofday tv_interval);
use HabitatHarness;

our $iter   = 1000;
our $filter = '';
GetOptions(
    "iter=i"   => \$iter,
    "filter=s" => \$filter,
) or die;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once';
HabitatEngine::InitLinkPatterns();
{

    package FakeCGI;
    sub new     { bless {}, shift }
    sub param   { return }
    sub charset { return }
    sub url     { return '' }
}
$HabitatEngine::q            = FakeCGI->new;
$HabitatEngine::OpenPageName = '';
$HabitatEngine::UserID       = 1001;
$HabitatEngine::UserData{id} = 1001;

sub time_bench {
    my ( $name, $sub ) = @_;
    return if ( $filter && $name !~ /\Q$filter\E/i );

    # Warm up to remove first-iteration noise (DBI prepare cache,
    # regex compile, module-load deferral, etc.).
    $sub->() for ( 1 .. 10 );

    my @times;
    for ( 1 .. $iter ) {
        my $t0 = [gettimeofday];
        $sub->();
        push @times, tv_interval($t0);
    }

    @times = sort { $a <=> $b } @times;
    my $p10 = $times[ int( $iter * 0.1 ) ] * 1e6;
    my $p50 = $times[ int( $iter * 0.5 ) ] * 1e6;
    my $p90 = $times[ int( $iter * 0.9 ) ] * 1e6;
    printf "%-40s p10=%7.1fus  median=%7.1fus  p90=%7.1fus\n", $name, $p10, $p50, $p90;
}

# ----------------------------------------------------------------
# Crypto primitives (Stage 1)
# ----------------------------------------------------------------
time_bench( "RandomBytes(16)",    sub { HabitatEngine::RandomBytes(16) } );
time_bench( "Hmac (10-byte msg)", sub { HabitatEngine::Hmac("benchmark") } );
time_bench(
    "ConstantEq (64ch)",
    sub {
        HabitatEngine::ConstantEq( "x" x 64, "x" x 64 );
    }
);
time_bench( "SignSessionToken", sub { HabitatEngine::SignSessionToken(1001) } );

my $tok = HabitatEngine::SignSessionToken(1001);
time_bench( "VerifySessionToken", sub { HabitatEngine::VerifySessionToken($tok) } );

time_bench( "GenCSRFToken", sub { HabitatEngine::GenCSRFToken() } );
my $csrf = HabitatEngine::GenCSRFToken();
time_bench( "VerifyCSRFToken", sub { HabitatEngine::VerifyCSRFToken($csrf) } );

# Bcrypt is slow on purpose; use fewer iterations
{
    local $iter = 20;
    time_bench( "HashPassword (cost 12)", sub { HabitatEngine::HashPassword("hunter2") } );
    my $h = HabitatEngine::HashPassword("hunter2");
    time_bench( "VerifyPassword (good)", sub { HabitatEngine::VerifyPassword( "hunter2", $h ) } );
    time_bench( "VerifyPassword (bad)",  sub { HabitatEngine::VerifyPassword( "wrong",   $h ) } );
}

# ----------------------------------------------------------------
# Store (Stage 3 + 4)
# ----------------------------------------------------------------
$dbh->do("INSERT INTO system (id, data, time) VALUES ('bench', 'x', 1)");
time_bench(
    "ReadDBItems (single row)",
    sub {
        Habitat::Store::ReadDBItems( "system", "data", "", "", "id=?", "bench" );
    }
);
time_bench(
    "WriteDBItems (upsert)",
    sub {
        Habitat::Store::WriteDBItems( "system", "id,data,time", 1, ( "bench", "y", 2 ) );
    }
);

# ----------------------------------------------------------------
# Renderer (Stage 5/6)
# ----------------------------------------------------------------
my $wiki_short = "= Heading =\n\nLorem ipsum [[OtherPage]] dolor sit amet.\n";
my $wiki_long  = $wiki_short x 50;
my $md_short   = "<!-- markdown -->\n# Heading\n\n**bold** and `code`\n";

# Stage out a page record so WikiToHTML doesn't trip
$HabitatEngine::Pages{Bench} = {
    page    => { name => 'Bench',        version  => 3 },
    section => { name => 'text_default', revision => 1 },
    text    => { text => '',             minor    => 0, newauthor => 0, summary => '' },
    rules   => 1,
};

time_bench( "WikiToHTML (short)",      sub { HabitatEngine::WikiToHTML( 'Bench', $wiki_short ) } );
time_bench( "WikiToHTML (long, ~50x)", sub { HabitatEngine::WikiToHTML( 'Bench', $wiki_long ) } );
time_bench( "WikiToHTML (Markdown)",   sub { HabitatEngine::WikiToHTML( 'Bench', $md_short ) } );

time_bench( "ScrubRawHtml",
    sub { HabitatEngine::ScrubRawHtml('<b>x</b><script>y</script><a href="javascript:1">z</a>') } );

print "\n";
print "Iterations per bench: $iter\n";
print "DB: in-memory SQLite (Habitat::Store dialect: ", Habitat::Store::dialect($dbh), ")\n";
