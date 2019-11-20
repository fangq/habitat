#!/usr/bin/perl

# example:
#  page2git.pl "http://iso2mesh.sourceforge.net/cgi-bin/index.cgi" "jsonlab/Doc/JData" jdata

$CGI=$ARGV[0];
$wikipage=$ARGV[1];
$repo=$ARGV[2];

$pgname=(split(/\//,$wikipage))[-1];

%revs=();
@histpage=`lynx -dont_wrap_pre -dump '$CGI?action=history&id=$wikipage'`;
foreach $line (@histpage){
	if($line =~ /\([ \*]\)\s*\([ \*]\).*Revision\s+([0-9\.]+)\s*\.\s*\.\s*(\(\w+\))*\s*(.*)\s*by\s*(\[\d+\])*(\w+)/){
		$dstr=`date --date='$3'`;
		$etime=`date --date='$3' +%s`;
		$rev=$1;
		$auth=$5;
		$dstr=~s/[\r\n]//g;
		$etime=~s/[\r\n]//g;
		$revs{$etime}=[$rev,$dstr,$auth];
	}
}
mkdir $repo;
chdir $repo;
system('git init');
foreach $etime (sort keys %revs){
	$rev=$revs{$etime}[0];
	qsystem("lynx -dont_wrap_pre -dump '$CGI?action=browse&id=$wikipage&revision=$rev&raw=1' > $pgname.wiki");
        qsystem("git add $pgname.wiki");
        qsystem("GIT_COMMITTER_DATE='$revs{$etime}[1]' GIT_AUTHOR_DATE='$revs{$etime}[1]' git commit --date '$revs{$etime}[1]' -m '$CGI?action=browse&id=$wikipage&revision=$rev'");
	print "$rev $etime -> committed\n";
}
sub qsystem{
	#print join('',@_)."\n";
	system(join('',@_));
}
