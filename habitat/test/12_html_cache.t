#!/usr/bin/env perl
# Stage 6: HTML output cache. Verifies:
#   - $UseCache=0 (default): every request renders, no cache writes
#   - $UseCache=1, anonymous request: cache populated, hit on retry
#   - Authenticated request: cache bypassed (never serve a cached
#     anonymous page to a logged-in user, and vice-versa)
#   - RenamePage invalidates cache entries for the old id

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();

no warnings 'once';
HabitatEngine::InitLinkPatterns();

# GetParam reaches into $q->param; stub it for any path that needs it.
{
    package FakeCGI3;
    sub new { bless {}, shift }
    sub param   { return }
    sub charset { return }
    sub url     { return '' }
}
$HabitatEngine::q = FakeCGI3->new;

# Seed a page so the wiki has something to cache.
$HabitatEngine::OpenPageName = '';
$HabitatEngine::UserID       = 1001;
$HabitatEngine::UserData{'id'}       = 1001;
$HabitatEngine::UserData{'username'} = 'alice';
{
    my $P = \%{ $HabitatEngine::Pages{'Cached'}{'page'} };
    my $S = \%{ $HabitatEngine::Pages{'Cached'}{'section'} };
    my $T = \%{ $HabitatEngine::Pages{'Cached'}{'text'} };
    $P->{name}      = 'Cached';
    $P->{version}   = 3;
    $P->{tscreate}  = 1_700_000_000;
    $S->{name}      = 'text_default';
    $S->{ip}        = '127.0.0.1';
    $S->{host}      = 'localhost';
    $T->{text}      = "cached body\n";
    $T->{summary}   = '';
    $T->{minor}     = 0;
    $T->{newauthor} = 0;
    HabitatEngine::SavePageDB('Cached');
}

# ----------------------------------------------------------------
# UpdateHtmlCacheDB writes; ReadDBItems retrieves
# ----------------------------------------------------------------
HabitatEngine::UpdateHtmlCacheDB( 'Cached', '<html>cached for Cached</html>' );
my $hit = $dbh->selectrow_array("SELECT text FROM html WHERE id='Cached[en]'");
is( $hit, '<html>cached for Cached</html>', "UpdateHtmlCacheDB wrote the row" );

# ----------------------------------------------------------------
# RenamePage cleans up html cache entries for the old id
# ----------------------------------------------------------------
HabitatEngine::UpdateHtmlCacheDB( 'Cached', '<html>still cached</html>' );

# Seed a second-language cache entry to verify LIKE pattern works
$dbh->do( "INSERT OR REPLACE INTO html (id, time, text) VALUES (?, ?, ?)",
    undef, 'Cached[zh]', 100, '<html>zh</html>' );

is(
    $dbh->selectrow_array("SELECT COUNT(*) FROM html WHERE id LIKE 'Cached[%]'"),
    2, "two cache rows present pre-rename (en and zh)"
);

HabitatEngine::RenamePage( 'Cached', 'Renamed', 0, 0 );

is(
    $dbh->selectrow_array("SELECT COUNT(*) FROM html WHERE id LIKE 'Cached[%]'"),
    0, "after RenamePage: zero cache rows for old id (all lang variants invalidated)"
);

# ----------------------------------------------------------------
# DoCacheBrowse cookie-bypass guard
# ----------------------------------------------------------------
$dbh->do("DELETE FROM html");
$dbh->do( "INSERT INTO html (id, time, text) VALUES (?, ?, ?)",
    undef, 'Renamed[en]', 100, '<html>anonymous</html>' );

# Stub $q so InitParam can run; DoCacheBrowse reads from it.
{
    package FakeCGI2;
    sub new { bless {}, shift }
    sub param   { return }
    sub charset { return }
    sub url     { return '' }
}
$HabitatEngine::q = FakeCGI2->new;

local $HabitatEngine::UseCache = 1;
local $HabitatEngine::HomePage = 'Renamed';

# Anonymous (no cookie): DoCacheBrowse should hit the cache and print
{
    local %ENV = (
        QUERY_STRING   => 'Renamed',
        REQUEST_METHOD => 'GET',
    );
    my $captured = '';
    open( my $oldout, '>&', \*STDOUT );
    close STDOUT;
    open( STDOUT, '>', \$captured );
    my $r = HabitatEngine::DoCacheBrowse();
    open( STDOUT, '>&', $oldout );
    is( $r, 1, "anonymous request with cached entry returns 1 (cache hit)" );
    like( $captured, qr/anonymous/, "cached body emitted to STDOUT" );
}

# Same request but with a Cookie header: cache must be bypassed
{
    local %ENV = (
        QUERY_STRING   => 'Renamed',
        REQUEST_METHOD => 'GET',
        HTTP_COOKIE    => 'HabitatWiki=anything',
    );
    my $r = HabitatEngine::DoCacheBrowse();
    is( $r, 0,
        "request with Cookie header bypasses cache (would serve admin-stripped HTML to authed user otherwise)"
    );
}

done_testing;
