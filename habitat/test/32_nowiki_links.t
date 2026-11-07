#!/usr/bin/env perl
# <nowiki> shows its content as text: HTML typed inside it is never
# emitted as markup (it bypassed ScrubRawHtml before), and character
# references still display. Local "http:" links become scheme-relative,
# so they also work on https pages. Language codes are never paths.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once', 'redefine';
HabitatEngine::InitLinkPatterns();

{

    package FakeCGI32;
    sub new     { bless {}, shift }
    sub param   { return }
    sub charset { return }
    sub url     { return '' }
}
$HabitatEngine::q       = FakeCGI32->new;
$HabitatEngine::RawHtml = 1;

sub render {
    my ( $text, $trusted ) = @_;
    my $id = 'NowikiTest';
    delete $HabitatEngine::Pages{$id};
    $HabitatEngine::Pages{$id}{'page'}{'admin_saved'} = $trusted ? 1 : 0;
    $HabitatEngine::OpenPageName = $id;
    return HabitatEngine::WikiToHTML( $id, $text );
}

for my $trusted ( 0, 1 ) {
    my $who = $trusted ? 'admin-saved' : 'user-saved';
    my $out = render( "a <nowiki><script>alert(1)</script></nowiki> b\n", $trusted );
    unlike( $out, qr/<script/i, "$who: <script> inside <nowiki> is not markup" );
    like( $out, qr/&lt;script&gt;alert\(1\)&lt;\/script&gt;/, "$who: it is shown as text" );
}

my $out = render("<nowiki><img src=x onerror=alert(1)></nowiki>\n");
unlike( $out, qr/<img/i, "<img onerror> inside <nowiki> is not markup" );

$out = render("<nowiki>&lt;toc&gt; and ''quotes'' and [[Link]]</nowiki>\n");
like( $out, qr/&lt;toc&gt; and ''quotes'' and \[\[Link\]\]/, "entities and wiki marks in <nowiki> show literally" );

$out = render("<tt><nowiki><!-- markdown --></nowiki></tt>\n");
like( $out, qr/&lt;!-- markdown --&gt;/, "an HTML comment in <nowiki> is visible" );

$out = render("<pre><nowiki>{{x}}</nowiki></pre>\n");
like( $out, qr/<pre>\{\{x\}\}<\/pre>/, "<nowiki> inside <pre>" );

# Local links.
$out = render("[http:?action=index all pages] [http:/images/a.png] [http:#top up]\n");
like( $out, qr/href="\?action=index"/, "[http:?...] becomes a relative link" );
like( $out, qr/href="\/images\/a\.png"/, "[http:/...] becomes a root-relative link" );
like( $out, qr/href="#top"/, "[http:#...] becomes an anchor link" );
$out = render("http:/images/logo.png\n");
like( $out, qr/<img src="\/images\/logo\.png"/, "bare http:/x.png image is root-relative" );
$out = render("[https://example.com/ ext] http://example.org/x\n");
like( $out, qr/href="https:\/\/example\.com\/"/, "absolute https link unchanged" );
like( $out, qr/href="http:\/\/example\.org\/x"/, "absolute http link unchanged" );

# Language codes pick a file that is run as Perl: never a path.
is( HabitatEngine::SafeLangID($_), $_, "language code '$_' accepted" ) for qw(en cn zh_TW);
is( HabitatEngine::SafeLangID($_), '', "language value '$_' refused" )
  for ( '../../upload/x', 'en/../../x', "en\0", 'en.', '', 'EN', 'english' );
is( HabitatEngine::SafeLangID(undef), '', "undefined language refused" );

done_testing();
