#!/opt/CSCperl/current/bin/perl -w
#!/m1/oracle/app/oracle/product/11.2.0/db_1/perl/bin/perl


# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is the Holdings XML Script.
#
# The Initial Developer of the Original Code is
# Ere Maijala, The National Library of Finland.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s): Minttu Hurme, Nicholas Volk
#
# Alternatively, the contents of this file may be used under the
# terms of the GNU General Public License Version 2 or later (the
# "GPL"), in which case the provisions of the GPL are applicable
# instead of those above.  If you wish to allow use of your
# version of this file only under the terms of the GPL and not to
# allow others to use your version of this file under the MPL,
# indicate your decision by deleting the provisions above and
# replace them with the notice and other provisions required by
# the GPL.  If you do not delete the provisions above, a recipient
# may use your version of this file under either the MPL or the
# GPL.
#
# ***** END LICENSE BLOCK *****
#
# v.1.7 (merge) 
#
# - merged NV's and MH's code
# - $settings{'exclude_locations'} support
#
# Holdings XML script v.1.6 (nvolk)
#
# - Updated perl and oracle path to support Voyager 9.2.1
# - Fixed SYSHOI-5607
# - removed iso-latin-1 characters
# - restructured code a bit

# Holdings XML script v1.5.
# This script is installed in Voyager's /m1/voyager/xxxdb/webvoyage/cgi-bin (Classic WebVoyage)
# or /m1/voyager/xxxdb/tomcat/vwebv/context/vwebv/htdocs (Tomcat WebVoyage)
#
# (NV: is WV path always correct? check...)
#
# Command line guidelines on updating $0 on each DB on the server:
#
# 0. copy the latest getHoldings.cgi to /tmp/
#
# 1. chmod 775 /tmp/getHoldings.cgi
#
# 2. execute command in BASH shell:
#
#  for i in `for j in /m1/www/* /m1/voyager/*db/tomcat /m1/voyager/*db/webvoyage; do find $j -name "getHoldings.cgi"; done`; do echo "if [ -e $i ]; then mv $i $i.old; fi"; echo cp /tmp/getHoldings.cgi $i; echo chmod 775 $i; done > /tmp/foo.sh
#
# 3. check manually /tmp/foo.sh
#
# 4. if satisfied, execute 'bash /tmp/foo.sh' (without quotes)
#

# CGI must be enabled for this and other cgi scripts:
# Edit the appropriate Apache {xxxdb}_vwebv_httpd.conf file in
# /m1/shared/apache2/conf/ActivatedVirtualHosts/
#
# Add the following within the <VirtualHost *:{port}> section:
#
#       # Allow for execution of CGI scripts
#       AddHandler cgi-script .cgi
#       <Directory "/m1/voyager/{xxxdb}/tomcat/vwebv/context/vwebv/htdocs">
#               Options MultiViews
#               AllowOverride None
#               Options ExecCGI
#               Order allow,deny
#               Allow from all
#       </Directory>
#
#  Restart Apache in order for the configuration change to take effect. / edit.18.10.2017

use strict;
use DBI;
use CGI qw(:standard);
use Cwd 'abs_path';
use File::Basename qw(dirname);
use Encode;

our %settings = ();

sub get_env_file() {
  my ( $env_file ) = abs_path($0) =~ /^(.*?db\/)/;
  $env_file .= 'ini/voyager.env';
  if ( -e $env_file ) { return $env_file; }

  my $dir = dirname(abs_path($0));
  $env_file = $dir . '/../../ini/voyager.env';
  if ( -e $env_file ) { return $env_file; }

  $env_file = $dir . '/../../../../../ini/voyager.env' if (! -e $env_file);
  if ( -e $env_file ) { return $env_file; }

  $env_file = $dir . '/../../../../../../ini/voyager.env' if (! -e $env_file);
  if ( -e $env_file ) { return $env_file; }


  return '';
}



sub get_db_params() {
  my $env_file = get_env_file();
  my $fh;

  open($fh, "<$env_file") || fail("Could not open env file '$env_file': $!");

  my $got_userpass = 0;
  my $got_tablespace = 0;
  my $got_oracle_home = 0;
  while (my $line = <$fh>) {
    chomp($line);
    if ( $line =~ /^\s*export\s+ORACLE_HOME\s*=\s*(\S+)/ ) {
      $settings{'oracle_home'} = $1;
      $got_oracle_home = 1;
    }
    elsif ( $line =~ /export\s+USERPASS\s*=\s*(\w+)\/(\w+)/ ) {
      $settings{'db_username'} = $1;
      $settings{'db_password'} = $2;
      $got_userpass = 1;
    }
    if ( $line =~ /export\s+DATABASE\s*=\s*(\w+)/ ) {
      $settings{'db_tablespace'} = $1;
      $got_tablespace = 1;
    }
    last if ($got_userpass && $got_tablespace && $got_oracle_home );
  }
  close($fh);
}


sub get_oracle_home() {
  my @oracle_homes =
    ( '/m1/oracle/app/oracle/product/12.1.0.2/db_1/',
      '/m1/oracle/app/oracle/product/11.2.0/db_1',
      '/m1/oracle/app/oracle/product/10.2.0/db_1',
      '/m1/oracle/app/oracle/product/9.2.0' );
  for ( my $i=0; $i <= $#oracle_homes; $i++ ) {
    my $oracand = $oracle_homes[$i];
    if ( -d $oracand ) {
      return $oracand;
    }
    if ( $oracand =~ s/^\/m1\//\// ) {
      if ( -d $oracand ) {
	return $oracand;
      }
    }
  }
  return undef;
}

sub init_settings() {
  $settings{'db_params'} = 'host=localhost;sid=VGER'; # host=xxx;sid=VGER
  # Read env/voyager.ini
  &get_db_params();

  # Database settings
  $ENV{ORACLE_SID} = 'VGER';

  if ( $settings{'oracle_home'} && -d $settings{'oracle_home'} ) {
    $ENV{ORACLE_HOME} = $settings{'oracle_home'};
  }
  else {
    $ENV{ORACLE_HOME} = &get_oracle_home();
    if ( !defined($ENV{ORACLE_HOME}) ) {
      # do something?
    }
  }


  # location.location_codes for those locations which should not be shown
  #
  # note: case-sensitive, each location code should be surrounded with single quotes and separated with comma
  # note: this setting should include non-existing location code, if no filtering is wished
  #
  # Examples:
  # $settings{'exclude_locations'}="\'pienp\',\'mikrof\'";
  # $settings{'exclude_locations'}="\'xxx\'";
  my $ap = abs_path($0);
  if ( $ap =~ /heliadb/ ) {
    $settings{'exclude_locations'}= "'Porvooref','Porvooshor','Porvoostaf','Porvoojour'";
  }


}


  my $data = " " ;   #  info about bib ids found etc


sub get_bib_id($$) {
  my ( $dbh, $tablespace ) = @_;
  my $local_bib_id = param('localBibId');

  if ( $local_bib_id ) {
    if ( $local_bib_id =~ /\D/ ) {
      fail('Invalid parameter');
    }
             # return $local_bib_id;      
  }

  my $global_bib_id = param('globalBibId');

  if ( !$global_bib_id ) {
    fail('Missing parameters');
  }
  if ( $global_bib_id =~ /\D/ ) {
    fail('Invalid parameter');
  }




  my $count_loc = 0; 
  my $count_glob = 0;
  my @collectedBibs;

  my @LocalBibs = param('localBibId');
     foreach my $name (@LocalBibs) {
       my $value = $name;
       $count_loc = $count_loc + 1; 
     }
 

  my @GlobalBibs = param('globalBibId');
     foreach my $name (@GlobalBibs ) {
       my $value = $name;
       $count_glob = $count_glob + 1;
              push(@collectedBibs,$value);
     }



  my $date_sth = $dbh->prepare("alter session set nls_date_format = 'yyyy.mm.dd hh24:mi:ss'") || die($dbh->errstr);
  $date_sth->execute() || die($dbh->errstr);
  $date_sth->finish();

  # Convert parameter bib id to local bib id:
  my $bib_id = undef;

  if ( $count_loc >=1 ) {
   foreach my $name (@LocalBibs) {
     my $sth = $dbh->prepare("SELECT BIB_ID FROM ${tablespace}BIB_TEXT WHERE BIB_ID = ?") || fail($dbh->errstr);
     $sth->execute($name) || die($dbh->errstr);
         if (my (@row) = $sth->fetchrow_array()) {
         $bib_id = $row[0];
       }
     $sth->finish();
       if (!$bib_id) {
          $dbh->disconnect();
          fail('Bib record not found/Local...');
         } else {
         push(@collectedBibs,$bib_id);
       }
          # return $bib_id;     
   } 
      # return $bib_id;
  }       

         my $previous="";                 # deduplicate ->
         my @sortedArray = sort(@collectedBibs);
            @collectedBibs = @sortedArray;
         my @collectedBibsSec;

       foreach my $found (@collectedBibs) {
          chomp($found);

           if ($previous eq $found) { }  # skip
            else {
              push(@collectedBibsSec,$found);
              $previous = $found;
           }
       } 


                  my $count=0;
		  my $pieceString="";
		foreach my $piece (@collectedBibsSec) {
		    $pieceString .= $piece . "   ";	
		    $count = $count +1;
                }


            if ($count == 0) {
                    $data .= "  Bib record not found. ";
                } elsif ($count == 1)  {
                    $data .= "  Bib record found: " .  @collectedBibsSec[0] ;
			$bib_id = @collectedBibsSec[0] ; 	                         
			        # return $bib_id;   #  return later 
                } elsif ($count > 1) {
                    $data .= "  Several bib records found: " . $pieceString ;
                } else {
                    $data .= "  ???" . $count ;
                }
       
#original:
#  my $sth = $dbh->prepare("SELECT BIB_ID FROM ${tablespace}BIB_INDEX WHERE INDEX_CODE='035A' AND NORMAL_HEADING=?") || fail($dbh->errstr);
#  $sth->execute("FCC$global_bib_id") || die($dbh->errstr);
#  if (my (@row) = $sth->fetchrow_array()) {
#    $bib_id = $row[0];
#  }
#  $sth->finish();
#  if (!$bib_id) {
#    $dbh->disconnect();
#    fail('Bib record not found');
#  }


   return $bib_id;   # checked ids


}



sub get_bib_record($$$) {
  my ( $dbh, $bib_id, $tablespace ) = @_;
  # Get marc record:
  my $bib_marc_sql = qq|
select record_segment
  from ${tablespace}bib_data
  where bib_id=?
  order by seqnum
|;

  my $bib_marc_sth = $dbh->prepare($bib_marc_sql) || die($dbh->errstr);

  my $marcstr = '';
  my $found = 0;
  $bib_marc_sth->execute($bib_id) || die($dbh->errstr);
  while (my (@marc_row) = $bib_marc_sth->fetchrow_array())
  {
    $marcstr .= $marc_row[0];
    $found = 1;
  }
  $bib_marc_sth->finish();

  if (!$found)
  {
    $dbh->disconnect();
    fail('Bib record not found');
  }

  return $marcstr;
}


sub cleanup_str($)
{
  my ($str) = @_;

  $str =~ s/[\x00-\x1f]/ /g;
  return $str;
}

sub iso2709_to_marcxml($$)
{
  my ($a_marc, $a_type) = @_;

  my $leader = cleanup_str(substr($a_marc, 0, 24));
  # Fix last characters of leader
  $leader = xml_encode(substr($leader, 0, 22) . '00');

  my $fields = "      <leader>$leader</leader>\n";

  my $dirpos = 24;
  my $base = substr($a_marc, 12, 5);
  while (ord(substr($a_marc, $dirpos, 1)) != 0x1e && $dirpos < length($a_marc))
  {
    my $field_code = xml_encode(substr($a_marc, $dirpos, 3));
    my $len = substr($a_marc, $dirpos + 3, 4);
    my $pos = substr($a_marc, $dirpos + 7, 5);

    if ($field_code < 10)
    {
      my $field = xml_encode(substr($a_marc, $base + $pos, $len));
      $field =~ s/\x1e$//g;
      $fields .= "      <controlfield tag=\"$field_code\">$field</controlfield>\n";
    }
    else
    {
      my $ind1 = substr($a_marc, $base + $pos, 1);
      my $ind2 = substr($a_marc, $base + $pos + 1, 1);
      my $field = substr($a_marc, $base + $pos + 2, $len - 2);
      $fields .= "      <datafield tag=\"$field_code\" ind1=\"$ind1\" ind2=\"$ind2\">\n";

      my @subfields = split(/[\x1e\x1f]/, $field);
      foreach my $subfield (@subfields)
      {
        my $subfield_code = xml_encode(substr($subfield, 0, 1));
        next if ($subfield_code eq '');

        my $subfield_data = xml_encode(substr($subfield, 1, length($subfield)));
        if ($subfield_data ne '')
        {
          $fields .= "        <subfield code=\"$subfield_code\">$subfield_data</subfield>\n";
        }
      }
      $fields .= "      </datafield>\n";
    }
    $dirpos += 12;
  }

  my $str = qq|    <record xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.loc.gov/MARC21/slim
     http://www.loc.gov/standards/marcxml/schema/MARC21slim.xsd"
     type="$a_type">
$fields    </record>
|;

  return $str;
}

sub fail($)
{
  my ($msg) = @_;

  print header(-type => 'text/xml', -charset => 'UTF-8', -expires => 'Thu, 25-Apr-1999 00:00:00 GMT');
  $msg = xml_encode($msg);
  print qq|<?xml version=\"1.0\" encoding=\"utf-8\"?>

<holdings>
  <diagnostics>
    <error>$msg</error>
  </diagnostics>
</holdings>
|;
  print STDERR "FAIL: $msg\n";
  exit 1;
}

sub xml_encode($)
{
  my ($str) = @_;
  if ( !defined($str) ) { return ''; }

  $str =~ s/&/&amp;/g;
  $str =~ s/\"/&quot;/g;
  $str =~ s/>/&gt;/g;
  $str =~ s/</&lt;/g;
  $str =~ s/[\x00-\x1f]+$//;
  $str =~ s/[\x00-\x1f]+/ /g;

  return $str;
}




# MAIN
{
  binmode(STDOUT, ":utf8");

  &init_settings();

  my $dbh = DBI->connect("dbi:Oracle:$settings{'db_params'}", $settings{'db_username'}, $settings{'db_password'}) || die "  Could not connect: $DBI::errstr";

  my $tablespace = $settings{'db_tablespace'};
  $tablespace .= '.' if ($tablespace && substr($tablespace, length($tablespace) - 1) ne '.');

  my $bib_id = &get_bib_id($dbh, $tablespace);

  my $marcstr = &get_bib_record($dbh, $bib_id, $tablespace);

  # Parse holdings:
  my $xml = "<holdings>\n";

  $xml .= '  <bib bibId="' . xml_encode($bib_id) . '">' . "\n";
  $xml .= decode_utf8(iso2709_to_marcxml($marcstr, 'Bibliographic'));
  $xml .= "  </bib>\n";


  my $mfhd_sql = qq|
select mfhd.mfhd_id, mfhd.display_call_no
  from ${tablespace}mfhd_master mfhd
  where mfhd.mfhd_id in (select mfhd_id from ${tablespace}bib_mfhd bmf where bmf.bib_id = ? and bmf.bib_id in (select bm.bib_id from ${tablespace}bib_master bm where bm.bib_id=bmf.bib_id and suppress_in_opac='N'))
    and suppress_in_opac = 'N'
  order by mfhd.normalized_call_no
|;

  # Use MHs exclude location:
  if ( defined($settings{'exclude_locations'}) ) {
    my $exclude_locations = $settings{'exclude_locations'};
    if ( $exclude_locations =~ /\S/ ) {
      $mfhd_sql = qq|
select mfhd.mfhd_id, mfhd.display_call_no
  from ${tablespace}mfhd_master mfhd, ${tablespace}location loc
  where mfhd.mfhd_id in (select mfhd_id from ${tablespace}bib_mfhd bmf where bmf.bib_id = ? and bmf.bib_id in (select bm.bib_id from ${tablespace}bib_master bm where bm.bib_id=bmf.bib_id and suppress_in_opac='N'))
    and mfhd.suppress_in_opac = 'N'
    and mfhd.location_id = loc.location_id
    and loc.location_code not in (${exclude_locations})
  order by mfhd.normalized_call_no
|;
    }
  }

  my $mfhd_sth = $dbh->prepare($mfhd_sql) || die($dbh->errstr);
  $mfhd_sth->execute($bib_id) || die($dbh->errstr);


  my $marc_sql = qq|
select record_segment

  from ${tablespace}mfhd_data
  where mfhd_id=?
  order by seqnum
|;

  my $marc_sth = $dbh->prepare($marc_sql) || die($dbh->errstr);


  my $item_sql = qq|
select item.item_id, permloc.location_display_name, temploc.location_display_name, circ.current_due_date
  from ${tablespace}item item
  left outer join ${tablespace}location permloc on (item.perm_location = permloc.location_id)
  left outer join ${tablespace}location temploc on (item.temp_location = temploc.location_id)
  left outer join ${tablespace}circ_transactions circ on (item.item_id = circ.item_id)
  where item.item_id in (select item_id from ${tablespace}mfhd_item mi where mi.mfhd_id = ?)
  order by item.item_id
|;

  my $item_status_sql = qq|
select its.item_status, its.item_status_date
  from ${tablespace}item_status its
  where its.item_id = ?
  order by its.item_status_date
|;


  my $item_sth = $dbh->prepare($item_sql) || die($dbh->errstr);
  my $item_status_sth = $dbh->prepare($item_status_sql) || die($dbh->errstr);


  while (my (@row) = $mfhd_sth->fetchrow_array())
  {
    my ($mfhd_id, $mfhd_call_no) = @row;

    $mfhd_call_no = decode_utf8($mfhd_call_no);

    $xml .= '  <mfhd mfhdId="' . xml_encode($mfhd_id) . '" mfhdCallNo="' . xml_encode($mfhd_call_no) . '">' . "\n";

    $marc_sth->execute($mfhd_id) || die($dbh->errstr);
    $marcstr = '';
    while (my (@marc_row) = $marc_sth->fetchrow_array())
    {
      $marcstr .= $marc_row[0];
    }
    $marc_sth->finish();

    $xml .= decode_utf8(iso2709_to_marcxml($marcstr, 'Holdings'));

    $item_sth->execute($mfhd_id) || die($dbh->errstr);
    my $item_xml = "    <items>\n";
    while (my (@item_row) = $item_sth->fetchrow_array())
    {
      my ($item_id, $item_perm_loc, $item_temp_loc, $item_due_date) = @item_row;

      $item_xml .= '      <item itemId="' . xml_encode($item_id) . '" permLocation="' . xml_encode($item_perm_loc) . '" tempLocation="' . xml_encode($item_temp_loc) . '" dueDate="' . xml_encode($item_due_date) . '">' . "\n";

      $item_status_sth->execute($item_id) || die($dbh->errstr);
      while (my (@status_row) = $item_status_sth->fetchrow_array())
      {
        my ($status, $date) = @status_row;

        $item_xml .= '        <status code="' . xml_encode($status) . '" date="' . xml_encode($date) . '"/>' . "\n";
      }
      $item_status_sth->finish();
   
    $item_xml .= "      </item>\n";
    }
    $item_sth->finish();

         $item_xml .= $data;  # info about bib ids found

    $item_xml .= "    </items>\n";

    $xml .= $item_xml;
    $xml .= "  </mfhd>\n";
  }
  $mfhd_sth->finish();
  $dbh->disconnect();

  $xml .= '</holdings>';

  $xml = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n\n$xml\n";

  # This apparently expires on purpose...
  print header(-type => 'text/xml', -charset => 'UTF-8', -expires => 'Thu, 25-Apr-1999 00:00:00 GMT');
  print $xml;
}


