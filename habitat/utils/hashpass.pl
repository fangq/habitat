#!/usr/bin/env perl
#
# hashpass.pl - keep only bcrypt hashes of $AdminPass / $EditPass in a
# site config, and change those tokens.
#
#   hashpass.pl DATADIR/config [--dry-run]
#       Replace every plain token in $AdminPass and $EditPass by
#       "{bcrypt}<hash>". Users who hold one of these tokens keep their
#       rights: their stored value becomes the token's role code.
#
#   hashpass.pl DATADIR/config --set admin|edit [--set ...]
#               [--random FILE] [--grant USER ...] [--dry-run]
#       Replace all tokens of $AdminPass (admin) or $EditPass (edit) by
#       one new token. It is asked for twice (not shown), or with
#       --random generated (32 letters and digits) and appended to FILE,
#       which is created readable only by you. Everybody who held an old
#       token of that variable loses it; --grant USER gives USER the new
#       token (the admin one when admin is set, else the editor one).
#
# The config is rewritten in place (same permissions, atomic rename) only
# after the new file has been read back and every hash checked; the user
# table is changed in one transaction, committed after the rename. No
# token, hash or database password is printed, and no copy of the old
# config is kept.
#
# The engine must understand hashed tokens (IsHashedToken in index.cgi):
# update the site's index.cgi first.

use strict;
use warnings;
use FindBin qw($Bin);
use Getopt::Long;
use Cwd qw(abs_path getcwd);
use Fcntl qw(O_WRONLY O_CREAT O_APPEND);

my ( @set, @grant, $random, $dry );
GetOptions( 'set=s' => \@set, 'grant=s' => \@grant, 'random=s' => \$random, 'dry-run' => \$dry )
  or die "bad options\n";
my $config = shift @ARGV;
die "usage: $0 DATADIR/config [--set admin|edit]... [--random FILE] [--grant USER]... [--dry-run]\n"
  if ( !defined($config) || @ARGV );
die "$config: not a file\n" if ( !-f $config );
$config = abs_path($config);
my %set = map { ( lc($_) => 1 ) } @set;
foreach ( keys %set ) { die "--set takes admin or edit\n" if ( !/^(admin|edit)$/ ); }
die "--grant needs --set\n"   if ( @grant  && !%set );
die "--random needs --set\n"  if ( $random && !%set );
$random = getcwd() . "/$random" if ( defined($random) && $random !~ m{^/} );

# Load the engine (as the tests do) for Hmac, the hashing and DBTable.
chdir("$Bin/..") or die "cannot chdir to $Bin/..: $!\n";
unshift @INC, "$Bin/../lib";
$ENV{NO_FATALS_TO_BROWSER} = 1;
{
    local $_ = 'nocgi';
    require "./index.cgi";
}
no warnings 'once';
die "this engine does not support hashed tokens\n" if ( !defined &HabitatEngine::IsHashedToken );

# The values Perl gives the config (a double-quoted "a@b" is "a"), and the
# database settings.
sub ReadConfig {
    my ($file) = @_;
    package HabitatEngine;
    our ( $DataDir, $AdminPass, $EditPass, $SecretFile, $UserDir, $DBName, $DBUser, $DBPass );
    ( $DataDir = $config ) =~ s{/[^/]+$}{};
    $SecretFile = "$DataDir/secret";
    $UserDir    = "$DataDir/users";
    ( $AdminPass, $EditPass ) = ( '', '' );
    local $SIG{__WARN__} = sub { };
    do $file or die "cannot read the config: " . ( $@ || $! ) . "\n";
    undef $HabitatEngine::SiteSecret;    # the key of this site, not of an earlier read
    return ( $AdminPass // '', $EditPass // '' );
}

my %var = ( admin => 'AdminPass', edit => 'EditPass' );
my %old;
@old{qw(admin edit)} = ReadConfig($config);
die "the secret file $HabitatEngine::SecretFile is missing: the site has to have run once\n"
  if ( !-s $HabitatEngine::SecretFile );

my $text = do { local ( @ARGV, $/ ) = ($config); <> };
foreach my $v ( values %var ) {
    if ( $text =~ /\$\Q$v\E\b/ && $text !~ /^[ \t]*\$\Q$v\E[ \t]*=/m ) {
        die "\$$v is used in the config but never assigned on a line of its own\n";
    }
}

# ---- new values ----
my ( %new, %fresh, %plainOf );    # %fresh: role => new hashed token
my @secrets;
foreach my $r (qw(admin edit)) {
    if ( $set{$r} ) {
        my $pw = defined($random) ? RandomToken() : AskToken( $var{$r} );
        die "the token must be 12 to 50 characters without spaces\n"
          if ( length($pw) < 12 || length($pw) > 50 || $pw =~ /\s/ );
        $new{$r} = '{bcrypt}' . HabitatEngine::HashPassword($pw);
        $fresh{$r} = $new{$r};
        push @secrets, [ $var{$r}, $pw ];
    } else {
        my @t;
        foreach my $tok ( split( /\s+/, $old{$r} ) ) {
            next if ( $tok eq '' );
            if ( HabitatEngine::IsHashedToken($tok) ) { push @t, $tok; next; }
            my $h = '{bcrypt}' . HabitatEngine::HashPassword($tok);
            $plainOf{$h} = $tok;
            push @t, $h;
        }
        $new{$r} = join( ' ', @t );
    }
}

# ---- user table: who keeps which token ----
require DBI;
my $dbh = DBI->connect( $HabitatEngine::DBName, $HabitatEngine::DBUser // '', $HabitatEngine::DBPass // '',
    { RaiseError => 1, PrintError => 0, AutoCommit => 1 } );
my $users = HabitatEngine::DBTable($HabitatEngine::UserDir);
die "unsafe table name\n" if ( $users !~ /^\w+$/ );
my %update;                              # id => new stored value
my %count = ( kept_admin => 0, kept_edit => 0, granted => 0, lost => 0 );
my $rows = $dbh->selectall_arrayref("SELECT id, name, groupid FROM $users WHERE groupid IS NOT NULL AND groupid <> ''");
foreach my $row (@$rows) {
    my ( $id, $name, $stored ) = @$row;
    my $had = 0;
    foreach my $r (qw(admin edit)) {
        foreach my $tok ( split( /\s+/, $old{$r} ) ) {
            next if ( $tok eq '' || !HabitatEngine::TokenGrants( $tok, $stored ) );
            $had = 1;
            last;
        }
    }
    next if ( !$had );
  ROLE: foreach my $r (qw(admin edit)) {
        foreach my $h ( split( /\s+/, $new{$r} ) ) {
            my $keeps =
              exists( $plainOf{$h} )
              ? HabitatEngine::TokenGrants( $plainOf{$h}, $stored )    # converted token
              : ( $stored =~ /^\{role\}/ && HabitatEngine::TokenGrants( $h, $stored ) );    # already hashed
            next if ( !$keeps );
            $update{$id} = HabitatEngine::RoleCode($h) if ( exists( $plainOf{$h} ) );
            $count{"kept_$r"}++;
            last ROLE;
        }
        $count{lost}++ if ( $r eq 'edit' );
    }
}
foreach my $name (@grant) {
    my $ids = $dbh->selectcol_arrayref( "SELECT id FROM $users WHERE name=?", undef, $name );
    die "--grant: no user named $name\n" if ( @$ids != 1 );
    my $tok = $fresh{admin} // $fresh{edit};
    $update{ $ids->[0] } = HabitatEngine::RoleCode($tok);
    $count{granted}++;
}

# ---- write the config ----
my $newtext = $text;
foreach my $r (qw(admin edit)) {
    next if ( $new{$r} eq $old{$r} );
    my $v = $var{$r};
    my $n = 0;
    $newtext =~ s{^([ \t]*\$\Q$v\E[ \t]*=[ \t]*)("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')([ \t]*;)}{
        $n++; $1 . "'$new{$r}'" . $3
    }gme;
    die "\$$v is not assigned a quoted string; change it by hand\n" if ( !$n );
}

my @kept = map { "$_ token(s): " . scalar( () = split( /\s+/, $new{$_} ) ) } grep { $new{$_} ne '' } qw(admin edit);
printf "%s\n",   $config;
printf "  %s %s\n", ( $set{$_} ? "new" : "hashed" ), "\$$var{$_}" foreach grep { $new{$_} ne $old{$_} } qw(admin edit);
print "  nothing to change in the config\n" if ( $newtext eq $text );
printf "  users: %d keep admin, %d keep editor, %d lose their token, %d granted\n",
  @count{qw(kept_admin kept_edit lost granted)};

if ($dry) {
    print "  dry run: nothing written\n";
    exit 0;
}
exit 0 if ( $newtext eq $text && !%update );

my $tmp = "$config.hashpass.$$";
{
    my @st = stat($config);
    open( my $fh, '>', $tmp ) or die "cannot write $tmp: $!\n";
    chmod( $st[2] & 07777, $tmp );
    print $fh $newtext;
    close($fh) or die "cannot write $tmp: $!\n";
}
my %back;
eval {
    @back{qw(admin edit)} = ReadConfig($tmp);
    foreach my $r (qw(admin edit)) {
        die "\$$var{$r} reads back differently\n" if ( $back{$r} ne $new{$r} );
    }
    foreach my $h ( keys %plainOf ) {
        die "a hash does not match its token\n" if ( !HabitatEngine::TokenMatches( $h, $plainOf{$h} ) );
    }
    foreach my $s (@secrets) {
        my $r = $s->[0] eq 'AdminPass' ? 'admin' : 'edit';
        die "the new hash does not match the new token\n" if ( !HabitatEngine::TokenMatches( $new{$r}, $s->[1] ) );
    }
    1;
} or do { unlink($tmp); die "config not changed: $@"; };

# Keep the new token before anything is replaced.
if (@secrets) {
    if ( defined($random) ) {
        sysopen( my $fh, $random, O_WRONLY | O_CREAT | O_APPEND, 0600 ) or do { unlink($tmp); die "cannot write $random: $!\n" };
        chmod( 0600, $random );
        print $fh "$config \$$_->[0]: $_->[1]\n" foreach (@secrets);
        close($fh);
        print "  new token(s) appended to $random\n";
    }
}

$dbh->begin_work;
my $sth = $dbh->prepare("UPDATE $users SET groupid=? WHERE id=?");
$sth->execute( $update{$_}, $_ ) foreach ( sort keys %update );
if ( !rename( $tmp, $config ) ) {
    my $err = $!;
    $dbh->rollback;
    unlink($tmp);
    die "cannot replace the config ($err): nothing changed\n";
}
if ( !eval { $dbh->commit; 1 } ) {
    my $err = $@;
    my $fh;
    open( $fh, '>', $config ) and print $fh $text and close($fh);
    die "database commit failed, config put back: $err";
}
printf "  done: config rewritten, %d user record(s) updated\n", scalar( keys %update );

sub RandomToken {
    my @c = ( 'A' .. 'Z', 'a' .. 'z', '0' .. '9' );
    my $s = '';
    while ( length($s) < 32 ) {
        foreach my $b ( unpack( 'C*', Habitat::Auth::RandomBytes(64) ) ) {
            $s .= $c[ $b % 62 ] if ( $b < 248 );    # 248 = 4*62: no bias
            last if ( length($s) == 32 );
        }
    }
    return $s;
}

sub AskToken {
    my ($v) = @_;
    my $tty;
    open( $tty, '+<', '/dev/tty' ) or die "no terminal to ask for \$$v; use --random FILE\n";
    my $echo = system('stty -echo </dev/tty 2>/dev/null') == 0;
    print $tty "new \$$v: ";
    chomp( my $a = <$tty> // '' );
    print $tty "\nagain: ";
    chomp( my $b = <$tty> // '' );
    print $tty "\n";
    system('stty echo </dev/tty 2>/dev/null') if ($echo);
    die "the two entries differ\n" if ( $a ne $b );
    return $a;
}
