#!/usr/bin/env python

import os
import pathlib
import argparse
import sys
import re
import base64
import subprocess
from time import strftime


sys.path.append("/home/pi/pialert/front/plugins")
sys.path.append('/home/pi/pialert/pialert') 

from logger import mylog
from plugin_helper import Plugin_Object, Plugin_Objects
from const import fullPholusPath, logPath

CUR_PATH = str(pathlib.Path(__file__).parent.resolve())
LOG_FILE = os.path.join(CUR_PATH, 'script.log')
RESULT_FILE = os.path.join(CUR_PATH, 'last_result.log')


def main():
    # sample
    # /home/pi/pialert/front/plugins/pholus_scan/script.py userSubnets=b'MTkyLjE2OC4xLjAvMjQgLS1pbnRlcmZhY2U9ZXRoMQ==' timeoutSec=10
    # sudo docker exec pialert /home/pi/pialert/front/plugins/pholus_scan__ignore/script.py userSubnets=b'MTkyLjE2OC4xLjAvMjQgLS1pbnRlcmZhY2U9ZXRoMQ==' timeoutSec=10
    
    # the script expects a parameter in the format of userSubnets=subnet1,subnet2,...
    parser = argparse.ArgumentParser(description='Import devices from settings')
    parser.add_argument('userSubnets', nargs='+', help="list of subnets with options")
    parser.add_argument('timeoutSec', nargs='+', help="timeout")
    values = parser.parse_args()

    # Assuming Plugin_Objects is a class or function that reads data from the RESULT_FILE
    # and returns a list of objects called 'devices'.
    plug_objects = Plugin_Objects(RESULT_FILE)

    # Print a message to indicate that the script is starting.
    print('In script:')

    # Assuming 'values' is a dictionary or object that contains a key 'userSubnets'
    # which holds a list of user-submitted subnets.
    # Printing the userSubnets list to check its content.
    print(values.userSubnets)

    # Extract the base64-encoded subnet information from the first element of the userSubnets list.
    # The format of the element is assumed to be like 'userSubnets=b<base64-encoded-data>'.
    userSubnetsParamBase64 = values.userSubnets[0].split('userSubnets=b')[1]
    timeoutSec = values.timeoutSec[0].split('=')[1]

    # Printing the extracted base64-encoded subnet information.
    print(userSubnetsParamBase64)
    print(timeoutSec)

    # Decode the base64-encoded subnet information to get the actual subnet information in ASCII format.
    userSubnetsParam = base64.b64decode(userSubnetsParamBase64).decode('ascii')

    # Print the decoded subnet information.
    print('userSubnetsParam:')
    print(userSubnetsParam)

    # Check if the decoded subnet information contains multiple subnets separated by commas.
    # If it does, split the string into a list of individual subnets.
    # Otherwise, create a list with a single element containing the subnet information.
    if ',' in userSubnetsParam:
        subnets_list = userSubnetsParam.split(',')
    else:
        subnets_list = [userSubnetsParam]

    # Execute the ARP scanning process on the list of subnets (whether it's one or multiple subnets).
    # The function 'execute_arpscan' is assumed to be defined elsewhere in the code.
    all_entries = execute_pholus_scan(subnets_list, timeoutSec)


    for entry in all_entries:
        plug_objects.add_object(
            # "Info", "Time", "MAC", "IP_v4_or_v6", "Record_Type", "Value"
            primaryId   = entry[2],
            secondaryId = entry[3],
            watched1    = entry[0],
            watched2    = entry[4],
            watched3    = entry[5],
            watched4    = '',
            extra       = entry[0],
            foreignKey  = entry[2])

    plug_objects.write_result_file()

    return 0


def execute_pholus_scan(userSubnets, timeoutSec):
    # output of possible multiple interfaces
    arpscan_output = ""
    result_list = []

    timeoutPerSubnet = float(timeoutSec) / len(userSubnets)

    print(timeoutPerSubnet)

    # scan each interface
    
    for interface in userSubnets:           

        temp = interface.split("--interface=")

        if len(temp) != 2:
            mylog('none', ["[PholusScan] Skip scan (need interface in format '192.168.1.0/24 --inteface=eth0'), got: ", interface])
            return

        mask = temp[0].strip()
        interface = temp[1].strip()

        pholus_output_list = execute_pholus_on_interface (interface, timeoutPerSubnet, mask)        

        print(pholus_output_list)   
       

        result_list += pholus_output_list

    
    print("List len:", len(result_list))  
    print("List:", result_list)  

    return result_list

def execute_pholus_on_interface(interface, timeoutSec, mask):
    

    # logging & updating app state        
      
    mylog('none', ['[PholusScan] Scan: Pholus for ', str(timeoutSec), 's ('+ str(round(int(timeoutSec) / 60, 1)) +'min)'])  
    mylog('verbose', ["[PholusScan] Pholus scan on [interface] ", interface, " [mask] " , mask])
    
    # the scan always lasts 2x as long, so the desired user time from settings needs to be halved
    adjustedTimeout = str(round(int(timeoutSec) / 2, 0)) 

    #  python3 -m trace --trace /home/pi/pialert/pholus/pholus3.py eth1 -rdns_scanning  192.168.1.0/24 -stimeout 600
    pholus_args = ['python3', fullPholusPath, interface, "-rdns_scanning", mask, "-stimeout", adjustedTimeout]

    # Execute command
    output = ""

    try:
        # try runnning a subprocess with a forced (timeout + 30 seconds)  in case the subprocess hangs
        output = subprocess.check_output (pholus_args, universal_newlines=True,  stderr=subprocess.STDOUT, timeout=(timeoutSec + 30))
    except subprocess.CalledProcessError as e:
        # An error occured, handle it
        mylog('none', ['[PholusScan]', e.output])
        mylog('none', ["[PholusScan] Error - Pholus Scan - check logs"])            
    except subprocess.TimeoutExpired as timeErr:
        mylog('none', ['[PholusScan] Pholus TIMEOUT - the process forcefully terminated as timeout reached']) 

    if output == "": # check if the subprocess failed                    
        mylog('none', ['[PholusScan] Scan: Pholus FAIL - check logs']) 
    else: 
        mylog('verbose', ['[PholusScan] Scan: Pholus SUCCESS'])
    
    #  check the last run output
    f = open(CUR_PATH + '/pialert_pholus_lastrun.log', 'r+')
    newLines = f.read().split('\n')
    f.close()        

    # cleanup - select only lines containing a separator to filter out unnecessary data
    newLines = list(filter(lambda x: '|' in x, newLines))        
    
    # build SQL query parameters to insert into the DB
    params = []

    for line in newLines:
        columns = line.split("|")
        if len(columns) == 4:
            # "Info", "Time", "MAC", "IP_v4_or_v6", "Record_Type", "Value"
            params.append( interface + " " + mask, timeNowTZ() , columns[0].replace(" ", ""), columns[1].replace(" ", ""), columns[2].replace(" ", ""), columns[3])

    return params

#-------------------------------------------------------------------------------
def cleanResult(str):
    # alternative str.split('.')[0]
    str = str.replace("._airplay", "")
    str = str.replace("._tcp", "")
    str = str.replace(".local", "")
    str = str.replace("._esphomelib", "")
    str = str.replace("._googlecast", "")
    str = str.replace(".lan", "")
    str = str.replace(".home", "")
    str = re.sub(r'-[a-fA-F0-9]{32}', '', str)    # removing last part of e.g. Nest-Audio-ff77ff77ff77ff77ff77ff77ff77ff77
    str = re.sub(r'#.*', '', str) # Remove everything after '#' including the '#'
    # remove trailing dots
    if str.endswith('.'):
        str = str[:-1]

    return str


# Disclaimer - I'm interfacing with a script I didn't write (pholus3.py) so it's possible I'm missing types of answers
# it's also possible the pholus3.py script can be adjusted to provide a better output to interface with it
# Hit me with a PR if you know how! :)
def resolve_device_name_pholus (pMAC, pIP, allRes):
    
    pholusMatchesIndexes = []

    index = 0
    for result in allRes:
        #  limiting entries used for name resolution to the ones containing the current IP (v4 only)
        if result["MAC"] == pMAC and result["Record_Type"] == "Answer" and result["IP_v4_or_v6"] == pIP and '._googlezone' not in result["Value"]:
            # found entries with a matching MAC address, let's collect indexes             
            pholusMatchesIndexes.append(index)

        index += 1

    # return if nothing found
    if len(pholusMatchesIndexes) == 0:
        return -1

    # we have some entries let's try to select the most useful one

    # airplay matches contain a lot of information
    # Matches for example: 
    # Brand Tv (50)._airplay._tcp.local. TXT Class:32769 "acl=0 deviceid=66:66:66:66:66:66 features=0x77777,0x38BCB46 rsf=0x3 fv=p20.T-FFFFFF-03.1 flags=0x204 model=XXXX manufacturer=Brand serialNumber=XXXXXXXXXXX protovers=1.1 srcvers=777.77.77 pi=FF:FF:FF:FF:FF:FF psi=00000000-0000-0000-0000-FFFFFFFFFF gid=00000000-0000-0000-0000-FFFFFFFFFF gcgl=0 pk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and '._airplay._tcp.local. TXT Class:32769' in str(allRes[i]["Value"]) :
            return allRes[i]["Value"].split('._airplay._tcp.local. TXT Class:32769')[0]
    
    # second best - contains airplay
    # Matches for example: 
    # _airplay._tcp.local. PTR Class:IN "Brand Tv (50)._airplay._tcp.local."
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and '_airplay._tcp.local. PTR Class:IN' in allRes[i]["Value"] and ('._googlecast') not in allRes[i]["Value"]:
            return cleanResult(allRes[i]["Value"].split('"')[1])    

    # Contains PTR Class:32769
    # Matches for example: 
    # 3.1.168.192.in-addr.arpa. PTR Class:32769 "MyPc.local."
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and 'PTR Class:32769' in allRes[i]["Value"]:
            return cleanResult(allRes[i]["Value"].split('"')[1])

    # Contains AAAA Class:IN
    # Matches for example: 
    # DESKTOP-SOMEID.local. AAAA Class:IN "fe80::fe80:fe80:fe80:fe80"
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and 'AAAA Class:IN' in allRes[i]["Value"]:
            return cleanResult(allRes[i]["Value"].split('.local.')[0])

    # Contains _googlecast._tcp.local. PTR Class:IN
    # Matches for example: 
    # _googlecast._tcp.local. PTR Class:IN "Nest-Audio-ff77ff77ff77ff77ff77ff77ff77ff77._googlecast._tcp.local."
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and '_googlecast._tcp.local. PTR Class:IN' in allRes[i]["Value"] and ('Google-Cast-Group') not in allRes[i]["Value"]:
            return cleanResult(allRes[i]["Value"].split('"')[1])

    # Contains A Class:32769
    # Matches for example: 
    # Android.local. A Class:32769 "192.168.1.6"
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and ' A Class:32769' in allRes[i]["Value"]:
            return cleanResult(allRes[i]["Value"].split(' A Class:32769')[0])

    # # Contains PTR Class:IN
    # Matches for example: 
    # _esphomelib._tcp.local. PTR Class:IN "ceiling-light-1._esphomelib._tcp.local."
    for i in pholusMatchesIndexes:
        if checkIPV4(allRes[i]['IP_v4_or_v6']) and 'PTR Class:IN' in allRes[i]["Value"]:
            if allRes[i]["Value"] and len(allRes[i]["Value"].split('"')) > 1:
                return cleanResult(allRes[i]["Value"].split('"')[1])

    return -1


#===============================================================================
# BEGIN
#===============================================================================
if __name__ == '__main__':
    main()