""" Colection of generic functions to support NetAlertX """

import io
import sys
import datetime
import os
import re
import unicodedata
import subprocess
import pytz
from pytz import timezone
import json
import time
from pathlib import Path
import requests
import base64
import hashlib
import random
import string
import ipaddress
import dns.resolver

import conf
from const import *
from logger import mylog, logResult

# Register NetAlertX directories
INSTALL_PATH="/app"

#-------------------------------------------------------------------------------
# DateTime
#-------------------------------------------------------------------------------
# Get the current time in the current TimeZone
def timeNowTZ():
    if conf.tz:
        return datetime.datetime.now(conf.tz).replace(microsecond=0)
    else:
        return datetime.datetime.now().replace(microsecond=0)
    # if isinstance(conf.TIMEZONE, str):
    #     tz = pytz.timezone(conf.TIMEZONE)
    # else:
    #     tz = conf.TIMEZONE

    # return datetime.datetime.now(tz).replace(microsecond=0)

def timeNow():
    return datetime.datetime.now().replace(microsecond=0)

def get_timezone_offset():    
    now = datetime.datetime.now(conf.tz)
    offset_hours = now.utcoffset().total_seconds() / 3600        
    offset_formatted =  "{:+03d}:{:02d}".format(int(offset_hours), int((offset_hours % 1) * 60))
    return offset_formatted


#-------------------------------------------------------------------------------
def updateSubnets(scan_subnets):
    subnets = []

    # multiple interfaces
    if type(scan_subnets) is list:
        for interface in scan_subnets :
            subnets.append(interface)
    # one interface only
    else:
        subnets.append(scan_subnets)

    return subnets



#-------------------------------------------------------------------------------
# File system permission handling
#-------------------------------------------------------------------------------
# check RW access of DB and config file
def checkPermissionsOK():
    #global confR_access, confW_access, dbR_access, dbW_access

    confR_access = (os.access(fullConfPath, os.R_OK))
    confW_access = (os.access(fullConfPath, os.W_OK))
    dbR_access = (os.access(fullDbPath, os.R_OK))
    dbW_access = (os.access(fullDbPath, os.W_OK))

    mylog('none', ['\n'])
    mylog('none', ['The backend restarted (started). If this is unexpected check https://bit.ly/NetAlertX_debug for troubleshooting tips.'])
    mylog('none', ['\n'])
    mylog('none', ['Permissions check (All should be True)'])
    mylog('none', ['------------------------------------------------'])
    mylog('none', [ "  " , confPath ,     " | " , " READ  | " , confR_access])
    mylog('none', [ "  " , confPath ,     " | " , " WRITE | " , confW_access])
    mylog('none', [ "  " , dbPath , "       | " , " READ  | " , dbR_access])
    mylog('none', [ "  " , dbPath , "       | " , " WRITE | " , dbW_access])
    mylog('none', ['------------------------------------------------'])

    #return dbR_access and dbW_access and confR_access and confW_access
    return (confR_access, dbR_access)
#-------------------------------------------------------------------------------
def fixPermissions():
    # Try fixing access rights if needed
    chmodCommands = []

    chmodCommands.append(['sudo', 'chmod', 'a+rw', '-R', fullDbPath])
    chmodCommands.append(['sudo', 'chmod', 'a+rw', '-R', fullConfPath])

    for com in chmodCommands:
        # Execute command
        mylog('none', ["[Setup] Attempting to fix permissions."])
        try:
            # try runnning a subprocess
            result = subprocess.check_output (com, universal_newlines=True)
        except subprocess.CalledProcessError as e:
            # An error occured, handle it
            mylog('none', ["[Setup] Fix Failed. Execute this command manually inside of the container: ", ' '.join(com)])
            mylog('none', [e.output])


#-------------------------------------------------------------------------------
def initialiseFile(pathToCheck, defaultFile):
    # if file not readable (missing?) try to copy over the backed-up (default) one
    if str(os.access(pathToCheck, os.R_OK)) == "False":
        mylog('none', ["[Setup] ("+ pathToCheck +") file is not readable or missing. Trying to copy over the default one."])
        try:
            # try runnning a subprocess
            p = subprocess.Popen(["cp", defaultFile , pathToCheck], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            stdout, stderr = p.communicate()

            if str(os.access(pathToCheck, os.R_OK)) == "False":
                mylog('none', ["[Setup] ⚠ ERROR copying ("+defaultFile+") to ("+pathToCheck+"). Make sure the app has Read & Write access to the parent directory."])
            else:
                mylog('none', ["[Setup] ("+defaultFile+") copied over successfully to ("+pathToCheck+")."])

            # write stdout and stderr into .log files for debugging if needed
            logResult (stdout, stderr)  # TO-DO should be changed to mylog

        except subprocess.CalledProcessError as e:
            # An error occured, handle it
            mylog('none', ["[Setup] ⚠ ERROR copying ("+defaultFile+"). Make sure the app has Read & Write access to " + pathToCheck])
            mylog('none', [e.output])

#-------------------------------------------------------------------------------
def filePermissions():
    # check and initialize .conf
    (confR_access, dbR_access) = checkPermissionsOK() # Initial check

    if confR_access == False:
        initialiseFile(fullConfPath, f"{INSTALL_PATH}/back/app.conf" )

    # check and initialize .db
    if dbR_access == False:
        initialiseFile(fullDbPath, f"{INSTALL_PATH}/back/app.db")

    # last attempt
    fixPermissions()


#-------------------------------------------------------------------------------
# File manipulation methods
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
def get_file_content(path):

    f = open(path, 'r')
    content = f.read()
    f.close()

    return content

#-------------------------------------------------------------------------------
def write_file(pPath, pText):
    # Convert pText to a string if it's a dictionary
    if isinstance(pText, dict):
        pText = json.dumps(pText)

    # Convert pText to a string if it's a list
    if isinstance(pText, list):
        for item in pText:
            write_file(pPath, item)

    else:
        # Write the text using the correct Python version
        if sys.version_info < (3, 0):
            file = io.open(pPath, mode='w', encoding='utf-8')
            file.write(pText.decode('unicode_escape'))
            file.close()
        else:
            file = open(pPath, 'w', encoding='utf-8')
            if pText is None:
                pText = ""
            file.write(pText)
            file.close()

#-------------------------------------------------------------------------------
# Setting methods
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
#  Return whole setting touple
def get_setting(key):

    settingsFile = apiPath + 'table_settings.json'

    try:
        with open(settingsFile, 'r') as json_file:

            data = json.load(json_file)

            for item in data.get("data",[]):
                if item.get("setKey") == key:
                    return item

            mylog('debug', [f'[Settings] ⚠ ERROR - setting_missing - Setting not found for key: {key} in file {settingsFile}'])  

            return None

    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        # Handle the case when the file is not found, JSON decoding fails, or data is not in the expected format
        mylog('none', [f'[Settings] ⚠ ERROR - JSONDecodeError or FileNotFoundError for file {settingsFile}'])                

        return None



#-------------------------------------------------------------------------------
# Settings
#-------------------------------------------------------------------------------

#-------------------------------------------------------------------------------
#  Return setting value
def get_setting_value(key):

    # Returns empty string if not set
    value = ''
    
    setting = get_setting(key)

    if setting is not None:

        # mylog('none', [f'[SETTINGS] setting json:{json.dumps(setting)}'])        

        set_type  = 'Error: Not handled'
        set_value = 'Error: Not handled'

        set_value = setting["setValue"]  # Setting value (Value (upper case) = user overridden default_value)
        set_type = setting["setType"]  # Setting type  # lower case "type" - default json value vs uppper-case "setType" (= from user defined settings)

        value = setting_value_to_python_type(set_type, set_value)

    return value

#-------------------------------------------------------------------------------
#  Convert the setting value to the corresponding python type


def setting_value_to_python_type(set_type, set_value):
    value = '----not processed----'

    # "type": {"dataType":"array", "elements": [{"elementType" : "select", "elementOptions" : [{"multiple":"true"}] ,"transformers": []}]}
 
    setTypJSN = json.loads(str(set_type).replace('"','\"').replace("'",'"'))

    # Handle different types of settings based on set_type dictionary
    dataType = setTypJSN.get('dataType', '')
    elements = setTypJSN.get('elements', [])

    # Ensure there's at least one element in the elements list
    if not elements:
        mylog('none', [f'[HELPER] No elements provided in set_type: {set_type} '])
        return value

    # Find the first element where elementHasInputValue is 1
    element_with_input_value = next((elem for elem in elements if elem.get("elementHasInputValue") == 1), None)

    # If no such element is found, use the last element
    if element_with_input_value is None:
        element_with_input_value = elements[-1]
        
    elementType     = element_with_input_value.get('elementType', '')
    elementOptions  = element_with_input_value.get('elementOptions', [])
    transformers    = element_with_input_value.get('transformers', [])

    # Convert value based on dataType and elementType
    if dataType == 'string' and elementType in ['input', 'select', 'textarea', 'datatable']:
        value = reverseTransformers(str(set_value), transformers)

    elif dataType == 'integer' and (elementType == 'input' or elementType == 'select'):    
        # handle storing/retrieving boolean values as 1/0
        if set_value.lower() not in ['true', 'false'] and isinstance(set_value, str):
            value = int(set_value)

        elif isinstance(set_value, bool):
            value = 1 if set_value else 0

        elif isinstance(set_value, str): 
            value = 1 if set_value.lower() == 'true' else 0
            
        else: 
            value = int(set_value)

    # boolean handling 
    elif dataType == 'boolean' and elementType == 'input':
        value = set_value.lower() in ['true', '1']

    # array handling
    elif dataType == 'array' and elementType == 'select':
        if isinstance(set_value, str):
            try:
                value = json.loads(set_value.replace("'", "\""))
                
                # reverse transformations to all entries
                value = reverseTransformers(value, transformers)
                    
            except json.JSONDecodeError as e:
                mylog('none', [f'[setting_value_to_python_type] Error decoding JSON object: {e}'])  
                mylog('none', [set_value])  
                value = []
                
        elif isinstance(set_value, list):
            value = set_value

    elif dataType == 'object' and elementType == 'input':
        if isinstance(set_value, str):
            try:
                value = reverseTransformers(json.loads(set_value), transformers)
            except json.JSONDecodeError as e:                
                mylog('none', [f'[setting_value_to_python_type] Error decoding JSON object: {e}'])  
                mylog('none', [{set_value}])  
                value = {}
                
        elif isinstance(set_value, dict):
            value = set_value

    elif dataType == 'string' and elementType == 'input' and any(opt.get('readonly') == "true" for opt in elementOptions):
        value = reverseTransformers(str(set_value), transformers)

    elif dataType == 'string' and elementType == 'input' and any(opt.get('type') == "password" for opt in elementOptions) and 'sha256' in transformers:
        value = hashlib.sha256(set_value.encode()).hexdigest()


    if value == '----not processed----':
        mylog('none', [f'[HELPER] ⚠ ERROR not processed set_type:  {set_type} '])  
        mylog('none', [f'[HELPER] ⚠ ERROR not processed set_value: {set_value} '])  

    return value

#-------------------------------------------------------------------------------
# Reverse transformed values if needed
def reverseTransformers(val, transformers):
    # Function to apply transformers to a single value
    def reverse_transformers(value, transformers):
        for transformer in transformers:
            if transformer == 'base64':
                if isinstance(value, str):
                    value = base64.b64decode(value).decode('utf-8')
            elif transformer == 'sha256':
                mylog('none', [f'[reverseTransformers] sha256 is irreversible'])
        return value

    # Check if the value is a list
    if isinstance(val, list):
        return [reverse_transformers(item, transformers) for item in val]
    else:
        return reverse_transformers(val, transformers)

#-------------------------------------------------------------------------------
# Generate a WHERE condition for SQLite based on a list of values.
def list_to_where(logical_operator, column_name, condition_operator, values_list):
    """
    Generate a WHERE condition for SQLite based on a list of values.

    Parameters:
    - logical_operator: The logical operator ('AND' or 'OR') to combine conditions.
    - column_name: The name of the column to filter on.
    - condition_operator: The condition operator ('LIKE', 'NOT LIKE', '=', '!=', etc.).
    - values_list: A list of values to be included in the condition.

    Returns:
    - A string representing the WHERE condition.
    """

    # If the list is empty, return an empty string
    if not values_list:
        return ""

    # Replace {s-quote} with single quote in values_list
    values_list = [value.replace("{s-quote}", "'") for value in values_list]

    # Build the WHERE condition for the first value
    condition = f"{column_name} {condition_operator} '{values_list[0]}'"

    # Add the rest of the values using the logical operator
    for value in values_list[1:]:
        condition += f" {logical_operator} {column_name} {condition_operator} '{value}'"

    return f'({condition})'





#-------------------------------------------------------------------------------
# IP validation methods
#-------------------------------------------------------------------------------
#-------------------------------------------------------------------------------
def checkIPV4(ip):
    """ Define a function to validate an Ip address
    """
    ipRegex = r"^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$"

    if(re.search(ipRegex, ip)):
        return True
    else:
        return False

#-------------------------------------------------------------------------------
def check_IP_format (pIP):
    # check if TCP communication error ocurred 
    if 'communications error to' in pIP:
        return ''

    # Check IP format 
    IPv4SEG  = r'(?:25[0-5]|(?:2[0-4]|1{0,1}[0-9]){0,1}[0-9])'
    IPv4ADDR = r'(?:(?:' + IPv4SEG + r'\.){3,3}' + IPv4SEG + r')'
    IP = re.search(IPv4ADDR, pIP)

    # Return empty if not IP
    if IP is None :
        return ""

    # Return IP
    return IP.group(0)

#-------------------------------------------------------------------------------
# String manipulation methods
#-------------------------------------------------------------------------------


#-------------------------------------------------------------------------------

def bytes_to_string(value):
    # if value is of type bytes, convert to string
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    return value

#-------------------------------------------------------------------------------

def if_byte_then_to_str(input):
    if isinstance(input, bytes):
        input = input.decode('utf-8')
        input = bytes_to_string(re.sub(r'[^a-zA-Z0-9-_\s]', '', str(input)))
    return input

#-------------------------------------------------------------------------------
def hide_email(email):
    m = email.split('@')

    if len(m) == 2:
        return f'{m[0][0]}{"*"*(len(m[0])-2)}{m[0][-1] if len(m[0]) > 1 else ""}@{m[1]}'

    return email

#-------------------------------------------------------------------------------
def hide_string(input_string):
    if len(input_string) < 3:
        return input_string  # Strings with 2 or fewer characters remain unchanged
    else:
        return input_string[0] + "*" * (len(input_string) - 2) + input_string[-1]


#-------------------------------------------------------------------------------
def removeDuplicateNewLines(text):
    if "\n\n\n" in text:
        return removeDuplicateNewLines(text.replace("\n\n\n", "\n\n"))
    else:
        return text

#-------------------------------------------------------------------------------

def sanitize_string(input):
    if isinstance(input, bytes):
        input = input.decode('utf-8')
    input = bytes_to_string(re.sub(r'[^a-zA-Z0-9-_\s]', '', str(input)))
    return input


#-------------------------------------------------------------------------------
def sanitize_SQL_input(val):
    if val is None:
        return ''
    if isinstance(val, str):
        return val.replace("'", "_")
    return val  # Return non-string values as they are


#-------------------------------------------------------------------------------
# Function to normalize the string and remove diacritics
def normalize_string(text):
    # Normalize the text to 'NFD' to separate base characters and diacritics
    if not isinstance(text, str):
        text = str(text)
    normalized_text = unicodedata.normalize('NFD', text)
    # Filter out diacritics and unwanted characters
    return ''.join(c for c in normalized_text if unicodedata.category(c) != 'Mn')


#-------------------------------------------------------------------------------
def generate_mac_links (html, deviceUrl):

    p = re.compile(r'(?:[0-9a-fA-F]:?){12}')

    MACs = re.findall(p, html)

    for mac in MACs:
        html = html.replace('<td>' + mac + '</td>','<td><a href="' + deviceUrl + mac + '">' + mac + '</a></td>')

    return html

#-------------------------------------------------------------------------------
def extract_between_strings(text, start, end):
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index != -1 and end_index != -1:
        return text[start_index + len(start):end_index]
    else:
        return ""

#-------------------------------------------------------------------------------
def extract_mac_addresses(text):
    mac_pattern = r"([0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2}[:-][0-9A-Fa-f]{2})"
    mac_addresses = re.findall(mac_pattern, text)
    return mac_addresses

#-------------------------------------------------------------------------------
def extract_ip_addresses(text):
    ip_pattern = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
    ip_addresses = re.findall(ip_pattern, text)
    return ip_addresses

#-------------------------------------------------------------------------------
def generate_random_string(length):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


# Helper function to determine if a MAC address is random
def is_random_mac(mac):
    # Check if second character matches "2", "6", "A", "E" (case insensitive)
    is_random = mac[1].upper() in ["2", "6", "A", "E"]

    # Check against user-defined non-random MAC prefixes
    if is_random:
        not_random_prefixes = get_setting_value("UI_NOT_RANDOM_MAC")
        for prefix in not_random_prefixes:
            if mac.startswith(prefix):
                is_random = False
                break
    return is_random

# Helper function to calculate number of children
def get_number_of_children(mac, devices):
    # Count children by checking devParentMAC for each device
    return sum(1 for dev in devices if dev.get("devParentMAC", "").strip() == mac.strip())



# Function to convert IP to a long integer
def format_ip_long(ip_address):
    try:
        # Check if it's an IPv6 address
        if ':' in ip_address:
            ip = ipaddress.IPv6Address(ip_address)
        else:
            # Assume it's an IPv4 address
            ip = ipaddress.IPv4Address(ip_address)
        return int(ip)
    except ValueError:
        # Return a default error value if IP is invalid
        return -1

#-------------------------------------------------------------------------------
# JSON methods
#-------------------------------------------------------------------------------

#-------------------------------------------------------------------------------
def isJsonObject(value):
    return isinstance(value, dict)

#-------------------------------------------------------------------------------
def add_json_list (row, list):
    new_row = []
    for column in row :
        column = bytes_to_string(column)

        new_row.append(column)

    list.append(new_row)

    return list



#-------------------------------------------------------------------------------
# Checks if the object has a __dict__ attribute. If it does, it assumes that it's an instance of a class and serializes its attributes dynamically. 
class NotiStrucEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            # If the object has a '__dict__', assume it's an instance of a class
            return obj.__dict__
        return super().default(obj)

#-------------------------------------------------------------------------------
#  Creates a JSON object from a DB row
def row_to_json(names, row):

    rowEntry = {}

    index = 0
    for name in names:
        rowEntry[name]= if_byte_then_to_str(row[name])
        index += 1

    return rowEntry

#-------------------------------------------------------------------------------
# Get language strings from plugin JSON
def collect_lang_strings(json, pref, stringSqlParams):    

    for prop in json["localized"]:
        for language_string in json[prop]:

            stringSqlParams.append((str(language_string["language_code"]), str(pref + "_" + prop), str(language_string["string"]), ""))


    return stringSqlParams

#-------------------------------------------------------------------------------
#  Misc
#-------------------------------------------------------------------------------

# -------------------------------------------------------------------------------------------
def format_date(date_str: str) -> str:
    """Format a date string as 'YYYY-MM-DD   HH:MM'"""
    dt = datetime.datetime.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    return dt.strftime('%Y-%m-%d   %H:%M')

# -------------------------------------------------------------------------------------------
def format_date_diff(date1: str, date2: str) -> str:
    """Return difference between two dates formatted as 'Xd   HH:MM'"""
    dt1 = datetime.datetime.fromisoformat(date1) if isinstance(date1, str) else date1
    dt2 = datetime.datetime.fromisoformat(date2) if isinstance(date2, str) else date2
    delta = dt2 - dt1

    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60

    return f"{days}d   {hours:02}:{minutes:02}"

# -------------------------------------------------------------------------------------------
def format_date_iso(date1: str) -> str:
    """Return ISO 8601 string for a date"""
    dt = datetime.datetime.fromisoformat(date1) if isinstance(date1, str) else date1
    return dt.isoformat()

# -------------------------------------------------------------------------------------------    
def is_random_mac(mac: str) -> bool:
    """Determine if a MAC address is random, respecting user-defined prefixes not to mark as random."""

    is_random = mac[1].upper() in ["2", "6", "A", "E"]

    # Get prefixes from settings
    prefixes = get_setting_value("UI_NOT_RANDOM_MAC")  

    # If detected as random, make sure it doesn't start with a prefix the user wants to exclude
    if is_random:
        for prefix in prefixes:
            if mac.upper().startswith(prefix.upper()):
                is_random = False
                break

    return is_random


# -------------------------------------------------------------------------------------------   
def get_date_from_period(period):
    """
    Convert a period request parameter into an SQLite date expression.
    Equivalent to PHP getDateFromPeriod().
    Returns a string like "date('now', '-7 day')"
    """    
    days_map = {
        '7 days': 7,
        '1 month': 30,
        '1 year': 365,
        '100 years': 3650,  # actually 10 years in original PHP
    }

    days = days_map.get(period, 1)  # default 1 day
    period_sql = f"date('now', '-{days} day')"

    return period_sql

#-------------------------------------------------------------------------------
def print_table_schema(db, table):
    sql = db.sql
    sql.execute(f"PRAGMA table_info({table})")
    result = sql.fetchall()

    if not result:
        mylog('none', f'[Schema] Table "{table}" not found or has no columns.')
        return

    mylog('debug', f'[Schema] Structure for table: {table}')
    header = f"{'cid':<4} {'name':<20} {'type':<10} {'notnull':<8} {'default':<10} {'pk':<2}"
    mylog('debug', header)
    mylog('debug', '-' * len(header))

    for row in result:
        # row = (cid, name, type, notnull, dflt_value, pk)
        line = f"{row[0]:<4} {row[1]:<20} {row[2]:<10} {row[3]:<8} {str(row[4]):<10} {row[5]:<2}"
        mylog('debug', line)


#-------------------------------------------------------------------------------
def checkNewVersion():
    mylog('debug', [f"[Version check] Checking if new version available"])

    newVersion = False

    with open(applicationPath + '/front/buildtimestamp.txt', 'r') as f:
        buildTimestamp = int(f.read().strip())

    try:
        response = requests.get(
            "https://api.github.com/repos/jokob-sk/NetAlertX/releases",
            timeout=5
        )
        response.raise_for_status()  # Raise an exception for HTTP errors
        text = response.text
    except requests.exceptions.RequestException as e:
        mylog('minimal', ["[Version check] ⚠ ERROR: Couldn't check for new release."])
        return False

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        mylog('minimal', ["[Version check] ⚠ ERROR: Invalid JSON response from GitHub."])
        return False

    # make sure we received a valid response and not an API rate limit exceeded message
    if data and isinstance(data, list) and "published_at" in data[0]:
        dateTimeStr = data[0]["published_at"]
        releaseTimestamp = int(datetime.datetime.strptime(dateTimeStr, '%Y-%m-%dT%H:%M:%S%z').timestamp())

        if releaseTimestamp > buildTimestamp + 600:
            mylog('none', ["[Version check] New version of the container available!"])
            newVersion = True
        else:
            mylog('none', ["[Version check] Running the latest version."])
    else:
        mylog('minimal', ["[Version check] ⚠ ERROR: Received unexpected response from GitHub."])

    return newVersion



#-------------------------------------------------------------------------------
def initOrSetParam(db, parID, parValue):
    sql = db.sql

    sql.execute ("INSERT INTO Parameters(par_ID, par_Value) VALUES('"+str(parID)+"', '"+str(parValue)+"') ON CONFLICT(par_ID) DO UPDATE SET par_Value='"+str(parValue)+"' where par_ID='"+str(parID)+"'")

    db.commitDB()

#-------------------------------------------------------------------------------
class json_obj:
    def __init__(self, jsn, columnNames):
        self.json = jsn
        self.columnNames = columnNames

#-------------------------------------------------------------------------------
class noti_obj:
    def __init__(self, json, text, html):
        self.json = json
        self.text = text
        self.html = html  

