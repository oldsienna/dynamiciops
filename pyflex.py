import requests
import json
from requests.packages import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

## Credentials
username = "<username>"
password = "<pwd>"
## Enable/disable debug mode
debug = 0
## The IP address of the Flex cluster
target = "<vxlfex_gateway>"

def login(target):
    """ Give me the IP of the Flex GW and I you a token """

    uri = "/api/login"
    url = "https://" + target + uri

    req = requests.get(url, auth=(username, password), verify=False)
    if req.status_code != 200:
        raise Exception('ERROR: {}'.format(req.content))
    token = req.text.strip('"')

    if debug:
        print("Token =",token)
        print(type(token))
    
    return token


def getAllVolsQOS(target, token):
    """ Full list of vols. Each vol contains 'limitIops' for each mapped SDC """
    
    uri = "/api/types/Volume/instances"
    url = "https://" + target + uri
    req = requests.get(url, auth=(username, token), verify=False)

    if req.status_code != 200:
        raise Exception('ERROR: {}'.format(req.content))
    req_json = json.loads(req.content)
    outlist = []
    for each_vol in req_json:
        vol = {}
        ## We will keep only these 3 fields
        vol['name'] = each_vol['name']
        vol['id'] = each_vol['id']
        vol['sdc'] = each_vol['mappedSdcInfo']
        if vol['sdc']:
        ## From the SDC list we only keep sdcId and limitIops
            for each_sdc in vol['sdc']:
                del each_sdc['limitBwInMbps']
                del each_sdc['sdcIp']
            outlist.append(vol)

    if debug:
        print(str(outlist))
    
    return outlist

def getVolsWithNoLimitIops(target, token):
    """ Get list of vols with where any SDC has 'limitIops' = 0 """
    
    uri = "/api/types/Volume/instances"
    url = "https://" + target + uri
    req = requests.get(url, auth=(username, token), verify=False)
    if req.status_code != 200:
        raise Exception('ERROR: {}'.format(req.content))
    req_json = json.loads(req.content)
    outlist = []
    for each_vol in req_json:
        vol = {}
        sdcList = []
        ## Build a list of sdcId with limitIops = 0
        if each_vol['mappedSdcInfo']:
            for each_sdc in each_vol['mappedSdcInfo']:
                if each_sdc['limitIops'] == 0:
                    sdcList.append(each_sdc['sdcId'])
        
        ## Do this only if we found any SDC with limitIops = 0, ie if the sdcList is not empty
        if sdcList:
            #vol['name'] = each_vol['name']
            vol['id'] = each_vol['id']
            vol['sdc'] = sdcList
            outlist.append(vol)

    if debug:
        print(str(outlist))
    
    return outlist

def setLimitIops(target, token, volumeId, sdcId, iops):
    """Sets the limitIops that one SDC generates for a specified volume"""

    uri = "/api/instances/Volume::" + volumeId + "/action/setMappedSdcLimits"
    url = "https://" + target + uri
    
    data = '{"sdcId": "' + str(sdcId) + '", "iopsLimit":"' + str(iops) + '"}'
    if debug:
        print(data)
    req = requests.post(url, auth=(username, token), json=json.loads(data), headers={'Content-type': 'application/json'}, verify=False)
    if req.status_code != 200:
        raise Exception('ERROR: {}'.format(req.content))
    req_json = json.loads(req.content)
    return req_json

def createVol(target, token, name, size, storagePool):
    """Let's create a volume given a name, size and SP"""
    
    uri = "/api/types/Volume/instances"
    url = "https://" + target + uri
    data = '{"volumeSizeInGb": "' + str(size) + '", "storagePoolId": "' + storagePool + '", "name": "' + name + '"}'
    if debug:
        print(data)
    req = requests.post(url, auth=(username, token), json=json.loads(data), headers={'Content-type': 'application/json'}, verify=False)
    if req.status_code != 200:
        raise Exception('ERROR: {}'.format(req.content))
    req_json = json.loads(req.content)
    if debug:
        print(req_json)
    
    return req_json['id']

def mapVolToSdc(target, token, volumeId, sdcId):
    """ Maps a Volume to an SDC"""

    uri = "/api/instances/Volume::" + volumeId + "/action/addMappedSdc"
    url = "https://" + target + uri
    
    data = '{"sdcId": "' + str(sdcId) + '", "allowMultipleMappings":"TRUE"}'
    if debug:
        print(data)
    req = requests.post(url, auth=(username, token), json=json.loads(data), headers={'Content-type': 'application/json'}, verify=False)
    if req.status_code != 200:
        raise Exception('ERROR: {}'.format(req.content))
    req_json = json.loads(req.content)
    return req_json

def prettyJson(ugly_dict):
    print(json.dumps(ugly_dict, indent=4, sort_keys=True))
    return

def main():
    token = login(target)
    AllVols = getAllVolsQOS(target, token)
    for vol in AllVols:
        print("\n** Volume ID: {}. Name: {} **".format(vol["id"], vol["name"]))
        for sdc in vol["sdc"]:
            print("  SDC ID: {}. Limit: {}".format(sdc["sdcId"], sdc["limitIops"]))
    print("\n")
    #prettyJson(AllVols)

    # NoQoSVols = getVolsWithNoLimitIops(target, token)
    # prettyJson(NoQoSVols)
    # #volid = createVol(target, token, "albvol2", "1", "7285739d00000001")
    # #print volid
    # #res = mapVolToSdc(target, token, volid, "af2bf1c500000002")
    # #res = mapVolToSdc(target, token, "02a82f1c00000004", "af2bf1c300000000")
    # #res = setLimitIops(target, token, "02a82f1c00000004", "af2bf1c300000000", 1000)
    # #print res

# Start program
if __name__ == "__main__":
    main()