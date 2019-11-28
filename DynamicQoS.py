from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from pyflex import login, setLimitIops
import os
import atexit
import ssl
import sys
import logging

# Method that populates objects of type vimtype
def get_all_objs(content, vimtype):
        obj = {}
        container = content.viewManager.CreateContainerView(content.rootFolder, vimtype, True)
        for managed_object_ref in container.view:
                obj.update({managed_object_ref: managed_object_ref.name})
        return obj

# Function to retrieve 
def get_cust_value(fieldKey, custValues):
    value = ""
    for cv in custValues:
        if (cv.key == fieldKey): value = cv.value
        exit
    return value

# Function to count number of running VMs on a datastore
def get_running_tot(ds, key_guid, sdc_list, vol_id):
    count = 0
    for vm in ds:
        if (vm.runtime.powerState == 'poweredOn'):
            count = count + 1
            # Look for VxFlex SDC id
            sdc_id = get_cust_value(key_guid, vm.runtime.host.customValue)
            if (sdc_id != ""):
                # Increment counter by 1
                sdc_list[vol_id, sdc_id] = sdc_list[vol_id, sdc_id] + 1 
    return count

def main():
    # Logger for storing vCenter Alarm logs 
    vcAlarmLog = logging.getLogger('vcenter_alarms')
    vcAlarmLog.setLevel(logging.INFO)
    vcAlarmLogFile = os.path.join('/var/log', 'vcenter_alarms.log')
    formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s","%Y-%m-%d %H:%M:%S") 
    vcAlarmLogHandler = logging.FileHandler(vcAlarmLogFile)
    vcAlarmLogHandler.setFormatter(formatter)
    vcAlarmLog.addHandler(vcAlarmLogHandler)
    vcAlarmLog.propagate = False

    # Use environment variable if not passed
    if len(sys.argv) < 2:
        vm_name = os.environ.get('VMWARE_ALARM_TARGET_NAME')
        if not vm_name:
            logMsg = "VM name undefined: set $VMWARE_ALARM_TARGET_NAME or pass as argument"
            vcAlarmLog.info(logMsg)
            print(logMsg)        
            quit()
    else:
        # Retrieve VM name from command line
        vm_name = sys.argv[1]

    # Make connection to vCenter Server
    try:
        conn = SmartConnect(host=vCenter, user=userName, pwd=password)
        logMsg = "\nvCenter Connection: Valid certificate\n"
        vcAlarmLog.info(logMsg)
        print(logMsg)
    except:
        conn = SmartConnect(host=vCenter, user=userName, pwd=password, sslContext=sslCtx)
        logMsg = "\nvCenter Connection: Invalid or untrusted certificate\n"
        vcAlarmLog.info(logMsg)
        print(logMsg)

    atexit.register(Disconnect, conn)

    customFields = conn.content.customFieldsManager.field
    datacenter = conn.content.rootFolder.childEntity[0]
    vms = datacenter.vmFolder.childEntity
    content = conn.RetrieveContent()

    # Create list of machines and locate target vm
    containerView = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    vms = containerView.view
    target_vm = None
    # vm_list = {}

    # Find target VM
    for vm in vms:
        summary = vm.summary
        # vm_list[summary.config.name] = summary.config.uuid
        if (summary.vm.name == vm_name):
            target_vm = vm
            exit

    if not target_vm:
        sys.exit()

    logMsg = "Target VM: {}\n  VM Name: {}\n".format(target_vm, target_vm.config.name)
    vcAlarmLog.info(logMsg)
    print(logMsg)

    # Retreive keys for custom fields
    for aField in customFields:
        if aField.name == "VxFlexVolumeId":
            key_vol_id = aField.key
        if aField.name == "VxFlexSdcId":
            key_sdc_id = aField.key
        if aField.name == "VxFlexIopsLimit":
            key_iops_limit = aField.key

    # Create list of datastores
    # datastores = get_all_objs(content, [vim.Datastore])
    # for ds in datastores:
    #     customValues = ds.customValue
    #     print("datastore: {}. vol_id: {}".format(ds.name, get_cust_value(key_vol_id, customValues)))

    # Find target VM's datastore(s)
    datastores = target_vm.datastore
    ds_list = {}
    ds_limits = {}
    sdc_list = {}

    for ds in datastores:
        # Grab custom attributes from datastore
        customValues = ds.customValue

        # Retrieve VxFlex Volume ID associated to this datastore
        vxflex_vol_id = get_cust_value(key_vol_id, customValues)
        logMsg = "datastore: {}. vol_id: {}".format(ds.name, vxflex_vol_id)
        vcAlarmLog.info(logMsg)
        print(logMsg)

        # Check if this is a VxFlex volume
        if vxflex_vol_id != "":
            # Retrieve VxFlex IOPS limit for this datastore
            try:
                vxflex_limit = int(get_cust_value(key_iops_limit, customValues))
            except: vxflex_vol_id = 0
            ds_limits[vxflex_vol_id] = vxflex_limit

            # Create list of SDCs connected to this volume
            for host in ds.host:
                # Check if SDC GUID exists for host
                vxflex_sdc_id = get_cust_value(key_sdc_id, host.key.customValue)
                # Flag it in a multi-dimensional list with running VM counter
                if vxflex_sdc_id != "": sdc_list[vxflex_vol_id, vxflex_sdc_id] = 0

            # Determine total number of running VMs on this volume
            # Tally the running VMs per SDC while we're at it
            running_vms = get_running_tot(ds.vm, key_sdc_id, sdc_list, vxflex_vol_id)
            ds_list[vxflex_vol_id] = running_vms

    # Log into VxFlex Gateway
    token = login(vxflex_gw)

    # Set IOPS limits on VxFlex SDCs with data collected from vCenter
    volumeHeader = ""
    for sdc in sdc_list:
        # Retrieve volume, SDC, running VMs and IOPS limit details
        vxflex_vol_id = sdc[0]
        vxflex_sdc_id = sdc[1]
        total_vms = ds_list[vxflex_vol_id]
        vxflex_limit = ds_limits[vxflex_vol_id]

        if volumeHeader != vxflex_vol_id:
            logMsg = "\nVolume ID: {}. Limit: {:,}. Running VMs: {:,}".format(vxflex_vol_id, vxflex_limit, total_vms)
            vcAlarmLog.info(logMsg)
            print(logMsg)
            volumeHeader = vxflex_vol_id

        # Carve up limits for each SDC (proportional to number of VMs)
        num_vms = sdc_list[vxflex_vol_id, vxflex_sdc_id]
        sdc_limit = int(vxflex_limit * (num_vms / total_vms))
        logMsg = "   SDC ID: {}. Running VMs: {:,}. SET Limit to: {:,}".format(vxflex_sdc_id, num_vms, sdc_limit)
        vcAlarmLog.info(logMsg)
        print(logMsg)

        # Set the IOP
        setLimitIops(vxflex_gw, token, vxflex_vol_id, vxflex_sdc_id, sdc_limit)

    logMsg = "\nVxFlex IOPS Limits set on {}\n".format(vxflex_gw)
    vcAlarmLog.info(logMsg)
    print(logMsg)

# VxFlex connection details
vxflex_user = "<user>"
vxflex_pwd = "<pwd>"
## The IP address of the Flex Gateway
vxflex_gw = "<vxflex_gateway>"

# vCenter connection details
vCenter = "<vcenter_server>"
dc = "Datacenter"
userName = "<user>"
password = "<pwd>"

sslCtx = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
sslCtx.verify_mode = ssl.CERT_NONE

# Start program
if __name__ == "__main__":
    main()