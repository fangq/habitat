#!/usr/bin/env perl
# Author-only raw-HTML gate (Option B):
#   - Page's current revision was saved by an admin (admin_saved=1)
#     -> ScrubRawHtml is bypassed in both the <html>...</html> block
#        path and the Markdown-render path. <script>, AJAX, and
#        javascript: URLs survive.
#   - Page saved by anyone else (admin_saved=0)
#     -> Scrub still happens. <script> stripped, javascript: URLs
#        stripped.
#
# The flag is captured at save time, not derived later — so revoking
# the admin password later doesn't retroactively un-trust existing
# pages, but the next non-admin save will flip the flag off.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once', 'redefine';
HabitatEngine::InitLinkPatterns();

{

    package FakeCGI14;
    sub new     { bless {}, shift }
    sub param   { return }
    sub charset { return }
    sub url     { return '' }
}
$HabitatEngine::q                  = FakeCGI14->new;
$HabitatEngine::UserID             = 1001;
$HabitatEngine::UserData{id}       = 1001;
$HabitatEngine::UserData{username} = 'admin';
$HabitatEngine::RawHtml            = 1;

# Toggle for the SavePageDB admin check below.
our $admin_state = 0;
*HabitatEngine::UserIsAdmin = sub { $admin_state };

sub seed_page {
    my ( $id, $text, $is_admin ) = @_;
    local $admin_state = $is_admin ? 1 : 0;

    my $P = \%{ $HabitatEngine::Pages{$id}{'page'} };
    my $S = \%{ $HabitatEngine::Pages{$id}{'section'} };
    my $T = \%{ $HabitatEngine::Pages{$id}{'text'} };
    $P->{name}      = $id;
    $P->{version}   = 3;
    $P->{tscreate}  = 1_700_000_000;
    $S->{name}      = 'text_default';
    $S->{ip}        = '127.0.0.1';
    $S->{host}      = 'localhost';
    $T->{text}      = $text;
    $T->{summary}   = '';
    $T->{minor}     = 0;
    $T->{newauthor} = 0;
    HabitatEngine::SavePageDB($id);
}

# ----------------------------------------------------------------
# SavePageDB / OpenPageDB round-trip the admin_saved flag.
# ----------------------------------------------------------------
seed_page( 'AdminPage', "stub\n", 1 );
seed_page( 'UserPage',  "stub\n", 0 );

is( $dbh->selectrow_array( "SELECT admin_saved FROM page WHERE id=?", undef, 'AdminPage' ),
    1, "admin-saved page row records admin_saved=1" );
is( $dbh->selectrow_array( "SELECT admin_saved FROM page WHERE id=?", undef, 'UserPage' ),
    0, "non-admin-saved page row records admin_saved=0" );

# OpenPageDB should reload the flag into the in-memory $Pages structure.
{
    local $HabitatEngine::OpenPageName = '';
    delete $HabitatEngine::Pages{'AdminPage'};
    HabitatEngine::OpenPageDB('AdminPage');
    is( $HabitatEngine::Pages{'AdminPage'}{'page'}{'admin_saved'},
        1, "OpenPageDB reloads admin_saved=1" );
}
{
    local $HabitatEngine::OpenPageName = '';
    delete $HabitatEngine::Pages{'UserPage'};
    HabitatEngine::OpenPageDB('UserPage');
    is( $HabitatEngine::Pages{'UserPage'}{'page'}{'admin_saved'},
        0, "OpenPageDB reloads admin_saved=0" );
}

# ----------------------------------------------------------------
# <html> block bypass in the wiki render path.
# ----------------------------------------------------------------
my $body = <<'WIKI';
<html>
<script>alert(1)</script>
<a href="javascript:bad()">bad</a>
<button onclick="evil()">go</button>
</html>
WIKI

# Admin-trusted: scrub skipped, dangerous markup survives.
{
    $HabitatEngine::Pages{'AdminPage'}{'rules'} = 1;
    $HabitatEngine::OpenPageName = 'AdminPage';
    my $out = HabitatEngine::WikiToHTML( 'AdminPage', $body );
    like( $out, qr|<script>|i,       "admin-trusted page: <script> survives ScrubRawHtml bypass" );
    like( $out, qr|javascript:bad|i, "admin-trusted page: javascript: URL survives" );
    like( $out, qr|onclick=|i,       "admin-trusted page: inline onclick survives" );
}

# Non-admin-saved: scrub stays on, dangerous markup stripped.
{
    $HabitatEngine::Pages{'UserPage'}{'rules'} = 1;
    $HabitatEngine::OpenPageName = 'UserPage';
    my $out = HabitatEngine::WikiToHTML( 'UserPage', $body );
    unlike( $out, qr|<script|i,     "untrusted page: <script> stripped by ScrubRawHtml" );
    unlike( $out, qr|javascript:|i, "untrusted page: javascript: URL stripped" );
    unlike( $out, qr|onclick=|i,    "untrusted page: inline onclick stripped" );
}

# ----------------------------------------------------------------
# Markdown render path observes the same gate.
# ----------------------------------------------------------------
SKIP: {
    eval { require Text::Markdown::Discount; 1 }
      or skip "Text::Markdown::Discount not installed", 4;

    my $md =
      "<!-- markdown -->\n# H\n\n<script>alert(2)</script>\n" . "[bad](javascript:alert(3))\n";

    {
        $HabitatEngine::Pages{'AdminPage'}{'rules'} = 1;
        $HabitatEngine::OpenPageName = 'AdminPage';
        my $out = HabitatEngine::WikiToHTML( 'AdminPage', $md );
        like( $out, qr|<h1[^>]*>H</h1>|i, "admin-trusted markdown: heading renders" );
        like( $out, qr|<script|i,         "admin-trusted markdown: <script> survives" );
    }

    {
        $HabitatEngine::Pages{'UserPage'}{'rules'} = 1;
        $HabitatEngine::OpenPageName = 'UserPage';
        my $out = HabitatEngine::WikiToHTML( 'UserPage', $md );
        like( $out, qr|<h1[^>]*>H</h1>|i, "untrusted markdown: heading still renders" );
        unlike( $out, qr|<script|i, "untrusted markdown: <script> stripped" );
    }
}

# ----------------------------------------------------------------
# A non-admin save on an admin-trusted page revokes trust.
# ----------------------------------------------------------------
seed_page( 'AdminPage', "follow-up\n", 0 );
is( $dbh->selectrow_array( "SELECT admin_saved FROM page WHERE id=?", undef, 'AdminPage' ),
    0, "non-admin save flips admin_saved back to 0 (no retroactive trust)" );

done_testing;
