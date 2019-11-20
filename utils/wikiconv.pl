#!/usr/bin/env perl

use lib "./lib";
use strict;

#use Text::Iconv;
use Text::Diff;
#use Text::Patch;

use vars qw($DataDir $KeepDir $PageDir $RcFile %Pages
$OpenPageName $FS $FS1 $FS2 $FS3 $FS4 $FS5 $q  $UsePerlDiff
%KeptRevisions $NewFS %Translate $Now $UserID $NewText
$UCS2Str $UCS2Num $cvUTF8ToUCS2);

if(@ARGV>=1){
   $DataDir     = $ARGV[0]; # Main wiki directory
}else{
   $DataDir     = "./wiki2db"; # Main wiki directory
}
$PageDir     = "$DataDir/page";     # Stores page data
$KeepDir     = "$DataDir/keep";     # Stores kept (old) page data
$RcFile      = "$DataDir/rclog";    # New RecentChanges logfile
$NewFS       = 0;
$Now = time; # Reset in case script is persistent
%Pages=('page'=>(),'text'=>(),'section'=>(),'embed'=>());
$UsePerlDiff=1;
#$cvUTF8ToUCS2 = new Text::Iconv( 'UTF-8', 'UNICODELITTLE')
#                or die "Can't create enc2utf converter";

if ($NewFS) {
  $FS = "\x1e\xff\xfe\x1e"; # An unlikely sequence for any charset
} else {
  $FS = "\x1e"; # The FS character is a superscript "3"
}
$FS1 = $FS . "1"; # The FS values are used to separate fields
$FS2 = $FS . "2"; # in stored hashtables and other data structures.
$FS3 = $FS . "3"; # The FS character is not allowed in user data.
$FS4 = $FS . "4"; # The FS character is not allowed in user data.
$FS5 = $FS . "5"; # The FS character is not allowed in user data.

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
sub ReadFileOrDie {
  my ($fileName) = @_;
  my ($status, $data);

  ($status, $data) = &ReadFile($fileName);
  if (!$status) {
    die(Ts('Can not open %s', $fileName) . ": $!");
  }
  return $data;
}

sub GetPageDirectory {
  my ($id) = @_;
  my $subdir;
  my @letters;

  if($id =~ /^U([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])([0-9A-F]*).WQYS/)
  {
            return "other/vec/$2";
   }

  if($id =~ /^U([0-9A-F][0-9A-F])[0-9A-F][0-9A-F]/)
  {
            return "U/$1";
   }
	      
  if ($id =~ /^([a-zA-Z])/) {
    return uc($1);
  }
  if($id =~ /^([\x80-\xff][\x80-\xff][\x80-\xff])/)
  {
	@letters = unpack("C*", $1);
	$subdir= sprintf("%02X",$letters[1]);
	return "other/$subdir";
  }
  if($id =~ /^([\x80-\xff][\x80-\xff][\x80-\xff]).WQYS/)
#  || $id=~/^\(draft\)([\x80-\xff][\x80-\xff][\x80-\xff]).WQYS/)
  {
      if($UCS2Str=~/^([0-9A-F][0-9A-F])([0-9A-F][0-9A-F])/){
	return "other/vec/$2";
      }
      else{
        @letters = unpack("C*", $1);
        $subdir= sprintf("%02X",$letters[1]);
        return "other/vec/$subdir";
      }
  }

  return "other";
}
sub BuildUCScodeNew
{
   my ($pgid)=@_;
   if($pgid=~/^\(draft\)UNI_(.*)_([89101234]*)p[tx]/ || $pgid=~/^UNI_(.*)_([89101234]*)p[tx]/
   || $pgid=~/^U([0-9A-Fa-f]+).WQYS/|| $pgid=~/^\(draft\)U([0-9A-Fa-f]+).WQYS/)
   {
        my $ucsbuf=hex($1);
        {
                $UCS2Num=$ucsbuf;
                $UCS2Str=sprintf("%X",$UCS2Num);
        }
   }
   elsif($pgid=~/^\(draft\)(.*)_([89101234]*)p[tx]/ || $pgid=~/^(.*)_([89101234]*)p[tx]/ )
   {
	my @ucsbuf=unpack("U0U*", $1);
        if(@ucsbuf==1)
        {
                $UCS2Num=$ucsbuf[0];
                $UCS2Str=sprintf("%X",$UCS2Num);
        }	
   }
   elsif( $pgid =~ /^([\x80-\xff][\x80-\xff][\x80-\xff])$/ ||$pgid=~/^([\x80-\xff][\x80-\xff][\x80-\xff]+)_VLOG$/
    ||$pgid=~/^([\x80-\xff][\x80-\xff][\x80-\xff]+).WQYS$/||$pgid=~/^\(draft\)([\x80-\xff][\x80-\xff][\x80-\xff]+).WQYS$/)
   {
#        $UCS2Num=unpack('S*',$cvUTF8ToUCS2->convert( $1 ) );
        $UCS2Str=sprintf("%X",$UCS2Num);
   }
}
sub GetPageFile {
  my ($id) = @_;

  return $PageDir . "/" . &GetPageDirectory($id) . "/$id.db";
}

sub OpenPage {
  my ($id) = @_;
  my ($fname, $data,$Page,$Text,$Section);

  $Page=\%{$Pages{$id}->{'page'}};
  $Section=\%{$Pages{$id}->{'section'}};
  $Text=\%{$Pages{$id}->{'text'}};

  if ($OpenPageName eq $id) {
    return;
  }
  %$Section = ();
  %$Text = ();
  $fname = &GetPageFile($id);

  if (-f $fname) {
    $data = &ReadFileOrDie($fname);

    %$Page = split(/$FS1/, $data, -1);
  }

#  if ($$Page{'version'} != 3) {
#    &UpdatePageVersion();
#  }
  $OpenPageName = $id;
}
sub OpenSection {
  my ($id,$name) = @_;
  my ($Page,$Section);
  
  $Page=\%{$Pages{$id}->{'page'}};
  $Section=\%{$Pages{$id}->{'section'}};

  if (!defined($$Page{$name})) {
    &OpenNewSection($id,$name, "");
  } else {
    %$Section = split(/$FS2/, $$Page{$name}, -1);
  }
}

sub OpenText {
  my ($id,$name) = @_;
  my ($Page,$Section,$Text);

  $Page=\%{$Pages{$id}->{'page'}};
  $Section=\%{$Pages{$id}->{'section'}};
  $Text=\%{$Pages{$id}->{'text'}};

  if (!defined($$Page{"text_$name"})) {
    &OpenNewText($id,$name);
  } else {
    &OpenSection($id,"text_$name");
    %$Text = split(/$FS3/, $$Section{'data'}, -1);
  }
}

sub OpenDefaultText {
  my ($id) = @_;
  &OpenText($id,'default');
}
sub OpenNewPage {
  my ($id) = @_;
  my ($pagehash,$Page);

  $Page=\%{$Pages{$id}->{'page'}};

  %$Page = ();
  $$Page{'version'} = 3; # Data format version
  $$Page{'revision'} = 0; # Number of edited times
  $$Page{'tscreate'} = $Now; # Set once at creation
  $$Page{'ts'} = $Now; # Updated every edit
}

sub OpenNewSection {
  my ($id,$name, $data) = @_;
  my ($Page,$Section);

  $Page=\%{$Pages{$id}->{'page'}};
  $Section=\%{$Pages{$id}->{'section'}};

  %$Section = ();
  $$Section{'name'} = $name;
  $$Section{'version'} = 1; # Data format version
  $$Section{'revision'} = 0; # Number of edited times
  $$Section{'tscreate'} = $Now; # Set once at creation
  $$Section{'ts'} = $Now; # Updated every edit
  $$Section{'ip'} = $ENV{REMOTE_ADDR};
  $$Section{'host'} = ''; # Updated only for real edits (can be slow)
  $$Section{'id'} = $UserID;
  $$Section{'username'} ="";
  $$Section{'data'} = $data;
  $$Page{$name} = join($FS2, %$Section); # Replace with save?
}

sub OpenNewText {
  my ($id,$name) = @_; # Name of text (usually "default")
  my ($Text);

  $Text=\%{$Pages{$id}->{'text'}};

  %$Text = ();
  $$Text{'isnew'}=1;
  if ($NewText ne '') {
    $$Text{'text'} = T($NewText);
  } else {
    $$Text{'text'} = T('Describe the new page here.') . "\n";
  }
  $$Text{'text'} .= "\n" if (substr($$Text{'text'}, -1, 1) ne "\n");
  $$Text{'minor'} = 0; # Default as major edit
  $$Text{'newauthor'} = 1; # Default as new author
  $$Text{'summary'} = '';
  &OpenNewSection($id,"text_$name", join($FS3, %$Text));
}

sub UpdatePageVersion {
  &ReportError(T('Bad page version (or corrupt page).'));
}
sub ReportError {
  my ($errmsg) = @_;

  print $errmsg;
}
sub OpenKeptList {
  my ($fname, $data);

  my @KeptList = ();
  $fname = &KeepFileName();
  return if (!(-f $fname));
  $data = &ReadFileOrDie($fname);
  @KeptList = split(/$FS1/, $data, -1); # -1 keeps trailing null fields
  return @KeptList;
}
sub KeepFileName {
  return $KeepDir . "/" . &GetPageDirectory($OpenPageName)
         . "/$OpenPageName.kp";
}

sub OpenKeptRevisions {
  my ($id,$name) = @_; # Name of section
  my ($fname, $data, %tempSection,@KeptList,$rev);

  @KeptList=&OpenKeptList();

  %KeptRevisions = ();
  foreach $rev (@KeptList) {
    next if($rev eq '');
    %tempSection = split(/$FS2/, $rev, -1);
    next if ($tempSection{'name'} ne $name);
    $KeptRevisions{$tempSection{'revision'}} = $rev;
  }
}

# Called after OpenKeptRevisions
sub OpenKeptRevision {
  my ($id,$revision) = @_;
  my ($Text,$Section);

  $Section=\%{$Pages{$id}->{'section'}};
  $Text=\%{$Pages{$id}->{'text'}};

  %$Section = split(/$FS2/, $KeptRevisions{$revision}, -1);
  %$Text = split(/$FS3/, $$Section{'data'}, -1);
  $$Text{'text'}=&PatchPage($$Text{'text'});
}

sub BuildWikiTree{
  my ($topDir,$baseDir)=@_;
  my $fcount;
  my (@dirs, @seg,$dir, $file, $fname, $sname, $lname, $currdir);
  my ($xmltext,$oo);
  my $treetext='';

  $fcount=0;
  $currdir=(reverse split(/\//,$topDir))[0];

  opendir(DIRLIST, $topDir);
  @dirs = readdir(DIRLIST);
  closedir(DIRLIST);
  @dirs = sort(@dirs);
  foreach $dir (@dirs) {
    next  if ($dir=~/\.$/ || $dir=~/\.\.$/);   # No ., .., or .dirs
    $fname = "$topDir/$dir";
    $sname = $dir;
    $sname =~ s/\.db$//;
    $lname = $fname;
    if($lname =~ /$baseDir\/(.+)$/) {$lname=$1;$lname=~s/\.db$//;}  # lname is page id
    if (-f $fname && $fname=~/\.db/) {
#        if(-d "$topDir/$sname") {next;}
	if($topDir=~/\/other\/[0-9A-F][0-9A-F]$/ && $lname=~/^[0-9A-F][0-9A-F]\/(.*)/){ $lname=$1;}
        $treetext.= "$lname\n";
        $fcount++;
    }elsif (-d $fname){
        if(-f "$fname\.db"){
          if($topDir=~/\/other\/[0-9A-F][0-9A-F]$/ && $lname=~/^[0-9A-F][0-9A-F]\/(.*)/){ $lname=$1;}
          $treetext.="$lname\n".&BuildWikiTree($fname,$baseDir);
        }else{
          $treetext.=&BuildWikiTree($fname,$baseDir);
        }
    }
  }
  return $treetext;
}

sub GenerateAllPagesList {
  my (@pages, @dirs, $id, $dir, @pageFiles, @subpageFiles, $subId,%saw,@out);

  @pages = ();
    # Old slow/compatible method.
    @dirs = qw(A B C D E F G H I J K L M N O P Q R S T U V W X Y Z other);
    foreach $dir (@dirs) {
      if (-e "$PageDir/$dir") {
         push(@pages, split(/\n/,&BuildWikiTree("$PageDir/$dir","$PageDir/$dir")));
      }
    }
    undef %saw;
    @out = grep(!$saw{$_}++, @pages);
    return sort(@out);
}
sub T {
  my ($text) = @_;

  if (defined($Translate{$text}) && ($Translate{$text} ne '')) {
    return $Translate{$text};
  }
  return $text;
}

sub GetDiff {
  my ($old, $new, $lock) = @_;
  my ($diff_out, $oldName, $newName, $key);

  if($UsePerlDiff){
      return diff(\$old, \$new, { STYLE => 'OldStyle' });
  }
}

sub PrintPageSQL{
   my ($id,$p,$KeptRev,$tx,$rev,$test)=@_;
   my ($summ,%s,%t);
   $tx=~ s/'/''/g;

   %s = split(/$FS2/, $KeptRev, -1);
   %t = split(/$FS3/, $s{'data'}, -1);
   $summ=$t{'summary'};
   $summ=~ s/'/''/g;
   $id=~ s/'/''/g;

   if($test!=1){
      print <<EESQL;
INSERT INTO "page" VALUES('$id',3,'$s{'username'}',$rev,$s{'ts'}, $$p{'tscreate'},
'$s{'ip'}','$s{'host'}','$summ','$tx',$t{'minor'},$t{'newauthor'},'$s{'id'}',NULL);
EESQL
   }
}
sub DumpSQL{
  my ($debug)=@_;
  my ($page,$Page,$Section,$Text,@pagelist,%sect,$bb,@revnum,$revision, $lasttime,
      %data,$count,$oldtext,$rev,$dif,$diffpatch, $content, $items, 
      @currrev);
  @pagelist=GenerateAllPagesList();
#  @pagelist=('TodoList');
#print(join("\n",@pagelist));
#exit;
  $items=0;
  foreach $page (@pagelist){
        BuildUCScodeNew($page);
        OpenPage($page);
	OpenDefaultText($page);
	OpenKeptRevisions($page,"text_default");
        $Page=\%{$Pages{$page}->{'page'}};
        $Section=\%{$Pages{$page}->{'section'}};
	$Text=\%{$Pages{$page}->{'text'}};
        $count=0;
	$diffpatch='';
	$rev=1;

	if($$Page{'version'}!=3){
	   next;
	}
        @revnum=sort {$a <=> $b} keys %KeptRevisions;
        $items+=@revnum+1;
        $KeptRevisions{$revnum[-1]+1}=join($FS2,%$Section);
	@revnum=sort {$a <=> $b} keys %KeptRevisions;
        @currrev=();
        undef $oldtext;

	foreach my $revision (@revnum) {
	  next if ($revision eq ""); # (needed?)
          %sect = split(/$FS2/, $KeptRevisions{$revision}, -1);
          %data = split(/$FS3/, $sect{'data'}, -1);
          $oldtext=$data{'text'}    if(!defined($oldtext));
	  $count++;
	  if($debug==1){
		print "$page [rev $revision] time $sect{ts}\n";
	  }
	  if($count>1){
	     if(not $oldtext=~/\n$/) {$oldtext.="\n";}
	     $dif=GetDiff($oldtext,$data{'text'});
             if($dif eq '') {next;}
             my $summ=$data{'summary'};
             $summ=~ s/'/''/g;
             my $revstr="$sect{'ts'}|$sect{'username'}|$sect{'host'}|$summ$FS5";
	     if($data{'minor'}==1 || length($dif)<length($oldtext)*0.25){
	        if($diffpatch eq ''){
		  	$diffpatch.=$oldtext."$FS4$revstr$dif";
		}else{
	          	$diffpatch.="$FS4$revstr$dif";
		}
		push(@currrev,$revision);
                $oldtext=$data{'text'};
		next if $revision<$revnum[-1];
	     }
	     $content=$diffpatch;
	     $content=$oldtext if($diffpatch eq '');
             if($debug==1){
                   print "===> $page [rev $revision] time $sect{ts} $rev, $count ".length($content)."[".join("/",@currrev)."]\n";
             }
	     PrintPageSQL($page,$Page,$KeptRevisions{$currrev[0]},$content,$rev++,$debug);
	     if($revision==$revnum[-1] && !($data{'minor'}==1 || length($dif)<length($oldtext)*0.25)){
		 @currrev=($revision);
		 $content=$data{'text'};
	         if($debug==1){
                     print "~~~> $page [rev $revision] time $sect{ts} $rev, $count ".length($content)."[".join("/",@currrev)."]\n";
	         }
		 PrintPageSQL($page,$Page,$KeptRevisions{$currrev[0]},$content,$rev++,$debug);
		 last;
	     }
	     $diffpatch='';
	     $oldtext=$data{'text'};
	     @currrev=();
	  }
          if(@revnum==1){
             if($debug==1){
                   print "---> $page [rev $revision] time $sect{ts} $rev, $count [".join("/",@currrev)."]\n";
             }
             PrintPageSQL($page,$Page,$KeptRevisions{$revision},$data{'text'},$rev++,$debug);
	     last;
          }
          $oldtext=$data{'text'};
	  push(@currrev,$revision);
	}
  }
  if($debug==1){ 
	print "dumped $items records\n";
  }
}

&DumpSQL(0);
