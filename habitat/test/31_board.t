#!/usr/bin/env perl
# Boards (Habitat::Board): blogs and discussion forums built from
# subpages. Covers the text formats, board activation (admin-only),
# post/reply naming and numbering (incl. collisions), permissions,
# the index/thread views with sorting and pagination, editing,
# moderation, delete, rebuild of the derived index, and that
# ..discuss pages are left alone.

use strict;
use warnings;

BEGIN { *CORE::GLOBAL::exit = sub { die "EXIT\n" }; }

use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use CGI;
use HabitatHarness;

HabitatHarness::load_wiki();
my $dbh = HabitatHarness::fresh_test_db();
HabitatHarness::set_test_secret();
HabitatHarness::freeze_time(1_700_000_000);

no warnings 'once', 'redefine';
local $SIG{__WARN__} = sub {
    return if $_[0] =~ /uninitialized|isn't numeric|CSRF check failed|redefined/;
    warn $_[0];
};
HabitatEngine::InitLinkPatterns();
$HabitatEngine::UseCaptcha = 0;
$HabitatEngine::LangID     = '';
$HabitatEngine::AdminPass  = 'adm1n';
$HabitatEngine::EditPass   = 'ed1tor';
$HabitatEngine::ScriptName = 'index.cgi';
my $real_csrf = \&HabitatEngine::CSRFCheckOrDie;
*HabitatEngine::CSRFCheckOrDie = sub { 1 };

my %HASH = (
    admin  => HabitatEngine::HashPassword('adm1n'),
    editor => HabitatEngine::HashPassword('ed1tor'),
);
our %TestPermissions;    # re-applied after each request reset
my %UID = ( alice => 1001, bob => 1002, carol => 1003, ed => 1004, root => 1005 );

sub as {
    my ($who) = @_;
    %HabitatEngine::UserData = ();
    HabitatEngine::BoardResetCache();
    if ( $who eq 'anon' ) { $HabitatEngine::UserID = 111; return; }
    $HabitatEngine::UserID = $UID{$who};
    %HabitatEngine::UserData = ( id => $UID{$who}, username => ucfirst($who) );
    $HabitatEngine::UserData{adminpw} = $HASH{editor} if ( $who eq 'ed' );
    $HabitatEngine::UserData{adminpw} = $HASH{admin}  if ( $who eq 'root' );
}

sub run {
    my ( $method, $sub, $form, @args ) = @_;
    local $ENV{REQUEST_METHOD} = $method;
    %HabitatEngine::Pages = ();
    HabitatEngine::ResetRequestState();
    %HabitatEngine::Permissions = %TestPermissions;
    HabitatEngine::BoardResetCache();
    $HabitatEngine::q = CGI->new($form);
    my $out = '';
    my $exited;
    {
        local *STDOUT;
        open( STDOUT, '>', \$out ) or die;
        eval { $sub->(@args); 1 } or do { $exited = ( $@ eq "EXIT\n" ); die $@ unless $exited };
        close STDOUT;
    }
    return wantarray ? ( $out, $exited ? 1 : 0 ) : $out;
}

sub save {    # save a page as the current user
    my ( $id, $text ) = @_;
    $HabitatEngine::q = CGI->new( {} );
    %HabitatEngine::Pages = ();
    $HabitatEngine::OpenPageName = '';
    HabitatEngine::SaveBoardPage( $id, $text, 'test' );
    HabitatEngine::BoardResetCache();
}

sub meta { HabitatEngine::BoardResetCache(); HabitatEngine::BoardMeta( $_[0] ) }
sub text_of { $dbh->selectrow_array( "SELECT text FROM page WHERE id=?", undef, $_[0] ) }

sub newpost {
    my ( $board, %f ) = @_;
    return run( 'POST', \&HabitatEngine::DoBoardNewPost, { action => 'newpost', id => $board, %f }, $board );
}

sub reply {
    my ( $thread, $text ) = @_;
    return run( 'POST', \&HabitatEngine::DoBoardReply, { action => 'reply', id => $thread, text => $text }, $thread );
}

sub mod {
    my ( $id, $op ) = @_;
    return run( 'POST', \&HabitatEngine::DoBoardModerate, { action => 'boardmod', id => $id, op => $op }, $id );
}

sub tick { $HabitatEngine::Now += 60 }

# ---------------------------------------------------------------- formats
{
    my ( $m, $body ) = HabitatEngine::ParsePostHeader("<!-- post\ntitle: Hello  \ntags: a, b\nsticky: 1\n-->\nBody\n");
    is_deeply( $m, { title => 'Hello', tags => 'a, b', sticky => 1 }, 'post header parsed' );
    is( $body, "Body\n", '  ... and removed from the body' );
    is( HabitatEngine::BuildPostHeader( { title => "A -- B\nC", tags => 'x', sticky => 0, closed => 1 } ),
        "<!-- post\ntitle: A - B C\ntags: x\nclosed: 1\n-->\n", 'header built; "--" and newlines neutralised' );
    is( HabitatEngine::BuildPostHeader( {} ), '', 'no header when nothing is set' );

    my $c = HabitatEngine::ParseBoardDirective("Intro\n<board type=forum perpage=5 post=anon>\nmore");
    is_deeply( $c, { type => 'forum', perpage => 5, post => 'anon', reply => 'user' }, 'board directive parsed with defaults' );
    is_deeply( HabitatEngine::ParseBoardDirective("<board type=blog>"),
        { type => 'blog', perpage => 10, post => 'editor', reply => 'user' }, 'blog defaults: editors post, users comment' );
    is( HabitatEngine::ParseBoardDirective("see <board> inline"), undef, 'directive must be on its own line' );
    is( HabitatEngine::ParseBoardDirective("<board post=everyone perpage=9999>")->{post}, 'user', 'unknown level -> default' );

    is( HabitatEngine::BoardSlug('Hello, World!'), 'hello-world', 'slug: ASCII' );
    is( HabitatEngine::BoardSlug("Caf\xc3\xa9 d\xc3\xa9j\xc3\xa0 vu"), 'cafe-deja-vu', 'slug: accents folded' );
    is( HabitatEngine::BoardSlug("\xe4\xb8\xad\xe6\x96\x87\xe6\xa0\x87\xe9\xa2\x98"), '', 'slug: CJK -> empty (number fallback)' );
    cmp_ok( length( HabitatEngine::BoardSlug( 'word ' x 40 ) ), '<=', 60, 'slug: at most 60 characters' );
}

# ---------------------------------------------------------------- activation
as('alice');
save( 'Forum', "Our forum\n<board type=forum perpage=2>\n" );
is( HabitatEngine::BoardConfig('Forum'), undef, 'board saved by a user is not active' );
like( run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Forum' ), qr/&lt;board type=forum/, '  ... the directive is shown as typed' );
as('root');
save( 'Forum', "Our forum\n<board type=forum perpage=2>\n" );
is_deeply( HabitatEngine::BoardConfig('Forum'), { type => 'forum', perpage => 2, post => 'user', reply => 'user' },
    'board saved by an admin is active' );
as('alice');
save( 'Forum', "Our forum (edited)\n<board type=forum perpage=2 post=anon>\n" );
is( HabitatEngine::BoardConfig('Forum')->{post}, 'user', "a user's edit of the board page leaves its settings alone" );

# ---------------------------------------------------------------- posting
as('anon');
{
    my ( $out, $ex ) = newpost( 'Forum', title => 'Spam', text => 'x' );
    ok( $ex && $out =~ /not allowed to post/, 'anonymous cannot post on a post=user board' );
}
as('alice');
like( run( 'GET', \&HabitatEngine::DoBoardNewPost, {}, 'Forum' ), qr/name="title"/, 'new-post form has a title field' );
{
    my ( $out, $ex ) = newpost( 'Forum', title => '', text => 'x' );
    ok( $ex && $out =~ /give the post a title/, 'post without a title refused' );
    ( $out, $ex ) = newpost( 'Forum', title => 'T', text => "  \n" );
    ok( $ex && $out =~ /text is empty/, 'empty post refused' );
}
my $out = newpost( 'Forum', title => 'First topic', tags => 'Perl, wiki, perl', text => "Hello *world*\n" );
like( $out, qr/Forum\/0001/, 'first forum post is Forum/0001 (redirect)' );
like( text_of('Forum/0001'), qr/\A<!-- post\ntitle: First topic\ntags: perl, wiki\n-->\nHello/, '  ... header written into the page' );
is( meta('Forum/0001')->{author_name}, 'Alice', '  ... creator recorded' );
is( meta('Forum/0001')->{tags}, ',perl,wiki,', '  ... tags normalised' );
tick();
as('bob');
newpost( 'Forum', title => 'Second', text => 'b' );
ok( text_of('Forum/0002'), 'second post is Forum/0002' );

# A page created outside the board machinery, and a claimed-but-unsaved row.
$dbh->do( "INSERT INTO page (id, revision, text, tcreate, tupdate) VALUES ('Forum/0003', 1, 'raw', 1, 1)" );
tick();
newpost( 'Forum', title => 'Third', text => 'c' );
ok( text_of('Forum/0004'), 'allocator skips an existing page (Forum/0003 -> 0004)' );
$dbh->do( "INSERT INTO pagemeta (id, board, parent, kind, seq, tcreate, tactive) VALUES ('Forum/0005','Forum','Forum','post',0,1,1)" );
tick();
newpost( 'Forum', title => 'Fourth', text => 'd' );
ok( text_of('Forum/0006'), 'allocator skips a row claimed by a concurrent post (0005 -> 0006)' );
$dbh->do("DELETE FROM pagemeta WHERE id='Forum/0005'");
$dbh->do("DELETE FROM page WHERE id='Forum/0003'");

# ---------------------------------------------------------------- replies
tick();
as('bob');
$out = reply( 'Forum/0001', "reply one\n" );
like( $out, qr/Forum\/0001&bpage=1#r0001/, 'reply redirects to its anchor' );
ok( text_of('Forum/0001/0001'), 'first reply is Forum/0001/0001' );
is( meta('Forum/0001')->{nreplies},    1,     'post reply count updated' );
is( meta('Forum/0001')->{last_author}, 'Bob', '  ... last author' );
is( meta('Forum/0001')->{tactive},     $HabitatEngine::Now, '  ... last activity' );
tick(); as('carol'); reply( 'Forum/0001', "reply two\n" );
tick(); as('bob');
reply( 'Forum/0001', "<html><script>alert(1)</script><b>bold</b></html>reply three\n" );
is( meta('Forum/0001')->{nreplies}, 3, 'three replies' );
as('anon');
{
    my ( $o, $ex ) = reply( 'Forum/0001', 'anon' );
    ok( $ex && $o =~ /not allowed to reply/, 'anonymous cannot reply on reply=user' );
    ( $o, $ex ) = reply( 'Forum', 'x' );
    ok( $ex && $o =~ /only be posted to a thread/, 'cannot reply to the board itself' );
}

# ---------------------------------------------------------------- edit rules
as('alice'); ok( HabitatEngine::UserCanEdit('Forum/0001'), 'author can edit own post' );
as('bob');   ok( !HabitatEngine::UserCanEdit('Forum/0001'), 'another user cannot' );
ok( HabitatEngine::UserCanEdit('Forum/0001/0001'), 'reply author can edit own reply' );
ok( !HabitatEngine::UserCanEdit('Forum/0099'), 'a user cannot create a board page by hand' );
as('ed');    ok( HabitatEngine::UserCanEdit('Forum/0001'), 'editor can edit any post' );
as('anon');  ok( !HabitatEngine::UserCanEdit('Forum/0001'), 'anonymous cannot edit posts' );

# postedit: title/tags form with a revision check
as('alice');
{
    my $form = run( 'GET', \&HabitatEngine::DoBoardPostEdit, {}, 'Forum/0001' );
    like( $form, qr/value="First topic"/, 'edit form prefilled with the title' );
    my ($rev) = $form =~ /name="baserev" value="(\d+)"/;
    run( 'POST', \&HabitatEngine::DoBoardPostEdit,
        { id => 'Forum/0001', baserev => $rev, title => 'First topic (edited)', tags => 'perl', text => "Hello again\n" }, 'Forum/0001' );
    is( meta('Forum/0001')->{title}, 'First topic (edited)', 'title edited through the post form' );
    like( text_of('Forum/0001'), qr/Hello again/, '  ... body too' );
    my ( $o, $ex ) = run( 'POST', \&HabitatEngine::DoBoardPostEdit,
        { id => 'Forum/0001', baserev => $rev, title => 'stale', text => "x\n" }, 'Forum/0001' );
    ok( $ex && $o =~ /changed by someone else/, 'stale edit refused' );
}
as('bob');
{
    my ( $o, $ex ) = run( 'GET', \&HabitatEngine::DoBoardPostEdit, {}, 'Forum/0001' );
    ok( $ex && $o =~ /not allowed to edit/, "edit form refused for someone else's post" );
}
# A user cannot make their post sticky through the header.
as('alice');
save( 'Forum/0001', "<!-- post\ntitle: First topic (edited)\ntags: perl\nsticky: 1\n-->\nHello again\n" );
is( meta('Forum/0001')->{sticky}, 0, "a user's sticky header is ignored" );
unlike( text_of('Forum/0001'), qr/sticky/, '  ... and removed from the saved text' );

# ---------------------------------------------------------------- views
as('anon');
{
    local $HabitatEngine::UseCache = 1;
    my $page1 = run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Forum' );
    is( $HabitatEngine::UseCache, 0, 'board index is not put in the HTML cache' );
    my @order = $page1 =~ /href="index\.cgi\?(Forum\/\d+)"/g;
    is_deeply( \@order, [ 'Forum/0001', 'Forum/0006' ], 'forum: latest activity first, 2 per page' );
    like( $page1, qr/Page 1 of 2/, '  ... with a pager' );
    my $page2 = run( 'GET', \&HabitatEngine::BrowsePage, { bpage => 2 }, 'Forum' );
    is_deeply( [ $page2 =~ /href="index\.cgi\?(Forum\/\d+)"/g ], [ 'Forum/0004', 'Forum/0002' ], '  ... page 2' );
    unlike( $page1, qr/New post/, 'no "New post" link for anonymous' );
    like( $page1, qr/Log in<\/a> to post/, '  ... but a hint to log in' );
}
as('ed');
mod( 'Forum/0002', 'sticky' );
as('anon');
{
    my @order = run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Forum' ) =~ /href="index\.cgi\?(Forum\/\d+)"/g;
    is( $order[0], 'Forum/0002', 'sticky post listed first' );
    my $tagged = run( 'GET', \&HabitatEngine::BrowsePage, { tag => 'perl' }, 'Forum' );
    is_deeply( [ $tagged =~ /href="index\.cgi\?(Forum\/\d+)"/g ], ['Forum/0001'], 'tag filter' );
}
as('alice');
{
    my $p = run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Forum' );
    like( $p, qr/action=newpost&id=Forum/, '"New post" for a user who may post' );
    my $t = run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Forum/0001' );
    like( $t, qr/<title>[^<]*First topic \(edited\)/, 'thread page titled with the post title' );
    like( $t, qr/Posted by Alice/, '  ... post info line' );
    like( $t, qr/action=postedit&id=Forum\/0001"/, '  ... "edit post" link for the author' );
    unlike( $t, qr/&lt;!-- post/, '  ... header not shown' );
    like( $t, qr/>#1<.*>#2</s, '  ... replies 1 and 2 on page 1' );
    unlike( $t, qr/reply three/, '  ... reply 3 not on page 1' );
    like( $t, qr/action=reply&id=Forum\/0001/, '  ... Reply link' );
    like( $t, qr/Back to board/, '  ... Back to board tab' );
    unlike( $t, qr/action=discuss/, '  ... no Discuss tab on a post' );
    my $t2 = run( 'GET', \&HabitatEngine::BrowsePage, { bpage => 2 }, 'Forum/0001' );
    like( $t2, qr/reply three/, 'reply 3 on thread page 2' );
    {
        as('bob');
        my ($rev) = run( 'GET', \&HabitatEngine::DoBoardPostEdit, {}, 'Forum/0001/0001' ) =~ /name="baserev" value="(\d+)"/;
        my $o = run( 'POST', \&HabitatEngine::DoBoardPostEdit, { id => 'Forum/0001/0001', baserev => $rev, text => "reply one (edited)\n" }, 'Forum/0001/0001' );
        like( $o, qr/id=Forum\/0001&bpage=1#r0001/, 'editing a reply returns to it in its thread' );
        like( text_of('Forum/0001/0001'), qr/reply one \(edited\)/, '  ... text saved' );
        as('alice');
    }
  SKIP: {
        skip 'HTML::Scrubber not installed', 1 if !eval { require HTML::Scrubber; 1 };
        unlike( $t2, qr/<script>/, "a user's raw HTML in a reply is scrubbed" );
    }
    unlike( $t, qr/action=postedit&id=Forum\/0001\/0001/, 'no edit link on replies of others' );
}

# ---------------------------------------------------------------- moderation
as('ed');
mod( 'Forum/0001', 'close' );
is( meta('Forum/0001')->{closed}, 1, 'editor closed the thread' );
is( meta('Forum/0001')->{sticky}, 0, '  ... without making it sticky' );
as('bob');
{
    my ( $o, $ex ) = reply( 'Forum/0001', 'late' );
    ok( $ex && $o =~ /not allowed to reply/, 'closed thread: users cannot reply' );
}
as('ed');
reply( 'Forum/0001', "moderator note\n" );
is( meta('Forum/0001')->{nreplies}, 4, 'closed thread: editors still can' );
as('bob');
{
    my ( $o, $ex ) = mod( 'Forum/0001', 'open' );
    ok( $ex && $o =~ /Only editors/, 'users cannot moderate' );
}
as('ed');
mod( 'Forum/0001/0002', 'delete' );
is( meta('Forum/0001')->{nreplies}, 3, 'deleting a reply lowers the count' );
ok( !text_of('Forum/0001/0002'), '  ... page gone' );
ok( $dbh->selectrow_array("SELECT COUNT(*) FROM deletedpage WHERE id='Forum/0001/0002'"), '  ... kept in deletedpage' );

# ---------------------------------------------------------------- restricted posts
{
    local %TestPermissions = ( '^Forum/0004$' => 100 );
    as('anon');
    my $idx = run( 'GET', \&HabitatEngine::BrowsePage, { bpage => 2 }, 'Forum' );
    unlike( $idx, qr/Third/, 'restricted post: title not in the board index' );
    like( $idx, qr/\(restricted\)/, '  ... shown as restricted' );
    as('bob');
    my $t = run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Forum/0004' );
    unlike( $t, qr/Third/, '  ... thread page leaks no title' );
    unlike( $t, qr/Posted by/, '  ... nor the post info' );
    as('ed');
    ok( !HabitatEngine::UserCanEdit('Forum/0004'), '  ... editors cannot edit an admin-only post' );
    my ( $o, $ex ) = run( 'GET', \&HabitatEngine::DoBoardPostEdit, {}, 'Forum/0004' );
    ok( $ex && $o =~ /not allowed to edit/, '  ... nor open its edit form' );
    as('root');
    ok( HabitatEngine::UserCanEdit('Forum/0004'), '  ... admins can' );
}

# ---------------------------------------------------------------- long CJK titles, tag characters
as('alice');
{
    my $cjk = "\xe6\xb5\x8b" x 80;    # 80 CJK characters, 240 bytes
    newpost( 'Forum', title => $cjk, tags => 'a&action=edit, b#c, d=e, f\\g', text => "cjk\n" );
    my ($sum) = $dbh->selectrow_array("SELECT summary FROM rclog ORDER BY time DESC, revision DESC LIMIT 1");
    my $copy = $sum;
    ok( utf8::decode($copy), 'summary of a long CJK post is valid UTF-8 (cut by characters)' );
    my ($pid) = $dbh->selectrow_array("SELECT id FROM pagemeta WHERE title=?", undef, $cjk);
    ok( $pid, '  ... full 80-character title kept' );
    is( meta($pid)->{tags}, ',aactionedit,bc,de,fg,', '  ... URL/LIKE characters removed from tags' ) if ($pid);
    as('ed');
    mod( $pid, 'delete' ) if ($pid);
}

# ---------------------------------------------------------------- rebuild
{
    my $q = "SELECT id, kind, parent, seq, title, tags, author_name, nreplies, sticky, closed FROM pagemeta WHERE board='Forum' ORDER BY id";
    my $before = $dbh->selectall_arrayref($q);
    $dbh->do("DELETE FROM pagemeta WHERE board='Forum' AND kind<>'board'");
    as('root');
    my ( $np, $nr ) = HabitatEngine::BoardRebuild('Forum');
    is_deeply( [ $np, $nr ], [ 4, 3 ], 'rebuild indexed 4 posts and 3 replies' );
    is_deeply( $dbh->selectall_arrayref($q), $before, '  ... rows identical to the live index (creator from revision 1)' );
}

# ---------------------------------------------------------------- blog
as('root');
save( 'Blog', "My blog\n<board type=blog perpage=10>\n" );
as('alice');
{
    my ( $o, $ex ) = newpost( 'Blog', title => 'Hi', text => 'x' );
    ok( $ex && $o =~ /not allowed to post/, 'blog: users cannot post (post=editor)' );
}
require POSIX;
my $day = POSIX::strftime( '%Y-%m-%d', localtime($HabitatEngine::Now) );
as('ed');
tick(); newpost( 'Blog', title => 'Hello World', text => "first post\n" );
ok( text_of("Blog/$day-Hello-World"), "blog post named Blog/$day-Hello-World" );
tick(); newpost( 'Blog', title => 'Hello world!', text => "again\n" );
ok( text_of("Blog/$day-Hello-World-2"), 'same slug again gets -2' );
tick(); newpost( 'Blog', title => "\xe4\xb8\xad\xe6\x96\x87", text => "cjk\n" );
ok( text_of("Blog/$day-P3"), 'title without ASCII falls back to the post number' );
is( meta("Blog/$day-P3")->{title}, "\xe4\xb8\xad\xe6\x96\x87", '  ... title kept' );
as('alice');
reply( "Blog/$day-Hello-World", "nice\n" );
ok( text_of("Blog/$day-Hello-World/0001"), 'users can comment on blog posts' );
as('anon');
{
    my $p = run( 'GET', \&HabitatEngine::BrowsePage, {}, 'Blog' );
    my @order = $p =~ /href="index\.cgi\?(Blog\/[^"#]+)"/g;
    is( $order[0], "Blog/$day-P3", 'blog: newest first' );
    like( $p, qr/first post/, '  ... excerpts shown' );
    like( $p, qr/1 comment</, '  ... comment count' );
}

# ---------------------------------------------------------------- delete thread, discuss, csrf
as('ed');
mod( 'Forum/0001', 'delete' );
ok( !text_of('Forum/0001') && !text_of('Forum/0001/0001'), 'deleting a thread deletes its replies' );
ok( !meta('Forum/0001') && !meta('Forum/0001/0001'), '  ... and their index rows' );
is_deeply( [ HabitatEngine::BoardOf('Forum..discuss') ], [], '..discuss pages are not board pages' );
is_deeply( [ HabitatEngine::BoardOf('Forum/0002..discuss') ], [], '  ... nor below a board' );
*HabitatEngine::CSRFCheckOrDie = $real_csrf;
as('alice');
{
    my ( $o, $ex ) = newpost( 'Forum', title => 'no token', text => 'x' );
    ok( $ex && $o =~ /CSRF token missing/, 'posting needs a CSRF token' );
}

done_testing;
