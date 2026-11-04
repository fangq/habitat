#!/usr/bin/env perl
# $StyleSheet may carry a ?query (cache-busting, e.g. "?v=20261104"); the
# derived print and webfont stylesheets keep it. Without a query the
# derived names are unchanged.
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
no warnings 'once';
$HabitatEngine::q = CGI->new( {} );

sub links {
    my ($css) = @_;
    local $HabitatEngine::StyleSheet = $css;
    my $h = HabitatEngine::GetHtmlHeader( 'T', '' );
    return [ $h =~ /<link rel="stylesheet" href="([^"]+)"/g ];
}

is_deeply(
    links('css/wikistyle_column.css'),
    [ 'css/wikistyle_column_webfont.css', 'css/wikistyle_column.css', 'css/wikistyle_column_print.css' ],
    'plain stylesheet: derived names unchanged'
);
is_deeply(
    links('css/wikistyle_column.css?v=20261104'),
    [ 'css/wikistyle_column_webfont.css?v=20261104', 'css/wikistyle_column.css?v=20261104',
      'css/wikistyle_column_print.css?v=20261104' ],
    'versioned stylesheet: ?v= carried to the webfont and print stylesheets'
);

done_testing;
