import os
import re

from netaddr import IPAddress
import netifaces

from netbox_agent.config import netbox_instance as nb
from netbox_agent.ethtool import Ethtool

IFACE_TYPE_100ME_FIXED = 800
IFACE_TYPE_1GE_FIXED = 1000
IFACE_TYPE_1GE_GBIC = 1050
IFACE_TYPE_1GE_SFP = 1100
IFACE_TYPE_2GE_FIXED = 1120
IFACE_TYPE_5GE_FIXED = 1130
IFACE_TYPE_10GE_FIXED = 1150
IFACE_TYPE_10GE_CX4 = 1170
IFACE_TYPE_10GE_SFP_PLUS = 1200
IFACE_TYPE_10GE_XFP = 1300
IFACE_TYPE_10GE_XENPAK = 1310
IFACE_TYPE_10GE_X2 = 1320
IFACE_TYPE_25GE_SFP28 = 1350
IFACE_TYPE_40GE_QSFP_PLUS = 1400
IFACE_TYPE_50GE_QSFP28 = 1420
IFACE_TYPE_100GE_CFP = 1500
IFACE_TYPE_100GE_CFP2 = 1510
IFACE_TYPE_100GE_CFP4 = 1520
IFACE_TYPE_100GE_CPAK = 1550
IFACE_TYPE_100GE_QSFP28 = 1600
IFACE_TYPE_200GE_CFP2 = 1650
IFACE_TYPE_200GE_QSFP56 = 1700
IFACE_TYPE_400GE_QSFP_DD = 1750
IFACE_TYPE_OTHER = 32767

# Regex to match base interface name
# Doesn't match vlan interfaces and other loopback etc
INTERFACE_REGEX = re.compile('^(eth[0-9]+|ens[0-9]+|enp[0-9]+s[0-9]f[0-9])$')


class Network():
    def __init__(self, server, *args, **kwargs):
        self.nics = []

        self.server = server
        self.scan()

    def scan(self):
        for interface in os.listdir('/sys/class/net/'):
            if re.match(INTERFACE_REGEX, interface):
                ip_addr = netifaces.ifaddresses(interface).get(netifaces.AF_INET)
                nic = {
                    'name': interface,
                    'mac': open('/sys/class/net/{}/address'.format(interface), 'r').read().strip(),
                    'ip': [
                        '{}/{}'.format(
                            x['addr'],
                            IPAddress(x['netmask']).netmask_bits()
                        ) for x in ip_addr
                        ] if ip_addr else None,  # FIXME: handle IPv6 addresses
                    'ethtool': Ethtool(interface).parse()
                }
                self.nics.append(nic)

    def get_network_cards(self):
        return self.nics

    def get_netbox_type_for_nic(self, nic):
        if nic.get('ethtool') is None:
            return IFACE_TYPE_OTHER
        if nic['ethtool']['speed'] == '10000Mb/s':
            if nic['ethtool']['port'] == 'FIBRE':
                return IFACE_TYPE_10GE_SFP_PLUS
            return IFACE_TYPE_10GE_FIXED
        elif nic['ethtool']['speed'] == '1000Mb/s':
            if nic['ethtool']['port'] == 'FIBRE':
                return IFACE_TYPE_1GE_SFP
            return IFACE_TYPE_1GE_FIXED
        return IFACE_TYPE_OTHER

    def create_netbox_nic(self, device, nic):
        # TODO: add Optic Vendor, PN and Serial
        return nb.dcim.interfaces.create(
            device=device.id,
            name=nic['name'],
            mac_address=nic['mac'],
            type=self.get_netbox_type_for_nic(nic),
        )

    def update_netbox_network_cards(self):
        device = self.server.get_netbox_server()
        for nic in self.nics:
            interface = nb.dcim.interfaces.get(
                mac_address=nic['mac'],
                )
            # if network doesn't exist we create it
            if not interface:
                new_interface = self.create_netbox_nic(device, nic)
                if nic['ip']:
                    # for each ip, we try to find it
                    # assign the device's interface to it
                    # or simply create it
                    for ip in nic['ip']:
                        netbox_ip = nb.ipam.ip_addresses.get(
                            address=ip,
                        )
                        if netbox_ip:
                            netbox_ip.interface = new_interface
                            netbox_ip.save()
                        else:
                            netbox_ip = nb.ipam.ip_addresses.create(
                                address=ip,
                                interface=new_interface.id,
                                status=1,
                            )
            # or we check if it needs update
            else:
                # FIXME: implement update
                # update name or ip
                # see https://github.com/Solvik/netbox_agent/issues/9
                pass