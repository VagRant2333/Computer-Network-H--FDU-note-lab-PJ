from mininet.topo import Topo
from functools import partial
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
import time


def int_to_hex(i):
    if (i > 255 or i < 0):
        return "00"
    else:
        return hex(i)[2:4]


class SingleNode(Topo):
    def __init__(self):
        Topo.__init__(self)

        self.addSwitch("s1")

        for i in range(16):
            self.addHost("h" + str(i+1),
                         mac='00:00:00:00:00:'+int_to_hex(i+1))
            self.addLink("h" + str(i+1), "s1")


class FatTree(Topo):
    def __init__(self):
        "Create custom topo."

        # Initialize topology
        Topo.__init__(self)

        # Edge switch and hosts
        for i in range(1, 9):
            self.addSwitch("s" + str(i))
            self.addHost("h" + str(i*2-1),
                         mac='00:00:00:00:00:'+int_to_hex(i*2-1))
            self.addHost("h" + str(i*2),
                         mac='00:00:00:00:00:'+int_to_hex(i*2))
            self.addLink("h" + str(i*2-1), "s" + str(i))
            self.addLink("h" + str(i*2), "s" + str(i))

         # Core switch
        for i in range(17, 21):
            self.addSwitch("s" + str(i))

        # Agg switch
        for i in range(9, 17): #9-16
            self.addSwitch("s" + str(i))

            if (i % 2 == 0):
                self.addLink("s"+str(i), "s"+str(i-9))  # edge to agg
                self.addLink("s"+str(i), "s"+str(i-8))  # edge to agg

                core_id = 19

                self.addLink("s"+str(i), "s"+str(core_id))  # agg to core

                core_id = core_id + 1

                self.addLink("s"+str(i), "s"+str(core_id))  # agg to core
            else:
                self.addLink("s"+str(i), "s"+str(i-8))  # edge to agg
                self.addLink("s"+str(i), "s"+str(i-7))  # edge to agg

                core_id = 17 

                self.addLink("s"+str(i), "s"+str(core_id))  # agg to core

                core_id = core_id + 1

                self.addLink("s"+str(i), "s"+str(core_id))  # agg to core



def create_topo():
    topo = FatTree()
    #topo = SingleNode()
    net = Mininet(topo=topo, controller=partial(RemoteController,
                                               ip='127.0.0.1',
                                               port=6633))
    net.start()

    dumpNodeConnections(net.hosts)

    return net


def start_iperf_server(net):
    for i in range(16):
        server = net.get('h' + str(i+1))

        for j in range(8):  # eight flows
            server.cmd('iperf -s -u -p ' + str(5000+j) + ' &')

    print ("iperf servers started")


def start_client_sequential(net):
    print ("client starting")
    for i in range(16):
        client = net.get('h' + str(i+1))

        server_id = i+5
        if (server_id > 16):
            server_id = server_id - 16
        server_ip = '10.0.0.' + str(server_id)

        for j in range(4):
            client.cmd('iperf -c ' + server_ip + ' -u -p ' + str(5000+j) +
                       ' -b 1M -t 650 &')
            time.sleep(1)

        server_id = i+6
        if (server_id > 16):
            server_id = server_id - 16
        server_ip = '10.0.0.' + str(server_id)

        for j in range(4, 8):
            client.cmd('iperf -c ' + server_ip + ' -u -p ' + str(5000+j) +
                       ' -b 1M -t 650 &')
            time.sleep(1)

    print ("all iperf clients started")


if __name__ == '__main__':
    setLogLevel('info')
    net = create_topo()
    # CLI(net) 你可以在这里打开mininet的命令行界面，进行调试

    start_iperf_server(net)
    time.sleep(10)

    start_client_sequential(net)

    time.sleep(100)
    

    for i in range(16):
        client = net.get('h' + str(i+1))
        client.cmd("pkill iperf")

    net.stop()
