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
use FindBin ();
use CGI::Emulate::PSGI;
use CGI::Compile;

# Make sure CGI-relative paths in the script ($DataDir = "./habitatdb"
# etc.) resolve to the script's own directory, regardless of where
# plackup/starman was invoked from.
chdir $FindBin::Bin or die "app.psgi: cannot chdir to $FindBin::Bin: $!";
$ENV{PWD} = $FindBin::Bin;

my $cgi_path = "$FindBin::Bin/index.cgi";
-f $cgi_path or die "app.psgi: $cgi_path not found";

# Compile the CGI script once into a Perl sub. CGI::Emulate::PSGI then
# sets up %ENV / STDIN / STDOUT for each request and invokes the sub.
my $cgi_sub = CGI::Compile->compile($cgi_path);
CGI::Emulate::PSGI->handler($cgi_sub);
