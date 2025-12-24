from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.mac import haddr_to_bin
from ryu.lib.packet import packet
from ryu.lib.packet import arp
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import ether_types
from ryu.lib import mac, ip
from ryu.topology import event
from collections import defaultdict


class ProjectController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ProjectController, self).__init__(*args, **kwargs)
        # 交换机 datapath 缓存，每个switch的dpid：datapath
        self.datapath_list = {}
        # 已发现的交换机 ID 列表，用作unique，避免重复添加
        self.switches = []
        # 拓扑邻接矩阵：self.adjacency[u][v] = 从 u 到 v 的出端口号
        self.adjacency = defaultdict(dict)
        # 主机 IP -> (边缘switch dpid, 主机接入端口)
        self.hosts = {
            '10.0.0.1': (1, 1), '10.0.0.2': (1, 2),
            '10.0.0.3': (2, 1), '10.0.0.4': (2, 2),
            '10.0.0.5': (3, 1), '10.0.0.6': (3, 2),
            '10.0.0.7': (4, 1), '10.0.0.8': (4, 2),
            '10.0.0.9': (5, 1), '10.0.0.10': (5, 2),
            '10.0.0.11': (6, 1), '10.0.0.12': (6, 2),
            '10.0.0.13': (7, 1), '10.0.0.14': (7, 2),
            '10.0.0.15': (8, 1), '10.0.0.16': (8, 2),
        }
        # 在这里添加你需要的数据结构
        # self.debug_src = '10.0.0.7'
        # self.debug_dsts = {'10.0.0.11', '10.0.0.12'}
        self.link_load = defaultdict(float)
        self.flow_chosen = set()
        self.print_cnt = 0



    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features_handler(self, ev):
        print("switch_features_handler is called")
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        in_dpid = datapath.id

        # 解析报文
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # 忽略 LLDP 报文，这是因为我们打开了--observe-links参数，会用LLDP来发现拓扑
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        flow_type = None
        src_ip = None
        dst_ip = None

        if eth.ethertype == ether_types.ETH_TYPE_ARP and arp_pkt:
            flow_type = 'arp'
            src_ip = arp_pkt.src_ip
            dst_ip = arp_pkt.dst_ip
        elif eth.ethertype == ether_types.ETH_TYPE_IP and ip_pkt:
            flow_type = 'ipv4'
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst
        else:
            # 只处理 ARP 与 IPv4
            return

        # 只处理映射表中已知主机
        if src_ip not in self.hosts or dst_ip not in self.hosts:
            return
                
        
        # ---------- 路径计算：计算最短路径（或者加权最短，按照你的路由策略实现） ----------
        # 在这里实现你的代码。。。。

        src_edge = self.hosts[src_ip][0]
        dst_edge = self.hosts[dst_ip][0]

        def pod_of_edge(e):
            return (e - 1) // 2

        def aggs_in_pod(pod):
            return [9 + 2 * pod, 10 + 2 * pod]

        def cores_for_agg(agg):
            return [17, 18] if (agg % 2 == 1) else [19, 20]

        def dst_agg_for_core(dst_pod, core):
            return (9 + 2 * dst_pod) if core in [17, 18] else (10 + 2 * dst_pod)

        paths = []
        if src_edge == dst_edge:
            paths = [[src_edge]]
        else:
            sp = pod_of_edge(src_edge)
            dpod = pod_of_edge(dst_edge)
            if sp == dpod:
                for agg in aggs_in_pod(sp):
                    paths.append([src_edge, agg, dst_edge])
            else:
                for agg in aggs_in_pod(sp):
                    for core in cores_for_agg(agg):
                        paths.append([src_edge, agg, core, dst_agg_for_core(dpod, core), dst_edge])

        # 检查收敛
        valid_paths = []
        for pth in paths:
            ok = True
            for i in range(len(pth) - 1):
                if pth[i + 1] not in self.adjacency[pth[i]]:
                    ok = False
                    break
            if ok:
                valid_paths.append(pth)
        if not valid_paths:
            return

        # LLR
        # LPR
        def path_cost(pth):
            if len(pth) <= 1:
                return 0.0
            mx = 0.0
            for i in range(len(pth) - 1):
                u, v = pth[i], pth[i + 1]
                mx = max(mx, self.link_load[(u, v)])
            return mx

        best = min(valid_paths, key=lambda pth: (path_cost(pth), tuple(pth)))
        path = best

        # 对新流加负载 打印
        key = (src_ip, dst_ip)
        if flow_type == 'ipv4' and key not in self.flow_chosen:
            self.flow_chosen.add(key)
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                self.link_load[(u, v)] += 1.0

            if self.print_cnt < 10:
                self.print_cnt += 1
                print(f"[LLR #{self.print_cnt}] Path for {src_ip} -> {dst_ip}: {path}")

        
        # ---------- 在你选择的路径上安装流表 ----------
        # 在这里实现你的代码。。。。注意你选择的路径上的每一个switch都要安装流表，具体你要在这里一次性全装完，还是记忆你选择的路径，分多次装都可以。
        
        # raise NotImplementedError("请在此处补全路由逻辑，完成后注释掉这行代码。")
        idle_to = 30
        hard_to = 0

        for idx, sw in enumerate(path):
            if sw not in self.datapath_list:
                continue
            dp = self.datapath_list[sw]
            p = dp.ofproto_parser

            # if idx == 0:
            #     this_in = in_port
            # else:
            #     prev_sw = path[idx - 1]
            #     this_in = self.adjacency[sw][prev_sw]
            if sw == in_dpid:
                this_in = in_port
            elif idx == 0:
                # src host -> src edge
                this_in = self.hosts[src_ip][1]
            else:
                prev_sw = path[idx - 1]
                if prev_sw not in self.adjacency[sw]:
                    continue
                this_in = self.adjacency[sw][prev_sw]

            if idx == len(path) - 1:
                out_port = self.hosts[dst_ip][1]
            else:
                next_sw = path[idx + 1]
                out_port = self.adjacency[sw][next_sw]

            actions = [p.OFPActionOutput(out_port)]

            if flow_type == 'ipv4':
                match = p.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                   in_port=this_in,
                                   ipv4_src=src_ip, ipv4_dst=dst_ip)
                self.add_flow(dp, 100, match, actions)
            else:
                match = p.OFPMatch(eth_type=ether_types.ETH_TYPE_ARP,
                                   in_port=this_in,
                                   arp_spa=src_ip, arp_tpa=dst_ip)
                self.add_flow(dp, 90, match, actions)

        # if len(path) == 1:
        #     first_out = self.hosts[dst_ip][1]
        # else:
        #     first_out = self.adjacency[in_dpid][path[1]]
        if in_dpid in path:
            cur_idx = path.index(in_dpid)
        else:
            cur_idx = 0

        if cur_idx == len(path) - 1:
            first_out = self.hosts[dst_ip][1]
        else:
            nxt = path[cur_idx + 1]
            if nxt not in self.adjacency[in_dpid]:
                return
            first_out = self.adjacency[in_dpid][nxt]

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=msg.buffer_id,
                                  in_port=in_port,
                                  actions=[parser.OFPActionOutput(first_out)],
                                  data=data)
        datapath.send_msg(out)

    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        print(ev)
        switch = ev.switch.dp
        if switch.id not in self.switches:
            self.switches.append(switch.id)
            self.datapath_list[switch.id] = switch


    @set_ev_cls(event.EventSwitchLeave, MAIN_DISPATCHER)
    def switch_leave_handler(self, ev):
        print(ev)
        switch = ev.switch.dp.id
        if switch in self.switches:
            self.switches.remove(switch)
            del self.datapath_list[switch]
            del self.adjacency[switch]


    #get adjacency matrix of fattree
    @set_ev_cls(event.EventLinkAdd, MAIN_DISPATCHER)
    def link_add_handler(self, ev):
        s1 = ev.link.src
        s2 = ev.link.dst
        self.adjacency[s1.dpid][s2.dpid] = s1.port_no
        self.adjacency[s2.dpid][s1.dpid] = s2.port_no

    @set_ev_cls(event.EventLinkDelete, MAIN_DISPATCHER)
    def link_delete_handler(self, ev):
        s1 = ev.link.src
        s2 = ev.link.dst
        # Exception handling if switch already deleted
        try:
            del self.adjacency[s1.dpid][s2.dpid]
            del self.adjacency[s2.dpid][s1.dpid]
        except KeyError:
            pass
