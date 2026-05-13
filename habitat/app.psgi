# PSGI entrypoint for the Habitat wiki.
#
# Local dev (single process, auto-reload not required for this use):
#     plackup -p 51712 app.psgi
#
# Production (multi-worker preforking server):
#     starman --workers 8 --listen 127.0.0.1:51712 app.psgi
#     (typically behind nginx/Apache as a reverse proxy; set
#      $TrustedProxies in config so X-Forwarded-For/X-Forwarded-Proto
#      are honored from the upstream IP only.)
#
# The CGI deployment (cgi-bin/index.cgi under Apache mod_cgi or
# python3 -m http.server --cgi via runlocal.sh) keeps working
# unchanged; PSGI is an additional, faster runner.

use strict;
use warnings;
use File::Basename ();
use File::Spec ();
use Cwd ();
use CGI::Emulate::PSGI;
use CGI::Compile;

# __FILE__ is this app.psgi's own path even when loaded indirectly
# (Plack::Util::load_psgi from a test, mod_perl, etc.); FindBin::Bin
# would resolve to the caller's $0 dir instead.
my $here = Cwd::abs_path( File::Basename::dirname(__FILE__) )
  or die "app.psgi: cannot resolve own directory";

# Make sure CGI-relative paths in the script ($DataDir = "./habitatdb"
# etc.) resolve to the script's own directory, regardless of where
# plackup/starman was invoked from.
chdir $here or die "app.psgi: cannot chdir to $here: $!";
$ENV{PWD} = $here;

my $cgi_path = "$here/index.cgi";
-f $cgi_path or die "app.psgi: $cgi_path not found";

# Compile the CGI script once into a Perl sub. CGI::Emulate::PSGI then
# sets up %ENV / STDIN / STDOUT for each request and invokes the sub.
my $cgi_sub = CGI::Compile->compile($cgi_path);
CGI::Emulate::PSGI->handler($cgi_sub);
