#
# Habitat::Board — wiki-native blogs and discussion forums.
#
# A *board* is an ordinary wiki page whose text contains a directive
#
#     <board type=forum perpage=20 post=user reply=user>
#     <board type=blog  perpage=10 post=editor reply=user>
#
# Its child pages are posts (Board/0042 for a forum, Board/2026-11-07-
# My-Title for a blog) and their children are replies/comments
# (Board/0042/0003). Every post and every reply is its own page, so each
# has its own history, permissions and edit link.
#
# Post metadata lives in the post's own text, in an optional header
#
#     <!-- post
#     title: Hello world
#     tags: perl, wiki
#     sticky: 1
#     closed: 1
#     -->
#
# which the renderer strips. The `pagemeta` table is a derived index of
# boards, posts and replies (title, creator, times, reply counts) used
# to list, sort and paginate without reading every page; it can be
# rebuilt from the pages at any time (action=boardrebuild).
#
# Trust: posting can be open to users who may not edit the wiki, so a
# board's settings only take effect when an administrator saved the
# board page (the same rule as raw HTML, admin_saved). A non-admin edit
# of a board page leaves the active settings as they were.
#
# Same package as index.cgi (see Render.pm for why).
#
package HabitatEngine;

use strict;
no strict qw(vars refs);
use warnings;
no warnings qw(once uninitialized redefine);

our %BoardCache;
our $BoardMaxText = 100000;    # characters in one post or reply

my %BOARD_LEVEL = ( anon => -1, user => 1, editor => 50, admin => 100 );
my @META_COLS   = qw(id board parent kind seq title tags author_id author_name
  tcreate tupdate tactive nreplies last_author sticky closed config);

sub BoardResetCache { %BoardCache = (); }

sub _BoardTable { return Habitat::Store::T('pagemeta'); }

# Unknown level names count as the most restrictive.
sub BoardLevel {
    my ($n) = @_;
    $n = lc( $n // '' );
    return exists $BOARD_LEVEL{$n} ? $BOARD_LEVEL{$n} : 100;
}

# ----------------------------------------------------------------
# Text formats: post header and board directive
# ----------------------------------------------------------------

# Returns (\%meta, $body). Keys are lower-case; values trimmed.
sub ParsePostHeader {
    my ($text) = @_;
    my %m;
    $text = '' if ( !defined $text );
    if ( $text =~ s/\A\s*<!--\s*post\b(.*?)-->[ \t]*\r?\n?//s ) {
        foreach my $line ( split( /\r?\n/, $1 ) ) {
            $m{ lc($1) } = $2 if ( $line =~ /^\s*([A-Za-z]+)\s*:\s*(.*?)\s*$/ );
        }
    }
    return ( \%m, $text );
}

sub BuildPostHeader {
    my ($m) = @_;
    my @lines;
    foreach my $k (qw(title tags)) {
        my $v = $m->{$k};
        next if ( !defined($v) || $v eq '' );
        $v =~ s/[\r\n]+/ /g;
        $v =~ s/-{2,}/-/g;    # never close the comment early
        push @lines, "$k: $v";
    }
    foreach my $k (qw(sticky closed)) {
        push @lines, "$k: 1" if ( $m->{$k} );
    }
    return '' if ( !@lines );
    return "<!-- post\n" . join( "\n", @lines ) . "\n-->\n";
}

# The settings of a <board ...> directive line, with defaults filled in;
# undef when the text has none.
sub ParseBoardDirective {
    my ($text) = @_;
    return undef if ( !defined($text) || $text !~ /^[ \t]*<board\b([^>\n]*)>[ \t]*$/m );
    my $attrs = $1;
    my %a;
    while ( $attrs =~ /([A-Za-z]+)\s*=\s*["']?([A-Za-z0-9]+)["']?/g ) {
        $a{ lc($1) } = lc($2);
    }
    my $type = ( ( $a{type} // '' ) eq 'blog' ) ? 'blog' : 'forum';
    my %def =
      $type eq 'blog'
      ? ( perpage => 10, post => 'editor', reply => 'user' )
      : ( perpage => 20, post => 'user',   reply => 'user' );
    my %cfg = ( type => $type );
    $cfg{perpage} =
      ( ( $a{perpage} // '' ) =~ /^\d+$/ && $a{perpage} >= 1 && $a{perpage} <= 200 )
      ? $a{perpage} + 0
      : $def{perpage};
    foreach my $k (qw(post reply)) {
        $cfg{$k} = exists $BOARD_LEVEL{ $a{$k} // '' } ? $a{$k} : $def{$k};
    }
    return \%cfg;
}

sub _BoardConfigString {
    my ($c) = @_;
    return join( ';', map { "$_=$c->{$_}" } sort keys %$c );
}

sub _BoardConfigParse {
    my ($s) = @_;
    my %c = map { split( /=/, $_, 2 ) } grep { /=/ } split( /;/, $s // '' );
    return \%c;
}

# Cut a UTF-8 byte string to at most $n characters (never mid-character:
# PostgreSQL and strict MariaDB reject broken UTF-8).
sub _BoardCut {
    my ( $t, $n ) = @_;
    return '' if ( !defined $t );
    require Encode;
    my $u = Encode::decode( 'UTF-8', $t );
    return $t if ( length($u) <= $n );
    return Encode::encode( 'UTF-8', substr( $u, 0, $n ) );
}

# Title: no control characters, at most 200 characters (not bytes).
sub _BoardCleanTitle {
    my ($t) = @_;
    return '' if ( !defined $t );
    $t =~ s/[\x00-\x1f\x7f]+/ /g;
    $t =~ s/^\s+|\s+$//g;
    return _BoardCut( $t, 200 );
}

# Tags are stored as ",a,b," so one tag matches with LIKE '%,a,%'.
sub _BoardNormTags {
    my ($t) = @_;
    require Encode;
    return '' if ( !defined($t) || $t !~ /\S/ );
    my ( %seen, @tags );
    foreach my $x ( split( /[,;]/, $t ) ) {
        $x =~ s/[\x00-\x1f\x7f%_!&#=\\]+//g;    # LIKE and URL metacharacters
        $x =~ s/^\s+|\s+$//g;
        $x = lc($x);
        push @tags, $x if ( $x ne '' && !$seen{$x}++ );
    }
    my $s = '';
    foreach my $x (@tags) {    # whole tags only, at most 80 characters in all
        last if ( length( Encode::decode( 'UTF-8', "$s$x," ) ) > 80 );
        $s .= ( $s eq '' ? ',' : '' ) . "$x,";
    }
    return $s;
}

# ASCII slug for blog post names; '' when nothing usable is left (CJK).
sub BoardSlug {
    my ($t) = @_;
    return '' if ( !defined $t );
    require Encode;
    require Unicode::Normalize;
    my $u = Encode::decode( 'UTF-8', $t );
    $u = Unicode::Normalize::NFKD($u);
    $u =~ s/\p{Mn}+//g;
    $u =~ s/[^A-Za-z0-9]+/-/g;
    $u =~ s/^-+|-+$//g;
    $u = lc($u);
    if ( length($u) > 60 ) {
        $u = substr( $u, 0, 60 );
        $u =~ s/-[^-]*$// if ( $u =~ /-/ );
    }
    return Encode::encode( 'UTF-8', $u );
}

sub _BoardLikePrefix {
    my ($s) = @_;
    $s =~ s/([!%_])/!$1/g;
    return $s;
}

# ----------------------------------------------------------------
# Index lookups
# ----------------------------------------------------------------

sub BoardMeta {
    my ($id) = @_;
    return undef if ( !defined($id) || $id eq '' || !$dbh );
    return $BoardCache{"m:$id"} if ( exists $BoardCache{"m:$id"} );
    my $mt  = _BoardTable();
    my $row = eval { $dbh->selectrow_hashref( "SELECT * FROM $mt WHERE id=?", undef, $id ) };
    if ($row) { my %r = map { lc($_) => $row->{$_} } keys %$row; $row = \%r; }
    return $BoardCache{"m:$id"} = $row;
}

# Active settings of a board page (from its pagemeta row), or undef.
sub BoardConfig {
    my ($id) = @_;
    my $m = BoardMeta($id);
    return undef if ( !$m || $m->{kind} ne 'board' );
    my $c = _BoardConfigParse( $m->{config} );
    $c->{type}    ||= 'forum';
    $c->{perpage} ||= 20;
    return $c;
}

# (board, kind, parent) when $id is a post or reply of an active board.
sub BoardOf {
    my ($id) = @_;
    return () if ( !defined($id) || $id !~ m{/} || $id =~ m{/\.} );
    return () if ( defined($DiscussSuffix) && $DiscussSuffix ne '' && $id =~ /\Q$DiscussSuffix\E$/ );
    my @p = split( m{/}, $id );
    return () if ( @p < 2 );
    my $parent = join( '/', @p[ 0 .. $#p - 1 ] );
    return ( $parent, 'post', $parent ) if ( BoardConfig($parent) );
    if ( @p >= 3 ) {
        my $gp = join( '/', @p[ 0 .. $#p - 2 ] );
        return ( $gp, 'reply', $parent ) if ( BoardConfig($gp) && !BoardConfig($parent) );
    }
    return ();
}

sub BoardTitle {
    my ($id) = @_;
    my $m = BoardMeta($id);
    return '' if ( !$m || $m->{kind} eq 'board' || !_BoardCanRead($id) );
    return ( $m && $m->{kind} ne 'board' && defined( $m->{title} ) ) ? $m->{title} : '';
}

# Title to show for a post, falling back to the last part of its name.
sub _BoardShowTitle {
    my ( $id, $title ) = @_;
    return $title if ( defined($title) && $title ne '' );
    my $n = $id;
    $n =~ s{.*/}{};
    $n =~ s/_/ /g;
    return $n;
}

# ----------------------------------------------------------------
# Permissions
# ----------------------------------------------------------------

sub _BoardCanRead {
    my ($id) = @_;
    return $BoardCache{"r:$id"} if ( exists $BoardCache{"r:$id"} );
    return $BoardCache{"r:$id"} = _BoardCanReadNow($id);
}

sub _BoardCanReadNow {
    my ($id) = @_;
    &BuildRuleStack($id);
    my $up = &UserPermission();
    return 0 if ( defined( $Pages{$id}->{'clearance'} ) && $up < $Pages{$id}->{'clearance'} );
    my $pp = ReadPagePermissions( $id, \%Permissions );
    return 0 if ( $pp ne '' && $up < $pp );
    return 1;
}

sub _BoardBlocked {
    my $up = &UserPermission();
    return 1 if ( $up <= -100 );
    return 1 if ( &GetLockState() == 1 && $up < 100 );
    return 0;
}

sub _BoardEditPermOK {
    my ($id) = @_;
    my $need = ReadPagePermissions( $id, \%EditPermissions );
    return ( $need ne '' && &UserPermission() < $need ) ? 0 : 1;
}

sub BoardCanPost {
    my ($board) = @_;
    my $c = BoardConfig($board) or return 0;
    return 0 if ( _BoardBlocked() );
    return 0 if ( !_BoardEditPermOK("$board/0000") );
    return 0 if ( !_BoardCanRead($board) );
    return ( &UserPermission() >= BoardLevel( $c->{post} ) ) ? 1 : 0;
}

sub BoardCanReply {
    my ($thread) = @_;
    my ( $board, $kind ) = BoardOf($thread);
    return 0 if ( !$board || $kind ne 'post' );
    my $m = BoardMeta($thread) or return 0;
    return 0 if ( _BoardBlocked() );
    return 0 if ( $m->{closed} && &UserPermission() < 50 );
    return 0 if ( &IsPageLocked($thread) && !&UserIsAdmin() );
    return 0 if ( !_BoardEditPermOK("$thread/0000") );
    return 0 if ( !_BoardCanRead($thread) );
    return ( &UserPermission() >= BoardLevel( BoardConfig($board)->{reply} ) ) ? 1 : 0;
}

sub BoardIsModerator { return ( &UserPermission() >= 50 ) ? 1 : 0; }

# Edit rule for board posts/replies (used by UserCanEdit): editors and
# admins may edit any; a registered user only what they created. undef
# when $id is not part of a board (normal wiki rules apply).
sub BoardEditRule {
    my ($id) = @_;
    my ($board) = BoardOf($id);
    return undef if ( !$board );
    my $up = &UserPermission();
    return 0 if ( $up <= -100 );
    return 0 if ( !_BoardCanRead($id) );    # restricted pages stay restricted
    return 1 if ( $up >= 50 );
    my $m = BoardMeta($id) or return 0;
    return ( $UserID > 1000 && $m->{author_id} && $m->{author_id} == $UserID ) ? 1 : 0;
}

# ----------------------------------------------------------------
# Index maintenance
# ----------------------------------------------------------------

sub _BoardInsertRow {
    my (%r) = @_;
    my $mt = _BoardTable();
    $r{$_} //= 0 for qw(seq nreplies sticky closed author_id tupdate);
    $r{$_} //= '' for qw(title tags author_name last_author config parent board);
    return eval {
        local $dbh->{RaiseError} = 1;
        local $dbh->{PrintError} = 0;
        $dbh->do(
            "INSERT INTO $mt (" . join( ',', @META_COLS ) . ") VALUES (" . join( ',', ('?') x @META_COLS ) . ")",
            undef, map { $r{$_} } @META_COLS
        );
        1;
    } ? 1 : 0;
}

sub _BoardUpdateRow {
    my ( $id, %set ) = @_;
    return if ( !%set );
    my $mt   = _BoardTable();
    my @cols = sort keys %set;
    $dbh->do( "UPDATE $mt SET " . join( ',', map { "$_=?" } @cols ) . " WHERE id=?",
        undef, ( map { $set{$_} } @cols ), $id );
}

# Recount a post's replies; with $touch also mark new activity.
sub _BoardRecount {
    my ( $post, $touch, $who ) = @_;
    my $mt = _BoardTable();
    my ($n) = $dbh->selectrow_array( "SELECT COUNT(*) FROM $mt WHERE parent=? AND kind='reply'", undef, $post );
    my %set = ( nreplies => $n || 0 );
    if ($touch) {
        $set{tactive}     = $Now;
        $set{last_author} = $who // '';
    }
    _BoardUpdateRow( $post, %set );
}

sub _BoardCreatorName {
    return ( $UserID > 1000 && defined( $UserData{'username'} ) ) ? $UserData{'username'} : '';
}

# Called by SavePageDB before it writes a page: on a board post saved by
# someone who is not an editor, the sticky/closed lines of the header are
# reset to the indexed values, so the text never claims what the saver
# could not set (it is what a rebuild reads back).
sub BoardFixHeader {
    my ( $id, $text ) = @_;
    my $out = eval {
        my ( $board, $kind ) = BoardOf($id);
        return $text if ( !$board || $kind ne 'post' || BoardIsModerator() );
        my $idx = BoardMeta($id) || {};
        my ( $m, $body ) = ParsePostHeader($text);
        return $text if ( ( $m->{sticky} ? 1 : 0 ) == ( $idx->{sticky} ? 1 : 0 )
            && ( $m->{closed} ? 1 : 0 ) == ( $idx->{closed} ? 1 : 0 ) );
        $m->{sticky} = $idx->{sticky} ? 1 : 0;
        $m->{closed} = $idx->{closed} ? 1 : 0;
        return BuildPostHeader($m) . $body;
    };
    return defined($out) ? $out : $text;
}

# Called by SavePageDB after every save.
sub BoardAfterSave {
    my @args = @_;
    eval { _BoardAfterSave(@args); 1 } or warn "board index: $args[0]: $@";
    BoardResetCache();
}

sub _BoardAfterSave {
    my ( $id, $text, $prevrev, $admin_saved ) = @_;
    return if ( !$dbh );
    BoardResetCache();
    my $mt = _BoardTable();
    my ( $board, $kind, $parent ) = BoardOf($id);

    if ( !$board ) {

        # Maybe a board page. Only an administrator's save changes it.
        return if ( !$admin_saved );
        my $cfg = ParseBoardDirective($text);
        my $had = BoardMeta($id);
        if ($cfg) {
            my $cs = _BoardConfigString($cfg);
            if ( $had && $had->{kind} eq 'board' ) {
                _BoardUpdateRow( $id, config => $cs, tupdate => $Now );
            } elsif ( !$had ) {
                _BoardInsertRow(
                    id      => $id, board => $id, parent => '', kind => 'board',
                    tcreate => $Now, tupdate => $Now, tactive => $Now, config => $cs
                );
                BoardResetCache();
                BoardRebuild($id);    # index pages already below it
                my $htmldb = DBTable($HtmlDir);    # cached child pages lack the thread view
                DeleteDBItems( $htmldb, "id LIKE ? ESCAPE '!'", _BoardLikePrefix($id) . '/%' ) if ( SafeIdent($htmldb) );
            }
        } elsif ( $had && $had->{kind} eq 'board' ) {
            $dbh->do( "DELETE FROM $mt WHERE id=?", undef, $id );    # board switched off
        }
        return;
    }

    my ($m) = ParsePostHeader($text);
    my $row = BoardMeta($id);
    my %set = (
        title   => _BoardCleanTitle( $m->{title} ),
        tags    => _BoardNormTags( $m->{tags} ),
        tupdate => $Now,
    );
    if ( BoardIsModerator() ) {    # sticky/closed only from editors
        $set{sticky} = $m->{sticky} ? 1 : 0;
        $set{closed} = $m->{closed} ? 1 : 0;
    }
    if ($row) {
        _BoardUpdateRow( $id, %set );
    } else {
        my ($seq) = ( $id =~ m{/(\d+)$} );
        if ( !$seq ) {
            ($seq) = $dbh->selectrow_array( "SELECT MAX(seq) FROM $mt WHERE parent=? AND kind=?", undef, $parent, $kind );
            $seq = ( $seq || 0 ) + 1;
        }
        _BoardInsertRow(
            %set,
            id          => $id,
            board       => $board,
            parent      => $parent,
            kind        => $kind,
            seq         => $seq,
            author_id   => ( $UserID > 1000 ? $UserID : 0 ),
            author_name => _BoardCreatorName(),
            tcreate     => $Now,
            tactive     => $Now,
        );
    }
    _BoardRecount( $parent, 1, _BoardCreatorName() ) if ( $kind eq 'reply' && !$prevrev );
}

# Called after a page was deleted.
sub BoardForget {
    my ($id) = @_;
    return if ( !$dbh );
    eval {
        my $m = BoardMeta($id);
        if ($m) {
            my $mt = _BoardTable();
            $dbh->do( "DELETE FROM $mt WHERE id=?", undef, $id );
            _BoardRecount( $m->{parent}, 0 ) if ( $m->{kind} eq 'reply' );
            $dbh->do( "DELETE FROM $mt WHERE parent=? AND kind='reply'", undef, $id ) if ( $m->{kind} eq 'post' );
            $dbh->do( "DELETE FROM $mt WHERE board=?", undef, $id ) if ( $m->{kind} eq 'board' );
        }
        1;
    } or warn "board index: forget $id: $@";
    BoardResetCache();
}

# Called after RenamePage moved a page.
sub BoardRenamed {
    my ( $old, $new ) = @_;
    return if ( !$dbh );
    BoardForget($old);
    eval { _BoardIndexPage($new); 1 } or warn "board index: rename $old: $@";
    BoardResetCache();
}

# Index one existing page from its stored rows (rebuild, rename).
sub _BoardIndexPage {
    my ($id) = @_;
    my ( $board, $kind, $parent ) = BoardOf($id);
    return 0 if ( !$board );
    my $pagedb = &GetPageDB($id);
    return 0 if ( !SafeIdent($pagedb) || !SafeIdent("${pagedb}_revisions") );
    my $p = $dbh->selectrow_hashref( "SELECT text, author, data, tcreate, tupdate FROM $pagedb WHERE id=?", undef, $id );
    return 0 if ( !$p );
    my %p = map { lc($_) => $p->{$_} } keys %$p;

    # The creator is whoever saved the first revision.
    my $first = $dbh->selectrow_hashref(
        "SELECT author, data, tupdate FROM ${pagedb}_revisions WHERE page_id=? ORDER BY revision LIMIT 1",
        undef, $id );
    my %f = $first ? ( map { lc($_) => $first->{$_} } keys %$first ) : ( author => $p{author}, data => $p{data} );
    my ($m) = ParsePostHeader( $p{text} );
    my ($seq) = ( $id =~ m{/(\d+)$} );
    if ( !$seq ) {
        my $mt = _BoardTable();
        ($seq) = $dbh->selectrow_array( "SELECT MAX(seq) FROM $mt WHERE parent=? AND kind=?", undef, $parent, $kind );
        $seq = ( $seq || 0 ) + 1;
    }
    $dbh->do( "DELETE FROM " . _BoardTable() . " WHERE id=?", undef, $id );
    _BoardInsertRow(
        id          => $id,
        board       => $board,
        parent      => $parent,
        kind        => $kind,
        seq         => $seq,
        title       => _BoardCleanTitle( $m->{title} ),
        tags        => _BoardNormTags( $m->{tags} ),
        author_id   => ( ( $f{data} // '' ) =~ /^\d+$/ && $f{data} >= 1000 ) ? $f{data} : 0,
        author_name => $f{author} // '',
        tcreate     => $p{tcreate} || $p{tupdate} || $Now,
        tupdate     => $p{tupdate} || $Now,
        tactive     => $p{tcreate} || $p{tupdate} || $Now,
        sticky      => $m->{sticky} ? 1 : 0,
        closed      => $m->{closed} ? 1 : 0,
    );
    BoardResetCache();
    return 1;
}

# Re-derive every post/reply row of a board from its pages.
# Returns (posts, replies).
sub BoardRebuild {
    my ($board) = @_;
    return ( 0, 0 ) if ( !BoardConfig($board) );
    my $mt     = _BoardTable();
    my $pagedb = &GetPageDB("$board/x");
    return ( 0, 0 ) if ( !SafeIdent($pagedb) );
    my %keep = map { $_->[0] => [ $_->[1], $_->[2] ] }
      @{ $dbh->selectall_arrayref( "SELECT id, sticky, closed FROM $mt WHERE board=? AND kind='post'", undef, $board ) };
    $dbh->do( "DELETE FROM $mt WHERE board=? AND kind<>'board'", undef, $board );
    BoardResetCache();
    my $ids = $dbh->selectcol_arrayref( "SELECT id FROM $pagedb WHERE id LIKE ? ESCAPE '!'",
        undef, _BoardLikePrefix($board) . '/%' );
    my ( @posts, @replies );
    foreach my $id ( sort @$ids ) {
        my $rest = substr( $id, length($board) + 1 );
        my @s    = split( m{/}, $rest );
        next if ( grep { /^\./ || $_ eq '' } @s );
        next if ( defined($DiscussSuffix) && $DiscussSuffix ne '' && $id =~ /\Q$DiscussSuffix\E$/ );
        push @posts,   $id if ( @s == 1 );
        push @replies, $id if ( @s == 2 );
    }
    my ( $np, $nr ) = ( 0, 0 );
    foreach my $id (@posts) {
        next if ( BoardConfig($id) );    # a nested board is not a post
        next if ( !_BoardIndexPage($id) );
        $np++;
        _BoardUpdateRow( $id, sticky => $keep{$id}[0] || 0, closed => $keep{$id}[1] || 0 ) if ( $keep{$id} );
    }
    foreach my $id (@replies) { $nr += _BoardIndexPage($id); }

    # Reply counts and last activity of every post.
    my $posts = $dbh->selectcol_arrayref( "SELECT id FROM $mt WHERE board=? AND kind='post'", undef, $board );
    foreach my $pid (@$posts) {
        my $last = $dbh->selectrow_arrayref(
            "SELECT tcreate, author_name FROM $mt WHERE parent=? AND kind='reply' ORDER BY tcreate DESC, seq DESC LIMIT 1",
            undef, $pid );
        my ($n) = $dbh->selectrow_array( "SELECT COUNT(*) FROM $mt WHERE parent=? AND kind='reply'", undef, $pid );
        my %set = ( nreplies => $n || 0 );
        if ($last) { $set{tactive} = $last->[0]; $set{last_author} = $last->[1] // ''; }
        _BoardUpdateRow( $pid, %set );
    }
    BoardResetCache();
    return ( $np, $nr );
}

# Claim a new post/reply name. The INSERT into pagemeta (primary key id)
# is the atomic step: page saves are upserts and RequestLock is a no-op,
# so two simultaneous posts can only be told apart here.
sub BoardAllocateId {
    my ( $board, $kind, $parent, $title ) = @_;
    my $cfg = BoardConfig($board) or return ();
    my $mt  = _BoardTable();
    my ($max) = $dbh->selectrow_array( "SELECT MAX(seq) FROM $mt WHERE parent=? AND kind=?", undef, $parent, $kind );
    my $seq = ( $max || 0 ) + 1;
    my $base;
    if ( $kind eq 'post' && $cfg->{type} eq 'blog' ) {
        require POSIX;
        my $date = POSIX::strftime( '%Y-%m-%d', localtime($Now) );
        my $slug = BoardSlug($title);
        $base = &FreeToNormal( "$parent/$date-" . ( $slug ne '' ? $slug : "p$seq" ) );
        $base = &FreeToNormal("$parent/$date-p$seq") if ( &ValidId($base) ne '' || length($base) > 110 );
    }
    for my $try ( 0 .. 49 ) {
        my ( $id, $s );
        if ( defined $base ) {
            ( $id, $s ) = ( $try ? "$base-" . ( $try + 1 ) : $base, $seq );
        } else {
            $s  = $seq + $try;
            $id = sprintf( "%s/%04d", $parent, $s );
        }
        next if ( &ValidId($id) ne '' || length($id) > 120 );
        next if ( &PageExists($id) );
        my $ok = _BoardInsertRow(
            id          => $id,
            board       => $board,
            parent      => $parent,
            kind        => $kind,
            seq         => $s,
            title       => _BoardCleanTitle($title),
            author_id   => ( $UserID > 1000 ? $UserID : 0 ),
            author_name => _BoardCreatorName(),
            tcreate     => $Now,
            tupdate     => $Now,
            tactive     => $Now,
        );
        BoardResetCache();
        return ( $id, $s ) if ($ok);
    }
    return ();
}

# Save a board page as the current user, like DoPost's save step.
sub SaveBoardPage {
    my ( $id, $text, $summary ) = @_;
    $text = &RemoveFS($text);
    $text =~ s/\r\n?/\n/g;
    $text .= "\n" if ( $text !~ /\n\z/ );
    $summary = &RemoveFS( $summary // '' );
    $summary =~ s/[\r\n]+/ /g;
    $summary = _BoardCut( $summary, 100 );

    &BuildRuleStack($id);
    $text = &ApplyRegExp( $id, $text, \%NameSpaceE1, $Pages{$id}->{'postedit'} );    # as DoPost
    $text =~ s/<userip>/$ENV{'REMOTE_ADDR'}/gi;
    &OpenDefaultPage($id);
    $OpenPageName = $id;
    my $Section = \%{ $Pages{$id}->{'section'} };
    my $Text    = \%{ $Pages{$id}->{'text'} };
    $$Text{'text'}      = $text;
    $$Text{'minor'}     = 0;
    $$Text{'newauthor'} = 1;
    $$Text{'summary'}   = $summary;
    $$Section{'host'}   = &GetRemoteHost(1);
    &SaveDefaultText($id);
    my $pgmode = $Pages{$id}->{'clearance'} // 0;
    &SavePageDB($id);
    &WriteRcLogDB( $id, $summary, 0, $Now, $$Section{'revision'}, $UserData{'username'} // '',
        $$Section{'host'}, $pgmode );
    AddUserLogDB( $UserID, 'Wr', $id ) if ( $UserID >= 1000 );

    # The page, its thread and its board list it; drop cached copies.
    my $htmldb = DBTable($HtmlDir);
    if ( SafeIdent($htmldb) ) {
        my ( $board, $kind, $parent ) = BoardOf($id);
        foreach my $p ( grep { defined && $_ ne '' } ( $id, $parent, $board ) ) {
            DeleteDBItems( $htmldb, "id LIKE ?", "$p\[%\]" );
        }
    }
}

# ----------------------------------------------------------------
# HTML
# ----------------------------------------------------------------

sub _BoardCss {
    return '' if ( $BoardCache{css}++ );
    return <<'CSS';
<style type="text/css">
.wikiboard{width:100%;border-collapse:collapse;margin:8px 0}
.wikiboard th,.wikiboard td{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}
.wikiboard td.num{text-align:right;white-space:nowrap}
.wikiboardsticky td{background:#fffbe6}
.wikiboardtools{margin:8px 0}
.wikiboardtools form{display:inline}
.wikiboardpager{margin:8px 0}
.wikiblogpost{margin:0 0 18px 0}
.wikiblogpost h3{margin:0 0 2px 0}
.wikipostinfo,.wikiboardsmall{color:#666;font-size:90%}
.wikireply{border-top:1px solid #ddd;padding:6px 0;margin:6px 0}
.wikireplyhead{color:#666;font-size:90%;margin-bottom:4px}
.wikiboardform input[type=text]{width:60%}
.wikiboardform textarea{width:100%}
</style>
CSS
}

sub _BoardDate {
    my ($t) = @_;
    return $t ? &TimeToText($t) : '';
}

sub _BoardWho {
    my ($n) = @_;
    return ( defined($n) && $n ne '' ) ? &QuoteHtml($n) : T('anonymous');
}

sub _BoardCount {
    my ( $n, $one, $many ) = @_;
    return ( $n || 0 ) == 1 ? T($one) : Ts( $many, $n || 0 );
}

# Hint for visitors who could act after logging in.
sub _BoardLoginHint {
    my ( $level, $what ) = @_;
    return '' if ( $UserID >= 1000 || &UserPermission() >= BoardLevel($level) );
    return "<p class='wikiboardsmall'>" . &ScriptLink( 'action=login', T('Log in') ) . ' ' . $what . "</p>";
}

# Thread page on which reply number $seq appears.
sub _BoardReplyPage {
    my ( $thread, $seq, $per ) = @_;
    my ($pos) = $dbh->selectrow_array( "SELECT COUNT(*) FROM " . _BoardTable() . " WHERE parent=? AND kind='reply' AND seq<=?",
        undef, $thread, $seq );
    return int( ( ( $pos || 1 ) + $per - 1 ) / $per ) || 1;
}

sub _BoardPageNum {
    my $p = &GetParam( 'bpage', 1 );
    return ( $p =~ /^\d{1,6}$/ && $p >= 1 ) ? $p + 0 : 1;
}

sub _BoardPager {
    my ( $base, $page, $pages ) = @_;
    return '' if ( $pages <= 1 );
    my @l;
    push @l, &ScriptLink( "$base&bpage=" . ( $page - 1 ), T('Previous') ) if ( $page > 1 );
    push @l, Tss( 'Page %1 of %2', $page, $pages );
    push @l, &ScriptLink( "$base&bpage=" . ( $page + 1 ), T('Next') ) if ( $page < $pages );
    return "<div class='wikiboardpager'>" . join( ' | ', @l ) . "</div>";
}

# A short plain-text excerpt of a post body.
sub _BoardExcerpt {
    my ( $text, $max ) = @_;
    my ( undef, $body ) = ParsePostHeader($text);
    $body =~ s/\A\s*<!--\s*markdown\s*-->\s*//i;
    $body =~ s/<[^>]*>//g;
    $body =~ s/\[\[(?:[^\]|]*\|)?([^\]]*)\]\]/$1/g;
    $body =~ s/\[\S+\s+([^\]]*)\]/$1/g;
    $body =~ s/'{2,}//g;
    $body =~ s/^[=*#:;!]+\s*//mg;
    $body =~ s/\s+/ /g;
    $body =~ s/^\s+|\s+$//g;
    require Encode;
    my $u = Encode::decode( 'UTF-8', $body );
    $u = substr( $u, 0, $max ) . '...' if ( length($u) > $max );
    return &QuoteHtml( Encode::encode( 'UTF-8', $u ) );
}

sub _BoardPostForm {
    my (%o) = @_;    # action id title tags text sticky closed baserev submit withtitle
    my $h = _BoardCss() . "<div class='wikiboardform'>" . &GetFormStart();
    $h .= _BoardHidden( 'action', $o{action} ) . _BoardHidden( 'id', $o{id} );
    $h .= _BoardHidden( 'baserev', $o{baserev} ) if ( defined $o{baserev} );
    if ( $o{withtitle} ) {
        $h .= "<p><label>" . T('Title:') . "</label><br/>"
          . $q->textfield( -name => 'title', -value => $o{title} // '', -size => 60, -maxlength => 200, -override => 1 )
          . "</p><p><label>" . T('Tags (comma separated):') . "</label><br/>"
          . $q->textfield( -name => 'tags', -value => $o{tags} // '', -size => 60, -maxlength => 200, -override => 1 )
          . "</p>";
    }
    if ( $o{moderate} ) {
        $h .= "<p>"
          . $q->checkbox( -name => 'sticky', -checked => $o{sticky} ? 1 : 0, -value => 1, -label => T('Sticky (listed first)'), -override => 1 )
          . ' '
          . $q->checkbox( -name => 'closed', -checked => $o{closed} ? 1 : 0, -value => 1, -label => T('Closed (no new replies)'), -override => 1 )
          . "</p>";
    }
    $h .= "<p>"
      . $q->textarea( -name => 'text', -default => $o{text} // '', -rows => 18, -cols => 80, -override => 1 )
      . "</p>";
    $h .= "<p>" . &PrintCaptcha() . "</p>" if ( $UseCaptcha && &UserPermission() < 50 );
    $h .= $q->submit( -name => 'Save', -value => $o{submit} || T('Save') );
    $h .= $q->end_form . "</div>";
    return $h;
}

# Expansion of the <board> directive on the board page.
sub BoardIndexHtml {
    my ($board) = @_;
    $UseCache = 0;
    my $cfg = BoardConfig($board);
    if ( !$cfg ) {
        return "<div class='wikiinfo'>"
          . T('This board is not active yet: an administrator has to save this page.') . "</div>";
    }
    my $mt   = _BoardTable();
    my $per  = $cfg->{perpage};
    my $page = _BoardPageNum();
    my $tag  = &GetParam( 'tag', '' );
    $tag = lc($tag);
    $tag = '' if ( $tag =~ /[%_!,&#=\\\x00-\x1f]/ || length($tag) > 50 );
    my $where = "board=? AND kind='post'";
    my @bind  = ($board);
    if ( $tag ne '' ) { $where .= " AND tags LIKE ? ESCAPE '!'"; push @bind, "%,$tag,%"; }
    my ($n) = $dbh->selectrow_array( "SELECT COUNT(*) FROM $mt WHERE $where", undef, @bind );
    my $pages = int( ( $n + $per - 1 ) / $per ) || 1;
    $page = $pages if ( $page > $pages );
    my $off   = int( ( $page - 1 ) * $per );
    my $order = $cfg->{type} eq 'blog' ? 'sticky DESC, tcreate DESC, seq DESC' : 'sticky DESC, tactive DESC, seq DESC';
    my $rows  = $dbh->selectall_arrayref(
        "SELECT id, title, author_name, tcreate, tactive, nreplies, last_author, sticky, closed, tags "
          . "FROM $mt WHERE $where ORDER BY $order LIMIT " . int($per) . " OFFSET $off",
        { Slice => {} }, @bind );

    my $h = _BoardCss();
    my @tools;
    push @tools, &ScriptLinkClass( "action=newpost&id=$board", T('New post'), 'icon-plus' ) if ( BoardCanPost($board) );
    if ( $tag ne '' ) {
        push @tools, Ts( 'Tag: %s', &QuoteHtml($tag) ) . ' (' . &ScriptLink( "action=browse&id=$board", T('show all') ) . ')';
    }
    $h .= "<div class='wikiboardtools'>" . join( ' | ', @tools ) . "</div>" if (@tools);

    $h .= _BoardLoginHint( $cfg->{post}, T('to post.') ) if ( !BoardCanPost($board) );
    if ( !@$rows ) {
        $h .= "<p class='wikiboardsmall'>" . T('No posts yet.') . "</p>";
    } elsif ( $cfg->{type} eq 'blog' ) {
        foreach my $r (@$rows) {
            my %r = map { lc($_) => $r->{$_} } keys %$r;
            if ( !_BoardCanRead( $r{id} ) ) { $h .= "<div class='wikiblogpost wikiboardsmall'>" . T('(restricted)') . "</div>"; next; }
            my $title = &QuoteHtml( _BoardShowTitle( $r{id}, $r{title} ) );
            $h .= "<div class='wikiblogpost'><h3>" . &ScriptLinkClass( $r{id}, $title, 'wikipagelink' ) . "</h3>";
            $h .= "<div class='wikipostinfo'>" . _BoardDate( $r{tcreate} ) . ' &middot; ' . _BoardWho( $r{author_name} );
            $h .= ' &middot; ' . &ScriptLink( "$r{id}#replies", _BoardCount( $r{nreplies}, '1 comment', '%s comments' ) );
            $h .= ' &middot; ' . _BoardTagLinks( $board, $r{tags} ) if ( $r{tags} ne '' );
            $h .= "</div><p>" . _BoardExcerpt( &ReadRawWikiPage( $r{id} ), 300 ) . "</p></div>";
        }
    } else {
        $h .= "<table class='wikiboard'><tr><th>" . T('Topic') . "</th><th>" . T('Started by')
          . "</th><th class='num'>" . T('Replies') . "</th><th>" . T('Last activity') . "</th></tr>";
        foreach my $r (@$rows) {
            my %r = map { lc($_) => $r->{$_} } keys %$r;
            if ( !_BoardCanRead( $r{id} ) ) { $h .= "<tr><td colspan='4' class='wikiboardsmall'>" . T('(restricted)') . "</td></tr>"; next; }
            my $title = &QuoteHtml( _BoardShowTitle( $r{id}, $r{title} ) );
            my $flags = ( $r{sticky} ? '[' . T('sticky') . '] ' : '' ) . ( $r{closed} ? '[' . T('closed') . '] ' : '' );
            $h .= "<tr" . ( $r{sticky} ? " class='wikiboardsticky'" : '' ) . "><td>$flags"
              . &ScriptLinkClass( $r{id}, $title, 'wikipagelink' )
              . ( $r{tags} ne '' ? "<br/><span class='wikiboardsmall'>" . _BoardTagLinks( $board, $r{tags} ) . "</span>" : '' )
              . "</td><td>" . _BoardWho( $r{author_name} ) . "<br/><span class='wikiboardsmall'>"
              . _BoardDate( $r{tcreate} ) . "</span></td><td class='num'>" . ( $r{nreplies} || 0 )
              . "</td><td>" . _BoardDate( $r{tactive} )
              . ( $r{nreplies} ? "<br/><span class='wikiboardsmall'>" . _BoardWho( $r{last_author} ) . "</span>" : '' )
              . "</td></tr>";
        }
        $h .= "</table>";
    }
    my $base = "action=browse&id=$board" . ( $tag ne '' ? "&tag=$tag" : '' );
    $h .= _BoardPager( $base, $page, $pages );
    if ( &UserIsAdmin() ) {
        $h .= "<div class='wikiboardtools'>" . &GetFormStart()
          . _BoardHidden( 'action', 'boardrebuild' ) . _BoardHidden( 'id', $board )
          . $q->submit( -name => 'Rebuild', -value => T('Rebuild board index') ) . $q->end_form . "</div>";
    }
    return $h;
}

sub _BoardTagLinks {
    my ( $board, $tags ) = @_;
    return join( ', ',
        map { &ScriptLink( "action=browse&id=$board&tag=$_", &QuoteHtml($_) ) } grep { $_ ne '' } split( /,/, $tags // '' ) );
}

# Line above a post or reply: author, date, board/thread links.
sub BoardPostInfoHtml {
    my ($id) = @_;
    my ( $board, $kind, $parent ) = BoardOf($id);
    return '' if ( !$board || !_BoardCanRead($id) );
    my $m = BoardMeta($id) or return '';
    $UseCache = 0;
    my $h = _BoardCss() . "<div class='wikipostinfo'>";
    $h .= Ts( 'Posted by %s', _BoardWho( $m->{author_name} ) ) . ' &middot; ' . _BoardDate( $m->{tcreate} );
    if ( $kind eq 'post' ) {
        $h .= ' &middot; ' . T('in') . ' ' . &ScriptLinkClass( $board, &QuoteHtml($board), 'wikipagelink' );
        $h .= ' &middot; ' . _BoardTagLinks( $board, $m->{tags} ) if ( $m->{tags} ne '' );
        $h .= ' &middot; <b>' . T('closed') . '</b>' if ( $m->{closed} );
        $h .= ' &middot; ' . &ScriptLink( "action=postedit&id=$id", T('edit post') ) if ( &UserCanEdit($id) );
    } else {
        my $pm = BoardMeta($parent);
        $h .= ' &middot; ' . T('reply to') . ' '
          . &ScriptLinkClass( $parent, &QuoteHtml( _BoardShowTitle( $parent, $pm ? $pm->{title} : '' ) ), 'wikipagelink' );
    }
    return $h . "</div>";
}

# Replies below a post, paginated, each rendered from its own page.
sub BoardThreadHtml {
    my ($id) = @_;
    my ( $board, $kind ) = BoardOf($id);
    return '' if ( !$board || $kind ne 'post' || !_BoardCanRead($id) );
    $UseCache = 0;
    my $cfg  = BoardConfig($board);
    my $m    = BoardMeta($id) or return '';
    my $mt   = _BoardTable();
    my $per  = $cfg->{perpage};
    my $n    = $m->{nreplies} || 0;
    my $pages = int( ( $n + $per - 1 ) / $per ) || 1;
    my $page = _BoardPageNum();
    $page = $pages if ( $page > $pages );
    my $off  = int( ( $page - 1 ) * $per );
    my $rows = $dbh->selectall_arrayref(
        "SELECT id, seq, author_name, tcreate FROM $mt WHERE parent=? AND kind='reply' ORDER BY seq LIMIT " . int($per) . " OFFSET $off",
        undef, $id );

    my $h = _BoardCss() . "<div class='wikithread' id='replies'><h3>"
      . _BoardCount( $n, '1 reply', '%s replies' ) . "</h3>";
    $h .= _BoardModTools( $id, $m ) if ( BoardIsModerator() );
    foreach my $r (@$rows) {
        my ( $rid, $seq, $who, $t ) = @$r;
        my $anchor = sprintf( 'r%04d', $seq );
        if ( !_BoardCanRead($rid) ) {
            $h .= "<div class='wikireply' id='$anchor'><div class='wikireplyhead'>#$seq &middot; " . T('(restricted)') . "</div></div>";
            next;
        }
        &OpenDefaultPage($rid);
        my $text = $Pages{$rid}->{'text'}->{'text'};
        my $toc  = $TableOfContents;
        my $body = &WikiToHTML( $rid, $text );
        $TableOfContents = $toc;
        $h .= "<div class='wikireply' id='$anchor'><div class='wikireplyhead'>"
          . "<a href='#$anchor'>#$seq</a> &middot; " . _BoardWho($who) . ' &middot; ' . _BoardDate($t);
        $h .= ' &middot; ' . &ScriptLink( "action=postedit&id=$rid", T('edit') ) if ( &UserCanEdit($rid) );
        $h .= ' &middot; ' . &ScriptLink( $rid, T('permalink') );
        $h .= _BoardDeleteButton($rid) if ( BoardIsModerator() );
        $h .= "</div>$body</div>";
    }
    $h .= _BoardPager( "action=browse&id=$id", $page, $pages );
    if ( BoardCanReply($id) ) {
        $h .= "<div class='wikiboardtools'>" . &ScriptLinkClass( "action=reply&id=$id", T('Reply'), 'icon-comments' ) . "</div>";
    } elsif ( $m->{closed} ) {
        $h .= "<p class='wikiboardsmall'>" . T('This thread is closed.') . "</p>";
    } else {
        $h .= _BoardLoginHint( $cfg->{reply}, T('to reply.') );
    }
    return $h . "</div>";
}

sub _BoardHidden {
    my ( $n, $v ) = @_;
    return $q->hidden( -name => $n, -default => $v, -override => 1 );
}

sub _BoardModButton {
    my ( $id, $op, $label ) = @_;
    return &GetFormStart() . _BoardHidden( 'action', 'boardmod' ) . _BoardHidden( 'id', $id )
      . _BoardHidden( 'op', $op ) . $q->submit( -name => 'Do', -value => $label ) . $q->end_form;
}

sub _BoardDeleteButton {
    my ($id) = @_;
    return ' ' . _BoardModButton( $id, 'delete', T('delete') );
}

sub _BoardModTools {
    my ( $id, $m ) = @_;
    return "<div class='wikiboardtools'>"
      . _BoardModButton( $id, $m->{sticky} ? 'unsticky' : 'sticky', $m->{sticky} ? T('Unstick') : T('Make sticky') ) . ' '
      . _BoardModButton( $id, $m->{closed} ? 'open' : 'close', $m->{closed} ? T('Reopen') : T('Close thread') ) . ' '
      . _BoardModButton( $id, 'delete', T('Delete thread') ) . "</div>";
}

# Tabs in the page header (GetHeader).
sub BoardHeaderTabs {
    my ($id) = @_;
    my $h = '';
    if ( BoardConfig($id) ) {
        $h .= "<li class='inactivetab'>" . &ScriptLinkClass( "action=newpost&id=$id", T('New post'), 'icon-plus', T('New post') ) . "</li>"
          if ( BoardCanPost($id) );
        return $h;
    }
    my ( $board, $kind, $parent ) = BoardOf($id);
    return '' if ( !$board );
    if ( $kind eq 'post' ) {
        $h .= "<li class='inactivetab'>" . &ScriptLinkClass( "action=reply&id=$id", T('Reply'), 'icon-comments', T('Reply') ) . "</li>"
          if ( BoardCanReply($id) );
    }
    $h .= "<li class='inactivetab'>" . &ScriptLinkClass( $kind eq 'post' ? $board : $parent,
        $kind eq 'post' ? T('Back to board') : T('Back to thread'), 'icon-undo' ) . "</li>";
    return $h;
}

# ----------------------------------------------------------------
# Actions
# ----------------------------------------------------------------

sub _BoardIsPost { return ( ( $ENV{REQUEST_METHOD} // '' ) eq 'POST' ) ? 1 : 0; }

sub _BoardPage {
    my ( $title, $body ) = @_;
    print &GetHeader( '', $title, '' );
    print "<div class='wikitext'>$body</div>";
    print &GetCommonFooter();
}

sub _BoardFail { PrintMsg( $_[0], T('Error'), 1 ); }

sub _BoardCheckCaptcha {
    return if ( !$UseCaptcha || &UserPermission() >= 50 );
    _BoardFail( T('Wrong CAPTCHA Answer') )
      if ( !VerifyCaptcha( &GetParam( 'captchaans', '' ), &GetParam( 'captchaopt', '' ) ) );
}

sub _BoardBody {
    my $t = &GetParam( 'text', '' );
    $t = &RemoveFS($t);
    $t =~ s/\r\n?/\n/g;
    $t =~ s/\A\s*<!--\s*post\b.*?-->\s*//s;    # headers come from the form fields only
    _BoardFail( T('The text is empty.') ) if ( $t !~ /\S/ );
    _BoardFail( T('The text is too long.') ) if ( length($t) > $BoardMaxText );
    return $t;
}

sub _BoardRedirect {
    my ($target) = @_;
    print &GetRedirectPage( $target, $target, 1 );
}

# action=newpost&id=Board
sub DoBoardNewPost {
    my ($board) = @_;
    my $cfg = BoardConfig($board);
    _BoardFail( Ts( '%s is not a board.', &QuoteHtml($board) ) ) if ( !$cfg );
    _BoardFail( T('You are not allowed to post here.') ) if ( !BoardCanPost($board) );
    if ( !_BoardIsPost() ) {
        _BoardPage( Ts( 'New post in %s', $board ),
            _BoardPostForm( action => 'newpost', id => $board, withtitle => 1, moderate => BoardIsModerator(), submit => T('Post') ) );
        return;
    }
    CSRFCheckOrDie();
    _BoardCheckCaptcha();
    my $title = _BoardCleanTitle( &RemoveFS( &GetParam( 'title', '' ) ) );
    _BoardFail( T('Please give the post a title.') ) if ( $title eq '' );
    my $tags = &RemoveFS( &GetParam( 'tags', '' ) );
    my $body = _BoardBody();
    my %m    = ( title => $title, tags => join( ', ', grep { $_ ne '' } split( /,/, _BoardNormTags($tags) ) ) );
    if ( BoardIsModerator() ) { $m{sticky} = &GetParam( 'sticky', 0 ) ? 1 : 0; $m{closed} = &GetParam( 'closed', 0 ) ? 1 : 0; }
    my ($id) = BoardAllocateId( $board, 'post', $board, $title );
    _BoardFail( T('Could not create the post, please try again.') ) if ( !$id );
    my $ok = eval { SaveBoardPage( $id, BuildPostHeader( \%m ) . $body, Ts( 'New post: %s', $title ) ); 1 };
    if ( !$ok ) {
        my $err = $@;
        BoardForget($id) if ( !&PageExists($id) );
        die($err);
    }
    _BoardRedirect($id);
}

# action=reply&id=Board/0042
sub DoBoardReply {
    my ($thread) = @_;
    my ( $board, $kind ) = BoardOf($thread);
    _BoardFail( T('Replies can only be posted to a thread.') ) if ( !$board || $kind ne 'post' || !&PageExists($thread) );
    _BoardFail( T('You are not allowed to reply here.') ) if ( !BoardCanReply($thread) );
    my $title = _BoardShowTitle( $thread, BoardTitle($thread) );
    if ( !_BoardIsPost() ) {
        _BoardPage( Ts( 'Reply to %s', $title ), _BoardPostForm( action => 'reply', id => $thread, submit => T('Reply') ) );
        return;
    }
    CSRFCheckOrDie();
    _BoardCheckCaptcha();
    my $body = _BoardBody();
    my ( $id, $seq ) = BoardAllocateId( $board, 'reply', $thread, '' );
    _BoardFail( T('Could not save the reply, please try again.') ) if ( !$id );
    my $ok = eval { SaveBoardPage( $id, $body, Ts( 'Reply to %s', $title ) ); 1 };
    if ( !$ok ) {
        my $err = $@;
        BoardForget($id) if ( !&PageExists($id) );
        die($err);
    }
    my $m     = BoardMeta($thread);
    my $per   = BoardConfig($board)->{perpage};
    my $pages = int( ( ( $m ? $m->{nreplies} : 1 ) + $per - 1 ) / $per ) || 1;
    _BoardRedirect( "action=browse&id=$thread&bpage=$pages" . sprintf( '#r%04d', $seq ) );
}

# action=postedit&id=Board/0042 (title/tags/text form for posts and replies)
sub DoBoardPostEdit {
    my ($id) = @_;
    my ( $board, $kind ) = BoardOf($id);
    _BoardFail( T('This page is not a board post.') ) if ( !$board || !&PageExists($id) );
    _BoardFail( T('You are not allowed to edit this post.') ) if ( !_BoardCanRead($id) || !&UserCanEdit( $id, 1 ) );
    &OpenDefaultPage($id);
    my $cur = $Pages{$id}->{'text'}->{'text'};
    my $rev = $Pages{$id}->{'section'}->{'revision'};
    my ( $old, $oldbody ) = ParsePostHeader($cur);
    my $idx = BoardMeta($id) || {};
    $old->{sticky} = $idx->{sticky} ? 1 : 0;    # the index, not the text, is authoritative
    $old->{closed} = $idx->{closed} ? 1 : 0;
    my $mod = BoardIsModerator();
    if ( !_BoardIsPost() ) {
        _BoardPage(
            Ts( 'Editing %s', _BoardShowTitle( $id, BoardTitle($id) ) ),
            _BoardPostForm(
                action    => 'postedit', id => $id, baserev => $rev, withtitle => ( $kind eq 'post' ),
                moderate  => ( $mod && $kind eq 'post' ),
                title     => $old->{title}, tags => $old->{tags}, sticky => $old->{sticky}, closed => $old->{closed},
                text      => $oldbody, submit => T('Save')
            )
        );
        return;
    }
    CSRFCheckOrDie();
    _BoardCheckCaptcha();
    if ( &GetParam( 'baserev', '' ) ne $rev ) {
        _BoardFail( T('This post was changed by someone else while you were editing. Go back, copy your text, and edit again.') );
    }
    my $body = _BoardBody();
    my %m    = %$old;
    if ( $kind eq 'post' ) {
        $m{title} = _BoardCleanTitle( &RemoveFS( &GetParam( 'title', '' ) ) );
        _BoardFail( T('Please give the post a title.') ) if ( $m{title} eq '' );
        $m{tags} = join( ', ', grep { $_ ne '' } split( /,/, _BoardNormTags( &RemoveFS( &GetParam( 'tags', '' ) ) ) ) );
        if ($mod) { $m{sticky} = &GetParam( 'sticky', 0 ) ? 1 : 0; $m{closed} = &GetParam( 'closed', 0 ) ? 1 : 0; }
    }
    my $new = BuildPostHeader( \%m ) . $body;
    if ( $new ne $cur && "$new\n" ne $cur ) {
        SaveBoardPage( $id, $new, &GetParam( 'summary', '' ) ne '' ? &GetParam( 'summary', '' ) : T('Edited') );
    }
    if ( $kind eq 'post' ) {
        _BoardRedirect($id);
    } else {
        my $thread = ( BoardOf($id) )[2];
        my $seq    = ( BoardMeta($id) || {} )->{seq} || 0;
        my $pg     = _BoardReplyPage( $thread, $seq, BoardConfig($board)->{perpage} );
        _BoardRedirect( "action=browse&id=$thread&bpage=$pg" . sprintf( '#r%04d', $seq ) );
    }
}

# action=boardmod&id=X&op=sticky|unsticky|close|open|delete (editors, POST)
sub DoBoardModerate {
    my ($id) = @_;
    _BoardFail( T('This needs a form submission.') ) if ( !_BoardIsPost() );
    CSRFCheckOrDie();
    _BoardFail( T('Only editors and administrators can do this.') ) if ( !BoardIsModerator() || _BoardBlocked() );
    my ( $board, $kind, $parent ) = BoardOf($id);
    _BoardFail( T('This page is not a board post.') ) if ( !$board || !&PageExists($id) );
    _BoardFail( T('This page is locked.') ) if ( &IsPageLocked($id) && !&UserIsAdmin() );
    _BoardFail( T('You are not allowed to edit this post.') ) if ( !_BoardCanRead($id) );
    my $op = &GetParam( 'op', '' );
    if ( $op eq 'delete' ) {
        my @del = ($id);
        if ( $kind eq 'post' ) {
            my $r = $dbh->selectcol_arrayref( "SELECT id FROM " . _BoardTable() . " WHERE parent=? AND kind='reply'", undef, $id );
            unshift @del, @$r;
        }
        foreach my $p (@del) {
            &DeletePage( $p, 0, 1 ) if ( &PageExists($p) );
            BoardForget($p);
        }
        _BoardRedirect( $kind eq 'post' ? $board : $parent );
        return;
    }
    my %flag = ( sticky => [ 'sticky', 1 ], unsticky => [ 'sticky', 0 ], close => [ 'closed', 1 ], open => [ 'closed', 0 ] );
    _BoardFail( T('Unknown operation.') ) if ( !$flag{$op} || $kind ne 'post' );
    &OpenDefaultPage($id);
    my $cur = $Pages{$id}->{'text'}->{'text'};
    my ( $m, $body ) = ParsePostHeader($cur);
    my $idx = BoardMeta($id) || {};
    $m->{sticky} = $idx->{sticky} ? 1 : 0;
    $m->{closed} = $idx->{closed} ? 1 : 0;
    my ( $k, $v ) = @{ $flag{$op} };
    if ( $m->{$k} != $v ) {
        $m->{$k} = $v;
        SaveBoardPage( $id, BuildPostHeader($m) . $body, $op );
    }
    _BoardRedirect($id);
}

# action=boardrebuild&id=Board (admins, POST)
sub DoBoardRebuild {
    my ($board) = @_;
    _BoardFail( T('This needs a form submission.') ) if ( !_BoardIsPost() );
    CSRFCheckOrDie();
    _BoardFail( T('Only administrators can do this.') ) if ( !&UserIsAdmin() );
    _BoardFail( Ts( '%s is not a board.', &QuoteHtml($board) ) ) if ( !BoardConfig($board) );
    my ( $np, $nr ) = BoardRebuild($board);
    _BoardPage( T('Board index rebuilt'),
        Tss( 'Indexed %1 posts and %2 replies.', $np, $nr ) . '<p>' . &ScriptLink( $board, T('Back to board') ) . '</p>' );
}

1;
