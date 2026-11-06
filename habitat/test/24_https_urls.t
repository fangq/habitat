#!/usr/bin/env perl
# Links the wiki builds to itself use https by default ($UseHttps), even
# when the request reached the CGI as plain http (TLS proxy in front);
# never for localhost; $UseHttps = 0 keeps the request's scheme.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use CGI;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);
no warnings 'once';

sub url_for {
    my (%env) = @_;
    local @ENV{ keys %env } = values %env;
    local $ENV{HTTPS};
    delete $ENV{HTTPS};
    $HabitatEngine::q = CGI->new('');
    return HabitatEngine::SelfUrl();
}
my %site = ( SERVER_NAME => 'wenq.org', SERVER_PORT => 80, SCRIPT_NAME => '/legacy/index.cgi', HTTP_HOST => 'wenq.org' );

$HabitatEngine::UseHttps = 1;
is( url_for(%site), 'https://wenq.org/legacy/index.cgi', "plain-http request: self URL upgraded to https" );
is( url_for( %site, SERVER_NAME => 'localhost', HTTP_HOST => 'localhost:51712', SERVER_PORT => 51712 ),
    'http://localhost:51712/legacy/index.cgi', "localhost keeps http" );
is( url_for( %site, SERVER_NAME => '127.0.0.1', HTTP_HOST => '127.0.0.1' ),
    'http://127.0.0.1/legacy/index.cgi', "127.0.0.1 keeps http" );

{
    local $HabitatEngine::UseHttps = 0;
    is( url_for(%site), 'http://wenq.org/legacy/index.cgi', "\$UseHttps = 0 keeps the request's scheme" );
}

# Redirects (e.g. glyph page -> editor) carry the https URL.
{
    local @ENV{ keys %site } = values %site;
    delete local $ENV{HTTPS};
    $HabitatEngine::q        = CGI->new('');
    $HabitatEngine::FullUrl  = '';
    $HabitatEngine::RedirType = 2;
    my $html = HabitatEngine::GetRedirectPage( 'Canvas#U4E00_WQYS', 'Canvas', 0 );
    like( $html, qr{^Location: https://wenq\.org/legacy/index\.cgi\?Canvas}m, "redirect Location uses https" );
}

done_testing;
