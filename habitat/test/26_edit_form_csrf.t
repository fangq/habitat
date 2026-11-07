#!/usr/bin/env perl
# The edit page's form is written by hand (<form name="myform">, which
# the editor scripts refer to) instead of through GetFormStart, so it
# has to add the CSRF token itself. Without it DoPost's CSRFCheckOrDie
# refused every save with "CSRF token missing or invalid".

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
HabitatEngine::InitLinkPatterns();
$HabitatEngine::UseCaptcha = 0;
$HabitatEngine::LangID     = '';
*HabitatEngine::UserCanEdit = sub { 1 };

# A logged-in account, as the edit -> save round trip runs for real users.
$HabitatEngine::UserID = 1001;
%HabitatEngine::UserData = ( id => 1001, username => 'alice' );

sub run {
    my ( $sub, $form, @args ) = @_;
    $HabitatEngine::q = CGI->new($form);
    my $out = '';
    my $exited;
    {
        local *STDOUT;
        open( STDOUT, '>', \$out ) or die;
        eval { $sub->(@args); 1 } or do { $exited = ( $@ eq "EXIT\n" ); die $@ unless $exited };
        close STDOUT;
    }
    return ( $out, $exited ? 1 : 0 );
}

my $id = 'CsrfEditFormTest';
my ($page) = run( \&HabitatEngine::DoEdit, {}, $id, 0, 0, '', 0 );
my ($form) = $page =~ /(<form[^>]*name="myform">.*?<\/form>)/s;
ok( $form, 'edit page has the myform edit form' ) or diag( substr( $page, 0, 2000 ) );
$form //= '';
like( $form, qr/<textarea/, 'it is the form with the text area' );

my ($tok) = $form =~ /name="csrf_token" value="([^"]+)"/;
ok( $tok, 'edit form carries a csrf_token' );
is( HabitatEngine::VerifyCSRFToken($tok), 1, 'and it verifies for the same user' );

# Submit the form's hidden fields back, as the browser does.
my %post = ( $form =~ /<input type="hidden" name="([^"]+)" value="([^"]*)"/g );
$post{text}    = "saved through the edit form\n";
$post{summary} = 'csrf test';
$post{Save}    = 'Save';
my ( $out, $exited ) = run( \&HabitatEngine::DoPost, \%post );
unlike( $out, qr/CSRF token missing or invalid/, 'save is not refused as CSRF' ) or diag($out);
my ($saved) = $dbh->selectrow_array( 'SELECT text FROM page WHERE id=?', undef, $id );
like( $saved // '', qr/saved through the edit form/, 'page text was saved' );

# Still refused without the token.
delete $post{csrf_token};
$post{text} = "forged\n";
{
    local $SIG{__WARN__} = sub { warn $_[0] unless $_[0] =~ /CSRF check failed/ };
    ( $out, $exited ) = run( \&HabitatEngine::DoPost, \%post );
}
like( $out, qr/CSRF token missing or invalid/, 'a save without the token is still refused' );
($saved) = $dbh->selectrow_array( 'SELECT text FROM page WHERE id=?', undef, $id );
unlike( $saved // '', qr/forged/, 'and nothing was written' );

done_testing;
