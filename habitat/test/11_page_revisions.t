#!/usr/bin/env perl
# Stage 5: page_revisions schema. Verifies the new write path produces
# the expected row layout — one row per page in `page` (current
# snapshot), one row per historical revision in `page_revisions`.
#
# This test calls SavePageDB directly, bypassing the full DoPost
# flow, so the assertions land on storage shape rather than HTTP
# semantics.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::freeze_time(1_700_000_000);

# InitLinkPatterns populates $FS / $FS1..$FS5, which several of the
# read-path functions use as regex separators. Without it, PatchPage's
# regex degenerates to // which zero-width-matches everywhere.
HabitatEngine::InitLinkPatterns();

# A minimal CGI stub so functions reaching into $q->param via GetParam
# don't blow up. We don't render HTML; we just need GetParam to return
# the defaults the caller passes in.
{
    package FakeCGI;
    sub new   { bless {}, shift }
    sub param { return; }    # always undef -> GetParam returns its default
}

no warnings 'once';
$HabitatEngine::q            = FakeCGI->new;
$HabitatEngine::OpenPageName = '';
$HabitatEngine::UserID       = 1001;
$HabitatEngine::UserData{'id'}       = 1001;
$HabitatEngine::UserData{'username'} = 'alice';

sub save_revision {
    my ( $name, $text, $minor ) = @_;
    my $P = \%{ $HabitatEngine::Pages{$name}{'page'} };
    my $S = \%{ $HabitatEngine::Pages{$name}{'section'} };
    my $T = \%{ $HabitatEngine::Pages{$name}{'text'} };
    $P->{name}     = $name;
    $P->{version}  = 3;
    $P->{tscreate} = $HabitatEngine::Now;
    $S->{name}     = 'text_default';
    $S->{ip}       = '127.0.0.1';
    $S->{host}     = 'localhost';
    $T->{text}     = $text;
    $T->{summary}  = '';
    $T->{minor}    = $minor || 0;
    $T->{newauthor} = 0;
    HabitatEngine::SavePageDB($name);
}

# ----------------------------------------------------------------
# First save: page table gets the row, page_revisions stays empty.
# ----------------------------------------------------------------
save_revision( 'Welcome', "hello world\n" );
my ( $row_count, $rev, $text ) = $dbh->selectrow_array(
    "SELECT COUNT(*), MAX(revision), MAX(text) FROM page WHERE id='Welcome'" );
is( $row_count, 1, "first save: page has 1 row" );
is( $rev,       1, "first save: revision = 1" );
is( $text,      "hello world\n", "first save: text matches" );
is(
    $dbh->selectrow_array("SELECT COUNT(*) FROM page_revisions"),
    0,
    "first save: page_revisions empty"
);

# ----------------------------------------------------------------
# Second save: revision bumps to 2; page has the new text;
# page_revisions has the old rev 1 as a snapshot.
# ----------------------------------------------------------------
HabitatHarness::freeze_time(1_700_000_100);
save_revision( 'Welcome', "hello world v2\n" );
( $row_count, $rev, $text ) = $dbh->selectrow_array(
    "SELECT COUNT(*), MAX(revision), MAX(text) FROM page WHERE id='Welcome'" );
is( $row_count, 1, "second save: still 1 page row" );
is( $rev,       2, "second save: revision bumped to 2" );
is( $text,      "hello world v2\n", "second save: text is the new version" );

my $rev_row = $dbh->selectrow_hashref(
    "SELECT * FROM page_revisions WHERE page_id='Welcome' AND revision=1" );
is( $rev_row->{kind},    'snapshot',     "historical row has kind='snapshot'" );
is( $rev_row->{text},    "hello world\n", "historical row preserves the old text" );
is( $rev_row->{author},  'alice',        "historical row keeps the author" );

# ----------------------------------------------------------------
# Third save: a deeper history with rev 3; rev 2 moves to page_revisions
# ----------------------------------------------------------------
HabitatHarness::freeze_time(1_700_000_200);
save_revision( 'Welcome', "hello world v3\n" );
my $cur = $dbh->selectrow_hashref(
    "SELECT * FROM page WHERE id='Welcome'" );
is( $cur->{revision}, 3,                "third save: page rev=3" );
is( $cur->{text},     "hello world v3\n", "third save: page has v3 text" );

my $hist = $dbh->selectall_arrayref(
    "SELECT revision, text FROM page_revisions WHERE page_id='Welcome' ORDER BY revision"
);
is_deeply(
    $hist,
    [ [ 1, "hello world\n" ], [ 2, "hello world v2\n" ] ],
    "page_revisions contains both prior versions as snapshots"
);

# ----------------------------------------------------------------
# Different pages don't bleed into each other
# ----------------------------------------------------------------
save_revision( 'OtherPage', "different content\n" );
is(
    $dbh->selectrow_array("SELECT revision FROM page WHERE id='OtherPage'"),
    1, "OtherPage starts at rev 1 independent of Welcome"
);
is(
    $dbh->selectrow_array(
        "SELECT COUNT(*) FROM page_revisions WHERE page_id='OtherPage'"),
    0, "OtherPage has no history yet"
);

# ----------------------------------------------------------------
# ReadRawWikiPage returns the current text (no inline-diff splitting)
# ----------------------------------------------------------------
%HabitatEngine::TextCache = ();    # bypass per-request cache
delete $HabitatEngine::Pages{'Welcome'}{'text'};
my $cur_text = HabitatEngine::ReadRawWikiPage('Welcome');
is( $cur_text, "hello world v3\n", "ReadRawWikiPage returns the current text" );

# ----------------------------------------------------------------
# OpenKeptListDB returns all revisions (current + history), newest first
# ----------------------------------------------------------------
$HabitatEngine::OpenPageName = 'Welcome';
my @kept = HabitatEngine::OpenKeptListDB(1);
# First element is "Internal:Offset:..." marker. Subsequent are
# $FS2-joined section blobs indexed by revision number.
my $first = shift @kept;
like( $first, qr/^Internal:Offset:/, "first element is the offset marker" );

# kept[1], [2], [3] should be defined (revisions 1, 2, 3)
ok( defined $kept[1] && $kept[1] ne '', "kept list has revision 1" );
ok( defined $kept[2] && $kept[2] ne '', "kept list has revision 2" );
ok( defined $kept[3] && $kept[3] ne '', "kept list has revision 3" );

done_testing;
