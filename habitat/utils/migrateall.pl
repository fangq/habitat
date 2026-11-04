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
#   Rule pages (.v0/.v1/.e0/.e1) are copied verbatim. The engine applies
#   them with ApplyRegExpRules, which only reads the line-oriented
#   `from/to/opt` form; rewriting them to JSON (as an earlier version of
#   this script did) broke every page that inherits a rule.
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
log_msg "step 1/2: rewriting config -> $new_config";
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
log_msg "step 2/2: invoking utils/migrate.pl";
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

log_msg "done.";
log_msg "outputs:";
log_msg "  new config : $new_config" . ( $dry_run ? "  (would be written)" : "" );
log_msg "  new db     : $dest_dsn" .   ( $dry_run ? "  (would be written)" : "" );
log_msg "next: point habitatdb/config at the new DB / Postgres DSN and";
log_msg "      diff $new_config against your old config before swapping.";

