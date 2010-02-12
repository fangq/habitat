#!/usr/bin/env perl

use strict;
use vars qw($FS $FS1 $FS2 $FS3 $FS4 $RCName);

$FS = "\x1e"; # The FS character is a superscript "3"
$FS1 = $FS . "1"; # The FS values are used to separate fields
$FS2 = $FS . "2"; # in stored hashtables and other data structures.
$FS3 = $FS . "3"; # The FS character is not allowed in user data.
$FS4 = $FS . "4"; # The FS character is not allowed in user data.
$RCName      = "ChangeLog";

sub ReadFile {
  my ($fileName) = @_;
  my ($data);
  local $/ = undef; # Read complete files

  if (open(IN, "<$fileName")) {
    $data=<IN>;
    close IN;
    return (1, $data);
  }
  return (0, "");
}
sub ParseRCLog{
  my ($RcFile)=@_;
  my ($fileData, $rcline, $i, $daysago, $lastTs, $ts, $idOnly, 
      $pagename, $summary, $isEdit, $host, $kind, $extraTemp);
  my (@fullrc, $status, $oldFileData, $firstTs, $errorText, $showHTML,%extra);
  my $starttime = 0;
  my $showbar = 0;

  ($status, $fileData) = &ReadFile($RcFile);
  $errorText = "";
  if (!$status) {
    # Save error text if needed.
    $errorText = sprintf('Could not open %s log file', $RCName)
                 . ":</strong> $RcFile <p>"
                 . 'Error was' . ":\n<pre>$!</pre>\n" . '<p>'
    . 'Note: This error is normal if no changes have been made.' . "\n" ;
  }
  @fullrc = split(/\n/, $fileData);
  foreach $rcline (@fullrc) {
    ($ts, $pagename, $summary, $isEdit, $host, $kind, $extraTemp)
      = split(/$FS3/, $rcline);
    %extra = split(/$FS2/, $extraTemp, -1);
    print <<EEOFRC;
INSERT INTO "rclog" VALUES($ts,'$pagename','$summary',$isEdit,'$host','$kind',
'$extra{'id'}','$extra{'name'}',$extra{'revision'},NULL);
EEOFRC
  }
}
if(@ARGV >= 1){
   ParseRCLog($ARGV[0]);
}else{
   ParseRCLog('wiki2db/rclog');
}

