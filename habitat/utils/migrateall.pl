#!/usr/bin/env perl
#
# Habitat end-to-end legacy-data migrator.
#
#   perl utils/migrateall.pl <path_to_old_config> <path_to_old_db>
#
# Optional:
#   --dest DSN         destination DBI URL (default: <old_db>.new SQLite)
#   --dest-user U      destination DB user
#   --dest-pass P      destination DB password
#   --dry-run          parse + plan only; write nothing
#   --force            overwrite existing <old_config>.new / dest DB
#
# What this script does, in order:
#
#   1. CONFIG. Reads <path_to_old_config>, writes a modernized copy at
#      <path_to_old_config>.new with:
#        - retired keys dropped     ($WikiCipher, $CaptchaKey,
#                                    $NotifyDefault — see %RETIRED below)
#        - $UserDir value updated   ($DataDir/user → $DataDir/users)
#        - everything else passed through byte-for-byte so heredocs,
#          comments, and ordering are preserved
#
#   2. DATABASE. Hands off to utils/migrate.pl, which already knows how
#      to fold the legacy per-revision page rows into the new
#      `page` + `page_revisions` shape and to convert the FS-joined
#      `user.stylesheet` blob into the JSON `users.prefs` column.
#      Password hashes pass through unchanged — VerifyPassword still
#      accepts the legacy crypt(3) form and UpgradePasswordHashDB
#      transparently rotates them to bcrypt on first successful login.
#
#   3. RULE PAGES. For every page in the new DB whose id ends with
#      .v0 / .v1 / .e0 / .e1 (the four legacy ApplyRegExpRules
#      namespaces), the line-oriented `from/to/opt` body is parsed
#      and rewritten as a JSON array — the format EvalLocalRules
#      consumes. The old line format still works at runtime; the
#      JSON rewrite is so future edits get the structured, validated
#      form.
#
# Outputs after a successful run:
#   <path_to_old_config>.new
#   <path_to_old_db>.new        (unless --dest specified an alt DSN)
#   stderr trail of every action taken; summary at the end.

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/../lib";
use Getopt::Long;
use File::Basename ();
use Habitat::Store ();
use DBI;
use JSON::PP;

# Keys that the modernization stages explicitly retired. Stage 1
# removed the DES captcha key, Stage 5 dropped the legacy notify
# default. If the legacy config sets them, migrateall drops the
# line so the new wiki doesn't trip on an unused global.
my %RETIRED = map { $_ => 1 } qw(
  WikiCipher
  CaptchaKey
  NotifyDefault
);

# Per-key value transforms. Each entry is a coderef that receives
# the raw RHS (quoted string, heredoc, numeric, anything — exactly
# what the perl source contained) and returns the replacement.
# Returning undef means "drop the line entirely."
my %VALUE_TRANSFORM = (

    # Stage 5 renamed the user table from "user" to "users" because
    # `user` is reserved in Postgres. The DataDir-relative path in
    # legacy configs must be updated to match.
    UserDir => sub {
        my ($rhs) = @_;
        $rhs =~ s{(\$DataDir/)user(["'])}{$1users$2}g;
        return $rhs;
    },
);

my ( $dest_dsn, $dest_user, $dest_pass, $dry_run, $force, $help );
$dest_user = '';
$dest_pass = '';

GetOptions(
    "dest=s"      => \$dest_dsn,
    "dest-user=s" => \$dest_user,
    "dest-pass=s" => \$dest_pass,
    "dry-run"     => \$dry_run,
    "force"       => \$force,
    "help|h"      => \$help,
) or usage(2);

usage(0) if $help;
usage(2) if ( @ARGV != 2 );

my ( $old_config, $old_db ) = @ARGV;

sub usage {
    my ($exit) = @_;
    print STDERR <<"USAGE";
usage: $0 <path_to_old_config> <path_to_old_db> [options]

options:
  --dest DSN         destination DBI URL
                     (default: dbi:SQLite:dbname=<old_db>.new)
  --dest-user U      destination DB user
  --dest-pass P      destination DB password
  --dry-run          parse + plan only; write nothing
  --force            overwrite <old_config>.new and the destination DB
                     if they already exist

example:
  perl utils/migrateall.pl \\
      example/neurojson/habitatdb/config \\
      example/neurojson/habitatdb.db \\
      --dest 'dbi:Pg:dbname=habitat;host=localhost' \\
      --dest-user habitat
USAGE
    exit $exit;
}

sub log_msg { print STDERR "[migrateall] @_\n" }

die "old config not found: $old_config\n" if ( !-r $old_config );
die "old db not found: $old_db\n"         if ( !-r $old_db );

my $new_config = "$old_config.new";
$dest_dsn //= "dbi:SQLite:dbname=$old_db.new";
my $dest_is_sqlite_file = ( $dest_dsn =~ /^dbi:SQLite:dbname=(.+)$/i ) ? $1 : undef;

if ( !$force && !$dry_run ) {
    die "refusing to overwrite existing $new_config (pass --force)\n"
      if ( -e $new_config );
    die "refusing to overwrite existing $dest_is_sqlite_file (pass --force)\n"
      if ( defined $dest_is_sqlite_file && -e $dest_is_sqlite_file );
}

# ----------------------------------------------------------------
# Step 1: config migration
# ----------------------------------------------------------------
log_msg "step 1/3: rewriting config -> $new_config";
{
    open( my $in, '<', $old_config ) or die "open $old_config: $!\n";
    my @out;
    my ( $dropped, $transformed, $passed ) = ( 0, 0, 0 );

    while ( my $line = <$in> ) {

        # Match `$KeyName = <rest>` where <rest> can be anything: a
        # quoted string with embedded chars, a numeric, an array
        # constructor, a heredoc terminator, etc. We don't try to
        # parse the value — just slice off the `$Name` part and
        # let the perl parser at the wiki side handle the value.
        if ( $line =~ /^\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/s ) {
            my ( $key, $rhs ) = ( $1, $2 );

            if ( $RETIRED{$key} ) {
                log_msg "  drop retired key: \$$key";
                $dropped++;
                next;
            }

            if ( my $tx = $VALUE_TRANSFORM{$key} ) {
                my $new_rhs = $tx->($rhs);
                if ( !defined $new_rhs ) {
                    log_msg "  drop transformed-to-undef: \$$key";
                    $dropped++;
                    next;
                }
                if ( $new_rhs ne $rhs ) {
                    log_msg "  transform \$$key value";
                    $line = "\$$key = $new_rhs";
                    $line .= "\n" if ( $line !~ /\n\z/ );
                    $transformed++;
                } else {
                    $passed++;
                }
            } else {
                $passed++;
            }
        }
        push @out, $line;
    }
    close $in;

    if ( !$dry_run ) {
        open( my $w, '>', $new_config ) or die "open $new_config: $!\n";
        print {$w} @out;
        close $w;
    }
    log_msg "  config summary: $passed passed, $transformed transformed, $dropped dropped"
      . ( $dry_run ? "  (dry-run)" : "" );
}

# ----------------------------------------------------------------
# Step 2: hand off DB copy to utils/migrate.pl
# ----------------------------------------------------------------
log_msg "step 2/3: invoking utils/migrate.pl";
{
    my @cmd = (
        $^X, "$Bin/migrate.pl",
        '--source' => "dbi:SQLite:dbname=$old_db",
        '--dest'   => $dest_dsn,
    );
    push @cmd, '--dest-user' => $dest_user if ( $dest_user ne '' );
    push @cmd, '--dest-pass' => $dest_pass if ( $dest_pass ne '' );
    push @cmd, '--dry-run' if ($dry_run);

    log_msg "  exec: @cmd";
    my $rc = system(@cmd) >> 8;
    die "migrate.pl exited with status $rc\n" if ( $rc != 0 );
}

# ----------------------------------------------------------------
# Step 3: rule-page conversion (in the destination DB)
#
# Pages whose id ends with .v0/.v1/.e0/.e1 carry rewrite rules that
# the wiki applies via ApplyRegExpRules. The line-oriented form
# (`from/to/opt`) still works in the new engine, but EvalLocalRules
# (Stage 6) takes a structured JSON array. We rewrite the body so
# future edits use the validated form. The conversion uses the same
# regex ApplyRegExpRules does so parses are bit-identical.
# ----------------------------------------------------------------
log_msg "step 3/3: rewriting rule pages to JSON in destination";
if ($dry_run) {
    log_msg "  (skipped under --dry-run)";
} else {
    my $dst =
      DBI->connect( $dest_dsn, $dest_user, $dest_pass,
        { RaiseError => 1, AutoCommit => 1, PrintError => 0 } )
      or die "dest connect failed: $DBI::errstr\n";

    my $rule_re = qr/\.(?:v[01]|e[01])$/;
    my $rows    = $dst->selectall_arrayref(
            "SELECT id, text FROM page WHERE id LIKE '%.v0' OR id LIKE '%.v1' "
          . "OR id LIKE '%.e0' OR id LIKE '%.e1'" );
    my ( $converted, $skipped ) = ( 0, 0 );
    for my $row ( @{ $rows || [] } ) {
        my ( $id, $body ) = @$row;
        next unless ( $id =~ $rule_re );
        my $json = legacy_rules_to_json($body);
        if ( !defined $json ) {
            log_msg "  skip $id (no parseable rules)";
            $skipped++;
            next;
        }

        # Skip pages already in JSON form (idempotent re-runs).
        if ( $body =~ /\A\s*\[/ ) {
            log_msg "  skip $id (already JSON)";
            $skipped++;
            next;
        }
        $dst->do( "UPDATE page SET text=? WHERE id=?", undef, $json, $id );
        $dst->do(
            "UPDATE page_revisions SET text=? WHERE page_id=? "
              . "AND revision=(SELECT revision FROM page WHERE id=?)",
            undef, $json, $id, $id
        );
        $converted++;
        log_msg "  converted $id";
    }
    log_msg "  rule pages: $converted converted, $skipped skipped";
    $dst->disconnect;
}

log_msg "done.";
log_msg "outputs:";
log_msg "  new config : $new_config" . ( $dry_run ? "  (would be written)" : "" );
log_msg "  new db     : $dest_dsn" .   ( $dry_run ? "  (would be written)" : "" );
log_msg "next: point habitatdb/config at the new DB / Postgres DSN and";
log_msg "      diff $new_config against your old config before swapping.";

# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

# Convert a legacy line-oriented rule body into a JSON array. The
# parser mirrors ApplyRegExpRules: each non-blank, non-comment line
# is either `from/to[/flags]` (regex rewrite), `GREP pattern`,
# `HEAD N`, or `TAIL N`. GREP/HEAD/TAIL have no JSON equivalent and
# are preserved verbatim as `{op: 'GREP', arg: ...}` so they can be
# round-tripped by a future tooling pass.
#
# Returns the JSON string, or undef if the body has no parseable
# rules (caller can choose to leave the body alone in that case).
sub legacy_rules_to_json {
    my ($body) = @_;
    return undef if ( !defined $body || $body !~ /\S/ );

    # Continuation: `\<LF>` joins lines, mirroring ApplyRegExpRules.
    my $FSA = "\x1eA";
    my $b   = $body;
    $b =~ s/\\\s*\r*\n/$FSA/g;

    my @rules;
    for my $line ( split /\n/, $b ) {
        $line =~ s/[\r\n]+$//;
        next if ( $line eq '' );

        if ( $line =~ /^GREP\s+(.*)/ ) { push @rules, { op => 'GREP', arg => $1 }; next; }
        if ( $line =~ /^HEAD\s+(.*)/ ) { push @rules, { op => 'HEAD', arg => $1 }; next; }
        if ( $line =~ /^TAIL\s+(.*)/ ) { push @rules, { op => 'TAIL', arg => $1 }; next; }

        # Same regex ApplyRegExpRules uses, so we accept exactly
        # the line set the wiki engine accepts.
        if ( $line =~ m{(.*[^\\])/(.*[^\\])(/([mgi])){0,1}$} ) {
            my ( $from, $to, $opt ) = ( $1, $2, $4 // '' );
            $to =~ s/\\\//\//g;
            $to =~ s/\\\$/\$/g;
            $to =~ s/\\N/\n/g;
            my %r = ( from => $from, to => $to );
            $r{opt} = $opt if ( $opt ne '' );
            push @rules, \%r;
        }

        # Unparseable lines are silently dropped (same behavior as
        # the runtime parser). A future strict mode could warn.
    }

    return undef if ( !@rules );
    my $enc = JSON::PP->new->canonical(1)->pretty(0);
    return $enc->encode( \@rules );
}
