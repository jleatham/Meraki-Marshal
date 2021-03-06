READ_ME = '''
=== PREREQUISITES ===
Run in Python 3.6 or Later

Install requests and Meraki Dashboard API Python modules:
pip[3] install requests [--upgrade]
pip[3] install meraki [--upgrade]

=== DESCRIPTION ===
This script finds all MR access points in an organization, and then iterates
through all networks to obtain the Air Marshall information of the APs.

For questions, contact Josh at jleatham@cisco.com.
Shout out to Jeffry Handal as well. 

=== USAGE ===
python3 marshal.py parameters.ini

parameters.ini should include:
[access]
key = 1234|YOUR-APIKEY|5678
org = 12|ORGID|34

=== OUTPUT ===
marshal_log...csv   #shows all API calls and errors
rogue...csv         #final report, formatted, time stamped
temp_rogue...csv    # in case timeouts or errors, csv will include what it can.  Is deleted on 
                    # successful completion of rogue..csv file
'''


import configparser
import csv
import os
import sys
from datetime import datetime
#import getopt
import logging
from meraki import meraki
import requests
import time
import pandas as pd






#change the format from pandas to_csv -> to csvwriter
#this will allow for easier writing to CSV during the iteration, as opposed to
#writing the CSV file all at once, which is error prone
def main(api_key, org_id):
    # Get the org's inventory
    inventory = meraki.getorginventory(api_key, org_id, suppressprint=True)
    # Filter for only MR devices
    aps = [device for device in inventory if device['model'][:2] in ('MR') and device['networkId'] is not None]
    #networkList needed later on for mapping Device to Network ID
    networkList = []
    for ap in aps:
        networkList.append([ap['serial'],ap['networkId']])
    #used to concat all the dataframes (rows for CSVs)
    frames = []


    logger.info('Preparing the output file. Check your local directory.')
    timenow = '{:%Y%m%d_%H%M%S}'.format(datetime.now())
    filename = 'rogues_{0}.csv'.format(timenow)
    #####Added CSV writer so that CSV file would write while performing API iteration
    ##### Helps for when there are unexpected crashes or timeouts, we can still have some data
    temp_filename = 'temp_rogues_{0}.csv'.format(timenow)
    output_file = open(temp_filename, mode='w', newline='\n')
    field_names = ['SSID','Channels','Device SN','Network ID','First Seen','Last Seen','Plugged in Time']
    csv_writer = csv.DictWriter(output_file, fieldnames=field_names, restval='')
    csv_writer.writeheader()
    ###### End CSV init
    n = 1000  #used to print screen every n rogue ID found
    x = 0
    


    for ap in aps:
        #iterate through all network IDs and store each temporarily in roguedata
        try:
            #print(str(ap))
            roguedata = meraki.getairmarshal(api_key, ap['networkId'], 3600, suppressprint=True)
            #go through each rogue SSID per Network ID
            for rogue in roguedata:
                if 'ssid' in rogue: #skip if no data

                    ssidName  = data_value(rogue, 'ssid')
                    channels  = data_value(rogue, 'channels')
                    deviceSN  = data_value2(rogue, 'bssids','detectedBy','device')
                    networkID = get_network_id(networkList,data_value2(rogue, 'bssids','detectedBy','device'))
                    firstSeen = data_value(rogue, 'firstSeen')
                    lastSeen  = data_value(rogue, 'lastSeen')
                    wiredLast = data_value(rogue, 'wiredLastSeen')
                    
                    #Write CSV data row by row
                    data={'SSID':ssidName,'Channels':channels,'Device SN':deviceSN,'Network ID':networkID,'First Seen':firstSeen,'Last Seen':lastSeen,'Plugged in Time':wiredLast}
                    csv_writer.writerow(data)
                    #output to screen every n iterations of CSV lines
                    if x % n == 0:
                        logger.info("Processing Rogue SSIDs.  Count = {0}".format(str(x)))
                        #print("Processing Rogue SSIDs.  Count = "+str(x))
                x += 1


        except Exception as e:
            print (e)
            logger.error("Problem with AP:   {0}".format(str(ap)))
            #print("\nProblem with AP: \n"+ str(ap))
    
    
    
    output_file.close() #close out temp_rogue file
    #print("Adding Network names to CSV file")
    logger.info("Adding Network names to CSV file")
    master_df = pd.read_csv(temp_filename)   #reopen temp csv and import to pandas for processing
    master_df = add_network_name(master_df,api_key)  #get network name associated to each AP ID
    master_df = convert_dates(master_df)    #format DateTime to be consistent and readable
    #reorder CSV data
    master_df = master_df[['Network Name','SSID','Channels','Device SN','Network ID','First Seen','Last Seen','Plugged in Time']]
    master_df = master_df.reset_index(drop=True) #drop dataframe index
    master_df = master_df.sort_values(['Network Name'])  #sort CSV by network name
    master_df.to_csv(filename,index=False)  #write to final rogue CSV file
    #remove temp CSV file because final report was generated
    if os.path.exists(temp_filename):
        os.remove(temp_filename)
    else:
        #print("The file does not exist") 
        logger.error("The temp CSV file does not exist")   




# Prints READ_ME help message for user to read
def print_help():
    lines = READ_ME.split('\n')
    for line in lines:
        print('# {0}'.format(line))



def configure_logging():
    logger = logging.getLogger(__name__)
    logging.basicConfig(
        filename='{}_log_{:%Y%m%d_%H%M%S}.txt'.format(sys.argv[0].split('.')[0], datetime.now()),
        level=logging.DEBUG,
        format='%(asctime)s: %(levelname)7s: [%(name)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # Set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    # Tell the handler to use this format
    console.setFormatter(formatter)
    # Add the handler to the root logger
    logging.getLogger('').addHandler(console)  
    return logger

def read_config():

    inputs = sys.argv[1:]
    if len(inputs) == 0:
        print_help()
        sys.exit(2)
    file = inputs[0]

    cp = configparser.ConfigParser()
    try:
        cp.read(file)
        api_key = cp.get('access', 'key')
        org_id = cp.get('access', 'org')
    except:
        print_help()
        sys.exit(2)
    return api_key, org_id



def data_value(dictionary, key):
    try:
        return dictionary[key]
    except Exception as e:
        print(e)
        return ''

#not a good way to do this, several other ways, this is hard coded as a shortcut
#bssids is a nested json value, the data just happens to always be flat(1 entry), so
#we can point to it using hard coded pointers [0] for first nested json entry
def data_value2(dictionary, key1,key2,key3):
    try:
        return dictionary[key1][0][key2][0][key3]
    except Exception as e:
        print(e)
        return ''

#network list is a map of device SN to associated network
#if device SN is found, return associated network ID
def get_network_id(networkList,device):
    for i in networkList:
        if device in i[0]:
            return i[1]


def add_network_name(df,api_key):

    networkIdList = []
    networkIdList.extend(df['Network ID'].tolist()) #take all NetworkIDs from dataframe column and turn into a list
    networkIdList = set(networkIdList) #remove duplicates
    networkNameList = []
    #create a nested list of [network id, network names]
    for id in networkIdList:
        network = meraki.getnetworkdetail(api_key, id,suppressprint=True)
        if 'name' in network:
            networkNameList.append([id,network['name']])

    #loop through all rows of data
    #for each row, loop through and check all network ids
    #when network id(network[0]) is identified, add to a new column the associated network name
    for i in df.index:
        for network in networkNameList:
            if network[0] in df.ix[i,'Network ID']:
                df.ix[i,'Network Name'] = network[1]
                break
    return df

def convert_dates(df):
    #converts meraki API dates(in seconds format) into a datetime stamp
    df['First Seen'] = pd.to_datetime(df['First Seen'],unit='s')
    df['Last Seen'] = pd.to_datetime(df['Last Seen'],unit='s')
    #remove 0's from data, otherwise it will mess with datatimestamp
    for i in df.index:
        if df.ix[i,'Plugged in Time'] == 0:
            df.ix[i,'Plugged in Time'] = ''    
    df['Plugged in Time'] = pd.to_datetime(df['Plugged in Time'],unit='s')

    return df



  



if __name__ == '__main__':
    start_time = datetime.now()
    start = int(time.time())
    # Configure logging to stdout
    logger = configure_logging()
    # Output to logfile/console starting inputs  
    logger.info('Started script at {0}'.format(start_time))

    #parse input file.
    api_key, org_id = read_config()

    #Execute the program
    main(api_key, org_id)


    # Finish output to logfile/console
    end_time = datetime.now()
    end = int(time.time())
    logger.info('Ended script at {0}'.format(end_time))
    d = divmod(end - start,86400)  # days
    h = divmod(d[1],3600)  # hours
    m = divmod(h[1],60)  # minutes
    s = m[1]  # seconds
    logger.info('Total run time = {0} minutes , {1} seconds'.format(m[0],s))
