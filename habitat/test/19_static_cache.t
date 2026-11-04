#!/usr/bin/env perl
# Static page cache ($StaticCacheDir, served by Apache via mod_rewrite).
# Exercises the real BrowsePage / SavePageDB / CSRFCheckOrDie paths:
#   - the exact anonymous request the rewrite serves is written, as the
#     HTML body (no CGI headers), atomically, world-readable
#   - nothing else is written (logged in, wiki cookie, other query
#     strings, POST, revisions, per-request variables, missing pages,
#     unsafe ids)
#   - any write purges the whole cache; config/engine changes purge it
#   - a render that began before a purge does not write afterwards

use strict;
use warnings;
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
*HabitatEngine::UserIsAdmin = sub { 1 };    # seed pages as trusted

my $dir = tempdir( CLEANUP => 1 );
$HabitatEngine::StaticCacheDir = "$dir/cache";
mkdir $HabitatEngine::StaticCacheDir or die;
$HabitatEngine::CookieName = 'TestWikiCookie';
$HabitatEngine::HomePage   = 'Home';
$HabitatEngine::RawHtml    = 1;

sub seed {
    my ( $id, $text ) = @_;
    %HabitatEngine::Pages     = ();
    %HabitatEngine::TextCache = ();
    $HabitatEngine::OpenPageName = '';
    my $P = \%{ $HabitatEngine::Pages{$id}{'page'} };
    my $S = \%{ $HabitatEngine::Pages{$id}{'section'} };
    my $T = \%{ $HabitatEngine::Pages{$id}{'text'} };
    @$P{qw(name version tscreate)} = ( $id, 3, 1_700_000_000 );
    @$S{qw(name ip host)}          = ( 'text_default', '127.0.0.1', 'localhost' );
    @$T{qw(text summary minor newauthor)} = ( $text, '', 0, 0 );
    HabitatEngine::SavePageDB($id);
}

# Render $id as a request with the given environment / CGI params.
sub browse {
    my ( $id, %o ) = @_;
    local $ENV{REQUEST_METHOD} = $o{method} // 'GET';
    local $ENV{QUERY_STRING}   = exists $o{qs} ? $o{qs} : $id;
    local $ENV{HTTP_COOKIE}    = $o{cookie} // '';
    %HabitatEngine::Pages     = ();
    %HabitatEngine::TextCache = ();
    $HabitatEngine::OpenPageName = '';
    $HabitatEngine::q            = CGI->new( $o{params} // {} );
    $HabitatEngine::UserID       = $o{uid} // 111;
    %HabitatEngine::UserData     = $o{user} ? ( username => $o{user} ) : ();
    $HabitatEngine::StaticCacheOK = 1;
    $HabitatEngine::PrintedHeader = 0;    # each call is a new request
    my $out = '';
    {
        local *STDOUT;
        open( STDOUT, '>', \$out ) or die;
        HabitatEngine::BrowsePage($id);
        close STDOUT;
    }
    return $out;
}

sub cached { my ($rel) = @_; my $f = "$dir/cache/$rel"; return -f $f ? do { local ( @ARGV, $/ ) = $f; <> } : undef }

seed( 'TestPage',  "= Hello =\nstatic body\n<html><script>trusted()</script></html>\n" );
seed( 'Page/Sub',  "subpage body\n" );
seed( 'DatePage',  "today is &lt;datenow&gt;\n" );    # the form that renders a live date (as plugin templates emit it)
seed( 'Home',      "home body\n" );

# ---------------------------------------------------------------- write
my $out = browse('TestPage');
my $html = cached('p/TestPage.html');
ok( defined $html, "anonymous GET ?TestPage writes cache/p/TestPage.html" );
like( $html, qr/\A<!DOCTYPE/i, "  ... body only (starts with DOCTYPE)" );
unlike( $html, qr/\AContent-Type:/mi, "  ... no CGI header block" );
like( $html, qr/static body/, "  ... contains the rendered page" );
like( $html, qr/<script>trusted\(\)/, "  ... trusted raw HTML intact" );
( my $body = $out ) =~ s/\A(?:[A-Za-z][\w-]*:[^\r\n]*\r?\n)+\r?\n//;
is( $html, $body, "  ... identical to what the CGI sent" );
is( ( stat("$dir/cache/p/TestPage.html") )[2] & 07777, 0604, "  ... mode 0604 (readable by Apache)" );
ok( !glob("$dir/cache/p/*.tmp*"), "  ... no temp file left behind" );

browse('Page/Sub');
ok( defined cached('p/Page/Sub.html'), "subpage ?Page/Sub writes cache/p/Page/Sub.html" );

browse( 'Home', qs => '' );
ok( defined cached('front.html'), "bare GET (empty query) of the home page writes cache/front.html" );

# ---------------------------------------------------------------- no write
my @skip = (
    [ 'logged-in user',            uid => 1001, user => 'alice' ],
    [ 'wiki cookie present',       cookie => '_ga=1; TestWikiCookie=abc' ],
    [ 'action=browse&id= form',    qs => 'action=browse&id=TestPage', params => { action => 'browse', id => 'TestPage' } ],
    [ 'extra parameter (lang)',    qs => 'TestPage&lang=cn', params => { lang => 'cn' } ],
    [ 'POST',                      method => 'POST' ],
    [ 'old revision',              params => { revision => 1 } ],
);
for my $c (@skip) {
    my ( $label, %o ) = @$c;
    HabitatEngine::PurgeStaticCache();
    browse( 'TestPage', %o );
    ok( !defined cached('p/TestPage.html'), "not written: $label" );
}
HabitatEngine::PurgeStaticCache();
browse( 'TestPage', cookie => '_ga=GA1.1.1; _gid=x' );
ok( defined cached('p/TestPage.html'), "written despite analytics cookies (only the wiki cookie counts)" );

browse('DatePage');
ok( !defined cached('p/DatePage.html'), "not written: page renders a live date (datenow)" );
browse('NoSuchPage');
ok( !defined cached('p/NoSuchPage.html'), "not written: nonexistent page" );

for my $bad ( '../x', '.v0', 'Page/.v0', 'a//b', 'x/../y', '' ) {
    local $ENV{QUERY_STRING} = $bad;
    is( HabitatEngine::StaticCacheFile($bad), '', "unsafe/ineligible id rejected: '$bad'" );
}

# ---------------------------------------------------------------- purge
browse('TestPage');
browse( 'Home', qs => '' );
ok( defined cached('p/TestPage.html') && defined cached('front.html'), "cache populated" );
my $gen0 = HabitatEngine::StaticCacheGeneration();
seed( 'Other', "another page\n" );    # SavePageDB
ok( !defined cached('p/TestPage.html'), "SavePageDB purges page files" );
ok( !defined cached('front.html'),      "  ... and the front page" );
isnt( HabitatEngine::StaticCacheGeneration(), $gen0, "  ... and bumps the generation" );

browse('TestPage');
{
    $HabitatEngine::q = CGI->new( { csrf_token => HabitatEngine::GenCSRFToken() } );
    HabitatEngine::CSRFCheckOrDie();
}
ok( !defined cached('p/TestPage.html'), "a verified CSRF POST purges the cache" );

# A render that began before a purge must not write afterwards.
{
    local $ENV{REQUEST_METHOD} = 'GET';
    local $ENV{QUERY_STRING}   = 'TestPage';
    local $ENV{HTTP_COOKIE}    = '';
    $HabitatEngine::UserID        = 111;
    %HabitatEngine::UserData      = ();
    $HabitatEngine::StaticCacheOK = 1;
    $HabitatEngine::StaticCacheGen = HabitatEngine::StaticCacheGeneration();
    HabitatEngine::PurgeStaticCache();    # concurrent edit while "rendering"
    $HabitatEngine::StaticCacheGen = 'stale';
    HabitatEngine::WriteStaticCache( 'TestPage',
        "Content-Type: text/html\n\n<!DOCTYPE HTML>\n<html>stale</html>" );
    ok( !defined cached('p/TestPage.html'), "render begun before a purge does not write" );
}

# Config / engine change purges.
{
    my $cfg = "$dir/config";
    open( my $fh, '>', $cfg ) or die;
    print $fh "1;\n";
    close $fh;
    local $HabitatEngine::ConfigFile = $cfg;
    HabitatEngine::StaticCacheCheckStamp();    # records the stamp
    browse('TestPage');
    HabitatEngine::StaticCacheCheckStamp();
    ok( defined cached('p/TestPage.html'), "unchanged config: cache kept" );
    utime( 1_600_000_000, 1_600_000_000, $cfg );
    HabitatEngine::StaticCacheCheckStamp();
    ok( !defined cached('p/TestPage.html'), "config modified: cache purged" );
}

# Disabled by default.
{
    local $HabitatEngine::StaticCacheDir = '';
    HabitatEngine::PurgeStaticCache();
    browse('TestPage');
    ok( !glob("$dir/cache/p/*"), "StaticCacheDir '' : nothing written" );
}

done_testing;
