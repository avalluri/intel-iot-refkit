#!/usr/bin/env python

import dbus
import dbus.service 
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import sys, getopt
import threading as t

DBusGMainLoop(set_as_default=True)
conn = dbus.SystemBus()

DBUS_PROPERTIES_IFCE = "org.freedesktop.DBus.Properties"
DBUS_OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
NEARD_SERVICE = "org.neard"

outdir = "/var/lib/connman"


class WifiCredentials:
    def __init__(self):
        self.SSID = ''
        self.Secret = ''
        self.AuthType = ''
        self.EncodeType = ''
        self.X509Cert = ''
        self.Network = 0

class WSCParser:
    KEY_INVALD = 0
    AUTH_TYPE     = 0x1003
    CREDENTIAL    = 0x100e
    ENC_TYPE      = 0x100f
    PASS_ID       = 0x1012
    MAC_ADDR      = 0x1020
    NETWORK_IDX   = 0x1026
    KEY           = 0x1027
    SSID          = 0x1045
    VENDOR_EXTENSION = 0x1048
    VERSION       = 0x104a
    X509_CERT     = 0x104c

    auth_types = { 
        '0x01': 'None',
        '0x02': 'WPA-Private',
        '0x04': 'WEP-64',
        '0x08': 'WEP-Enterprise',
        '0x10': 'WPA2-Enterprise',
        '0x20': 'WPA2-Private',
        '0x22': 'WPA/WPA2-Private'
    }

    encode_type = ['None', 'WEP', 'TKIP', 'AEC'] 

    temp_cred = {
        'SSID': 'test_ssid',
        'Key': 'Secret'
    }

    def __init__(self, data):
        self._data = data
        self._cred = WSCParser.temp_cred

    def cred(self):
        return self._cred

    def decode_(self, data):
        i = 0
        size = len(data)
 
        while(i < size):
            if size - i < 4:
                print("ERROR: broken WSC data: not enough room for header")
                return False
            # parse 4 byte header: 2 bytes id, 2 bytes length
            id = data[i] * 256 + data[i+1]
            length = data[i+2] * 256 + data[i+3]
            i += 4
            if length < 1:
                print("ERROR: broken WSC data; length < 1B")
                return False
            if size - i < length:
                print("ERROR: not enough room for Value")
                return False
            print("ID: " + hex(id))
 
            if id == WSCParser.SSID:
                self._cred['SSID'] = "".join(map(chr, data[i:i+length]))
            elif id == WSCParser.KEY:
                self._cred['Key'] = "".join(map(chr, data[i:i+length]))
            elif id == WSCParser.X509_CERT:
                self._cred['X509Cert'] = "".join(map(chr, data[i:i+length]))
            elif id == WSCParser.AUTH_TYPE:
                if length != 2:
                    print("ERROR: Found Auth_type but len(%d) != 2" % length)
                    return False
                type = str(hex(data[i] * 256 + data[i+1]))
                if not WSCParser.auth_types.has_key(type):
                    print("ERROR: unknown auth type : %d" % type)
                    return False
                self._cred['AuthType'] = WSCParser.auth_types[type]
            elif id == WSCParser.ENC_TYPE:
                if length != 2:
                    print("ERROR: broken WSC data - Encode length(%d) != 2" % length)
                    return False
                encode = data[i] * 256 + data[i+1]
                if encode > len(WSCParser.encode_type):
                    print("ERROR: Unknwon encode type: %d" % encode)
                self._cred['Encode'] = WSCParser.encode_type[encode]
            elif id == WSCParser.NETWORK_IDX:
                if length != 1:
                    print("ERROR: broken WSC data - Netowrk IDX length(%d) != 1B" % length)
                    return False
                self._cred['Network'] = int(data[i])
            elif id == WSCParser.CREDENTIAL:
                if self.decode_(data[i:i+length]) == False:
                    return False
            elif id == WSCParser.MAC_ADDR:
                mac = []
                for e in bytearray(data[i:i+length]):
                    mac.append(str(e))
                self._cred['MAC'] = ":".join(mac)
            else:
                print("Uhandled ID: " + hex(id) + "length: " + length)
 
            i += length

        return True

    def parse(self):
        return self.decode_(self._data)

    def writeToConnman(self):
        g = """
[global]
Name=Wifi configuration
Description=Auto configured by neard-wifi-agent"""
        s = """
[service_wifi]
Type=wifi
IPv4=dhcp
IPv6=auto
Name=%s
Passphrase=%s
Security=%s"""
        file_name = outdir + "/wifi_" + self._cred['SSID'] + "_service"
        print("Wrting wifi configuration to: %s" % file_name)
        with open(file_name, 'w+') as f:
            f.write(g)
            f.write(s % (self._cred['SSID'], self._cred['Key'], self._cred['AuthType']))
            f.close()

 

class Agent(dbus.service.Object):
    PATH = '/org/refkit/neard'
    def __init__(self):
        bus_name = dbus.service.BusName('org.refkit.neard', dbus.SystemBus())
        dbus.service.Object.__init__(self, bus_name, Agent.PATH)

    @dbus.service.method('org.neard.HandoverAgent', in_signature='a{sv}',
                    out_signature='a{sv}')
    def RequestOOB(self, values):
        print("RequestOOB :%s" % values)

    @dbus.service.method('org.neard.HandoverAgent', in_signature='a{sv}')
    def PushOOB(self, data):
        if data.has_key('WSC'):
            print("PushOOB: Found WSC data")
            p = WSCParser(data['WSC'])
            p.parse()
            print("Found Credentials: %s" % str(p.cred()))
            p.writeToConnman()
        else:
            print("PushOOB: Unknown record : %s" % data)

    @dbus.service.method('org.neard.HandoverAgent')
    def Release(self):
        print("Release")

    @dbus.service.method("org.neard.NDEFAgent", in_signature='a{sv}')
    def GetNDEF(self, values):
        print("GetNDEF: %s" % str(values))
    
    @dbus.service.method("org.neard.NDEFAgent")
    def Release(self):
        print("Release")

class Adapter:
    IFACE = NEARD_SERVICE + '.Adapter'
    PollModeDual = 'Dual'
    PollModeTarget = 'Target'
    PollModeInitiator = 'Initiator'
    #
    # Signal Handlers
    #
    def onPropertiesChanged(self, iface, changed, invalidated):
        if iface != Adapter.IFACE:
            return
        
        for name, value in changed.iteritems():
            self.properties[name] = value
            print("Adapter property '%s' changed to '%s'" %(name, value)) 
            if name == 'Powered':
                if not value: self.setPowered(True)
            elif name == 'Mode' and value == 'Idle':
                t.Timer(2, self.activate).start()
                return

        for name in invalidated:
            del self.properties[name]

    def __init__(self, object_path, properties):
    
        self.object_path = object_path
        self.properties = properties
        self.proxy = conn.get_object(NEARD_SERVICE, object_path)
        self.adapter = dbus.Interface(self.proxy, Adapter.IFACE)
        self.prop_iface = dbus.Interface(self.proxy, DBUS_PROPERTIES_IFCE)

        self.prop_iface.connect_to_signal('PropertiesChanged', self.onPropertiesChanged)

    def activate(self):
        self.setPowered(True)
        self.startPollLoop(Adapter.PollModeDual)

    def powered(self):
        return self.properties['Powered']

    def setPowered(self, state):
        if self.properties['Powered'] != state:
            self.prop_iface.Set(Adapter.IFACE, 'Powered', dbus.Boolean(state, variant_level=1))

    def startPollLoop(self, mode):
        #if mode != self.properties['Mode'] and
        if  not self.properties['Polling']:
            print("Polling...")
            self.adapter.StartPollLoop(mode)

    def stopPolling(self):
        print("StopPolling: " + self.object_path)
        if self.properties['Polling']:
            self.adapter.StopPollLoop()

class Manager:
    NEARD_SERVICE = "org.neard"
    IFACE = NEARD_SERVICE + '.Manager'
    AGENTMANAGER_IFACE = NEARD_SERVICE + ".AgentManager"
    DEVICE_IFACE = NEARD_SERVICE + ".Device"
    #
    # Signal handlers
    #
    def onInterfacesAdded(self, object_path, interfaces):
        print("%s: " % object_path)
        for name, prop in interfaces.iteritems():
            print("   + %s" % name)
            if name == Adapter.IFACE :
                self.addAdapter(object_path, prop)
            elif name == Manager.AGENTMANAGER_IFACE:
                self.registerAgents(object_path)
            elif name == Manager.DEVICE_IFACE:
                self.addDevice(object_path, prop)

    def onInterfacesRemoved(self, object_path, interfaces):
        print("%s: " % object_path)
        for iface in interfaces:
            print("   - %s" % iface)
            if iface == Adapter.IFACE:
                print("Adapter removed : %s", object_path)
                del self.adapters[object_path]
 
    def __init__(self):
        self.adapters =  {}
        try:
            self.rootObj = conn.get_object(NEARD_SERVICE, '/')
            self.neardObj = conn.get_object(NEARD_SERVICE, '/org/neard')
            self.manager = dbus.Interface(self.rootObj, Manager.IFACE)
            self.obj_manager = dbus.Interface(self.rootObj, DBUS_OBJECT_MANAGER_IFACE)
            self.agent_manager = None
            self.agent = None
 
            objects =  self.obj_manager.GetManagedObjects()
            if objects :
                for object_path, interfaces in objects.iteritems():
                    self.onInterfacesAdded(object_path, interfaces)

            self.obj_manager.connect_to_signal('InterfacesAdded', self.onInterfacesAdded)
            self.obj_manager.connect_to_signal('InterfacesRemoved', self.onInterfacesRemoved)

            #conn.request_name('org.refkit.neard')
        except dbus.DBusException, e:
            print(__name__, e)
            return

    def addAdapter(self, object_path, props):
        adapter = Adapter(object_path, props)
        self.adapters[object_path] = adapter
        adapter.activate()
    
    def addDevice(self, object_path, prop):
        print("Found Device %s : %s" % (object_path, prop))
    
    def registerAgents(self, agent_manager_path):
        proxy = conn.get_object(NEARD_SERVICE, agent_manager_path)
        self.agent_manager = dbus.Interface(proxy, Manager.AGENTMANAGER_IFACE)
        if self.agent_manager:
            self.agent = Agent()
            self.agent_manager.RegisterHandoverAgent(Agent.PATH, 'wifi')
            self.agent_manager.RegisterNDEFAgent(Agent.PATH, 'Text')
    
    def unregisterAgents(self):
        print("Unregistring agents...")
        if self.agent_manager:
            self.agent_manager.UnregisterHandoverAgent(Agent.PATH, 'wifi')
            self.agent_manager.UnregisterNDEFAgent(Agent.PATH, 'Text')
        del self.agent

    def quit(self):
        self.unregisterAgents() 
        for key in self.adapters:
            self.adapters[key].stopPolling()
#        conn.release_name('org.refkit.neard')

    def __del__(self):
        self.quit()
        del self.adapters
        del self.manager

def Usage():
    print 'Usage: ' + sys.argv[0] + '-h  [-o outdir]'
    sys.exit(2)

def main(argv):
    global outdir
    try:
        opts, args = getopt.getopt(argv, "ho:", ["outdir="])
    except getopt.GetoptError:
        Usage()

    print("opts=%s, args=%s" % (opts, args))

    for opt, arg in opts:
        if opt == '-h':
            Usage()
        elif opt in ('-o', '--outdir'):
            outdir = arg

    try:
        s = Manager()
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        s.quit()
        GLib.MainLoop().quit()
 
    return 0

if __name__ == "__main__":
        main(sys.argv[1:])
