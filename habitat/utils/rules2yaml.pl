#!/usr/bin/env perl
#
# rules2yaml.pl - convert line-format rule pages (.v0/.v1/.e0/.e1) to
# the YAML rule format, and prove each conversion.
#
# A converted page is kept only if the engine gives exactly the same
# result for the old and the new rules on every sample text: every page
# of the wiki (latest revision), with and without a final newline, plus
# a few fixed strings. Anything else is reported and left alone.
#
#   rules2yaml.pl FILE [SAMPLE ...]
#       convert one rule text; print YAML on stdout, report on stderr
#   rules2yaml.pl --dsn DSN [--user U] [--table page] --out DIR
#   rules2yaml.pl --config DATADIR/config --out DIR
#       read every rule page of a wiki (read-only) and write, per page,
#       DIR/<id>.yaml (converted) or DIR/<id>.skip (why not), plus
#       DIR/report.txt. With --config the database settings, password
#       included, are taken from the site config and never printed.
#
# Nothing is written to the wiki. Line-format rules that cannot be
# expressed exactly (a "\1" or "$1" in the replacement, which the line
# format inserts literally; a continuation inside the pattern) make the
# page a .skip. Set R2Y_DEBUG=1 to print each candidate YAML on stderr.

use strict;
use warnings;
use FindBin qw($Bin);
use Getopt::Long;

my %opt = ( table => '' );
GetOptions( \%opt, 'dsn=s', 'user=s', 'pass=s', 'table=s', 'config=s', 'out=s' ) or die "bad options\n";

# Load the engine (as the tests do) for ApplyRegExpRules / ApplyYamlRules.
chdir("$Bin/..") or die "cannot chdir to $Bin/..: $!\n";
unshift @INC, "$Bin/../lib";
$ENV{NO_FATALS_TO_BROWSER} = 1;
{
    local $_ = 'nocgi';
    require "./index.cgi";
}
no warnings 'once';
&HabitatEngine::InitLinkPatterns();    # sets $FS: the line format joins continued lines with it

my $FSA = "\x{1e}A";    # stands for a joined line, as in ApplyRegExpRules

# ----------------------------------------------------------------
# Line format -> list of steps. Mirrors ApplyRegExpRules.
# ----------------------------------------------------------------
sub parse_lines {
    my ($rules) = @_;
    my ( @steps, @why );
    ( my $r = $rules ) =~ s/\\\s*\r*\n/$FSA/g;
    foreach my $line ( split( /\n/, $r ) ) {
        $line =~ s/[\r\n]$//;
        next if ( $line eq '' );
        if ( $line =~ /^GREP\s+(.*)/ ) {
            push( @why, "GREP pattern spans lines" ) if ( $1 =~ /$FSA/ );
            push( @steps, { grep => $1 } );
            next;
        }
        if ( $line =~ /^(HEAD|TAIL)\s+(.*)/ ) {
            my ( $k, $n ) = ( lc($1), $2 );
            if ( $n !~ /^\d+$/ ) { push( @why, "$1 $n is not a number" ); next; }
            push( @steps, { $k => $n } );
            next;
        }
        if ( $line =~ /(.*[^\\])\/(.*[^\\])(\/([mgi])){0,1}$/ ) {
            my ( $from, $to ) = ( $1, $2 );
            $to =~ s/\\\//\//g;
            $to =~ s/\\\$/\$/g;
            $to =~ s/\\N/\n/g;
            $to =~ s/$FSA/\n/g;
            if ( $from =~ /$FSA/ ) { push( @why, "pattern spans lines: $from" ); next; }
            if ( $from eq '^' ) { push( @steps, { prepend => $to } ); next; }
            if ( $from eq '$' ) { push( @steps, { append_eol => $to } ); next; }
            if ( $to =~ /\\[0-9]|\$[0-9]/ ) {
                push( @why, "replacement has \\N or \$N, inserted literally by the line format: $line" );
                next;
            }
            push( @steps, { from => $from, to => $to } );
            next;
        }
        ( my $c = $line ) =~ s/$FSA/\n/g;
        push( @steps, { comment => $c } );
    }
    return ( \@steps, \@why );
}

# ----------------------------------------------------------------
# Steps -> YAML text
# ----------------------------------------------------------------
sub yscalar {
    my ($s) = @_;
    if ( $s !~ /[\n\r]/ ) {
        ( my $q = $s ) =~ s/'/''/g;
        return "'$q'";
    }
    my $trail = 0;
    $trail++ while ( $s =~ s/\n\z// );
    my $body = join( "\n", map { $_ eq '' ? '' : "    $_" } split( /\n/, $s, -1 ) );
    return ( $trail ? '|2+' : '|2-' ) . "\n" . $body . ( "\n" x $trail );
}

sub to_yaml {
    my ( $steps, $exact_eol ) = @_;
    my $y = "# Rules in YAML (see Habitat/NewSyntax), converted from the line format.\n";
    foreach my $s (@$steps) {
        if ( exists $s->{comment} ) {
            $y .= join( '', map { "# $_\n" } split( /\n/, $s->{comment}, -1 ) );
            next;
        }
        my @kv;
        if    ( exists $s->{from} )    { @kv = ( from => $s->{from}, to => $s->{to} ); }
        elsif ( exists $s->{prepend} ) { @kv = ( prepend => $s->{prepend} ); }
        elsif ( exists $s->{append_eol} ) {
            @kv = $exact_eol ? ( from => '$', to => $s->{append_eol}, opt => '' ) : ( append => $s->{append_eol} );
        } else {
            my ($k) = keys %$s;
            @kv = ( $k => $s->{$k} );
        }
        my $lead = '- ';
        while (@kv) {
            my ( $k, $v ) = splice( @kv, 0, 2 );
            my $sv = ( $k =~ /^(head|tail)$/ ) ? $v : yscalar($v);
            $y .= "$lead$k: $sv" . ( $sv =~ /\n\z/ ? '' : "\n" );
            $lead = '  ';
        }
    }
    return $y;
}

# ----------------------------------------------------------------
# Convert and prove. Returns (yaml or undef, @messages).
# ----------------------------------------------------------------
my @FIXED = ( '', 'x', "x\n", "one\ntwo\nthree", "one\ntwo\nthree\n", "a/b \\1 \$1 ^ \$ .* <p>&amp;" );

sub samples {
    my %seen;
    my @s;
    foreach my $t ( @FIXED, @_ ) {
        next if ( !defined($t) );
        ( my $bare = $t ) =~ s/\n+\z//;
        foreach my $v ( $t, $bare, "$bare\n" ) { push( @s, $v ) if ( !$seen{$v}++ ); }
    }
    return @s;
}

sub convert {
    my ( $rules, @sample ) = @_;
    my ( $steps, $why ) = parse_lines($rules);
    return ( undef, @$why ) if (@$why);
    return ( undef, 'no rules in it' ) if ( !grep { !exists $_->{comment} } @$steps );
    my @s = samples(@sample);
    my $fail;
    foreach my $exact ( 0, 1 ) {
        last if ( $exact && !grep { exists $_->{append_eol} } @$steps );
        my $yaml = to_yaml( $steps, $exact );
        print STDERR "---- candidate:\n$yaml" if ( $ENV{R2Y_DEBUG} );
        return ( undef, 'not recognised as YAML' ) if ( !HabitatEngine::IsYamlRules($yaml) );
        my $bad = 0;
        my $first;
        foreach my $t (@s) {
            my $old = HabitatEngine::ApplyRegExpRules( $rules, $t, 0 );
            my $new = HabitatEngine::ApplyYamlRules( $yaml, $t );
            next if ( $old eq $new );
            $bad++;
            $first //= "input " . dq($t) . "\n    line format: " . dq($old) . "\n    YAML:        " . dq($new);
        }
        my $note = $exact ? 'final "$/" rules kept as from: \'$\' (insert before a final newline)' : ();
        return ( $yaml, sprintf( 'identical on %d samples', scalar @s ), $note || () ) if ( !$bad );
        $fail = "differs on $bad of " . scalar(@s) . " samples; first: $first";
    }
    return ( undef, $fail );
}

sub dq {
    my ($s) = @_;
    $s = substr( $s, 0, 117 ) . '...' if ( length($s) > 120 );
    $s =~ s/\\/\\\\/g;
    $s =~ s/\n/\\n/g;
    $s =~ s/\r/\\r/g;
    return "\"$s\"";
}

sub slurp { local ( @ARGV, $/ ) = @_; return scalar <>; }

# ----------------------------------------------------------------
# One file
# ----------------------------------------------------------------
if ( !$opt{dsn} && !$opt{config} ) {
    die "usage: $0 FILE [SAMPLE ...] | --dsn DSN --out DIR | --config CONFIG --out DIR\n" if ( !@ARGV );
    my ( $yaml, @msg ) = convert( slurp( shift @ARGV ), map { slurp($_) } @ARGV );
    print STDERR "$_\n" for @msg;
    print $yaml if ( defined $yaml );
    exit( defined $yaml ? 0 : 2 );
}

# ----------------------------------------------------------------
# A whole wiki, read-only
# ----------------------------------------------------------------
die "--out DIR is required\n" if ( !$opt{out} );
my ( $dsn, $user, $pass, $table ) = ( $opt{dsn}, $opt{user} // '', $opt{pass} // '', $opt{table} );
if ( $opt{config} ) {
    package HabitatEngine;
    our ( $DataDir, $DBName, $DBUser, $DBPass, $PageDir, $DBTablePrefix );
    ( $DataDir = $opt{config} ) =~ s{/[^/]+$}{};
    $PageDir = "$DataDir/page";
    do $opt{config} or die "cannot read $opt{config}: " . ( $@ || $! ) . "\n";
    &InitLinkPatterns();
    ( $dsn, $user, $pass ) = ( $DBName, $DBUser // '', $DBPass // '' );
    $table ||= &DBTable($PageDir);
}
$table ||= 'page';
die "unsafe table name\n" if ( $table !~ /^\w+$/ );

require DBI;
my $dbh = DBI->connect( $dsn, $user, $pass, { RaiseError => 1, PrintError => 0, AutoCommit => 1 } );
$dbh->do('SET SESSION TRANSACTION READ ONLY') if ( $dsn =~ /^dbi:(mysql|MariaDB|Pg)/i );

my ( %text, %rev );
my $sth = $dbh->prepare("SELECT id, revision, text FROM $table");
$sth->execute;
while ( my ( $id, $r, $t ) = $sth->fetchrow_array ) {
    next if ( defined $rev{$id} && $rev{$id} >= ( $r // 0 ) );
    $rev{$id} = $r // 0;
    $t //= '';
    ($t) = &HabitatEngine::PatchPage($t) if ( $t =~ /$HabitatEngine::FS4/ );
    $text{$id} = $t;
}
$dbh->disconnect;

mkdir( $opt{out} );
my @rulepages = sort grep { m{(^|/)\.[ve][01]$} } keys %text;
my @pages     = map { $text{$_} } sort grep { !m{(^|/)\.[^/]+$} } keys %text;
open( my $rep, '>', "$opt{out}/report.txt" ) or die "$opt{out}/report.txt: $!\n";
printf $rep "%d pages, %d rule pages, table %s\n\n", scalar(@pages), scalar(@rulepages), $table;
my ( $ok, $skip ) = ( 0, 0 );
foreach my $id (@rulepages) {
    my ( $yaml, @msg ) = convert( $text{$id}, @pages );
    ( my $f = $id ) =~ s{/}{%2F}g;
    open( my $o, '>', "$opt{out}/$f." . ( defined $yaml ? 'yaml' : 'skip' ) ) or die "$f: $!\n";
    print $o defined $yaml ? $yaml : join( "\n", @msg, '', '--- original:', $text{$id} );
    close $o;
    defined $yaml ? $ok++ : $skip++;
    print $rep ( defined $yaml ? 'OK   ' : 'SKIP ' ), "$id: ", join( '; ', @msg ), "\n";
}
print $rep "\n$ok converted, $skip left in the line format\n";
close $rep;
print "$ok converted, $skip left in the line format; see $opt{out}/report.txt\n";
