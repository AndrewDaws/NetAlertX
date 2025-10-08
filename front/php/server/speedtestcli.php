<?php
require dirname(__FILE__).'/../server/init.php';

// 🔺----- API ENDPOINTS SUPERSEDED -----🔺
// check server/api_server/api_server_start.py for equivalents
// equivalent: /nettools
// 🔺----- API ENDPOINTS SUPERSEDED -----🔺

//------------------------------------------------------------------------------
// check if authenticated
require_once  $_SERVER['DOCUMENT_ROOT'] . '/php/templates/security.php';

//exec('speedtest-cli --secure --simple', $output);
exec('PATH=/usr/bin/:/usr/local/bin:/opt/venv/bin speedtest-cli --secure --simple', $output);
echo '<h4>'. lang('Speedtest_Results') .'</h4>';
echo '<pre style="border: none;">'; 
foreach($output as $line){
    echo $line . "\n";
}
echo '</pre>';
?>
