# 计网H lecture 8
## 拥塞控制
**拥塞控制 != 流量控制** congestion control vs flow control
流量控制：发送方为了防止接收方处理不过来，自己控制发送的数量。方案：发送方在ACK包中携带buffer剩余大小
拥塞控制：防止网络中间的每一跳出现拥塞
***
**拥塞情况1**
一个路由器，无限缓冲区，输入输出链路容量R
这时候，有A->B C->D，则如果两者的输入速率都达到R/2，开始排队（回忆：流量强度接近R，延迟接近正无穷，因为包到达的顺序可能混乱，而队列长度无穷大，平均等待时长无穷大）
**拥塞情况2**
如果发送方有timer，会重传
最理想的情况，是发送方可以随时得知路由器缓冲区是不是满了；也可以得知分组是不是已经丢失
但是现实中，没法实现已知丢失时再重传。这时候真正的throughput会下降。因为有（丢包所以确实需要的）重传的浪费，还有不必要重传的浪费
**拥塞情况3**
多个发送方，多跳路径，有timer
各个发送方会互相抢流量，每个路由器发送的速率有上限，使得跳数越多，竞争力越弱，吞吐量趋近于0

因此，原始输入速率并不是越高越好，整体上类似于偏高斯分布的形态

**结论：**
1. 吞吐量不可能超越容量R
2. 输入速率接近R，延迟急剧增加
3. 之后，会互相竞争，带来不必要重传，进一步降低有效吞吐量
4. 而且拥塞一旦产生，恢复会很困难
因此，不应该互相竞争或者一味增大输入速率，而是要拥塞控制

**端到端拥塞控制**，网络中的每一跳是没有反馈的；发送方/接收方要从得到的信息去推断可能的拥塞情况
**网络辅助拥塞控制**，路由器向通过拥塞路由器的流的发送/接收主机提供直接反馈（当然不是每一个包都发，这样会资源不够）；操作思路：在包头增加拥塞信息，让ACK携带拥塞信息，进行调控

e.g TCP ECN / ATM / DECbit
***
## TCP拥塞控制
课本中罗列了大量方法，但是不同的tcp实现一般只使用部分方法
*见荣誉课补充材料*
常在传输层进行拥塞控制，一般receiver flow control
**回忆：**packet主体是message 会根据payload大小（这个可以自己调配，最大值为MSS：MSS=Maximum Segment Size）分块装到`tcp segment`里，加上tcp header(20bytes)；之后到`IP packet`里，加上IP header(20bytes)；之后到`Ethernet Frame`里，加上Ethernet(14bytes)；加上校验和4bytes
如果IP Packet（即Ethernet data）超过MTU（1500bytes），会继续分包

上次：**Sliding Window**实现了多个inflight packet的停等
80s末期，开始重视QoS（quality of service）去解决拥塞控制

### 解决拥塞：高利用率，避免拥塞，保证公平

**A window** receiver **advitised** window
**C window** 发送方维护：**congestion** window

最后，我们保持滑动窗口的大小，为$W = min(cwnd, awnd)$
让源端的传输速率保持为$$\frac{W \times MSS}{RTT}$$
MSS=Maximum Segment Size
之后，$$W=BW \times RTT$$
BW为带宽；即W为网络在一个 RTT 时间内能够传输的最大数据量
这两个值都比较难以具体测算，于是需要进行预测

**TCP根据丢包的特征（losses delay marks路由器打的标签）来调整cwnd**
*具体的调整cwnd的算法有众多版本*
1. **TCP Tahoe**
   slow start，之后窗口指数级增长，到一定程度后丢包，这时候降速一半，之后再线性增加congestion avoidance。如果再发现丢包，则从头开始slow start指数增长，再线性增长，直到达到上次windows大小最大值的一半
   具体实现：每次ACK 窗口加一（这样宏观看在一个RTT中cwnd会乘以2，即为指数增长）；直到cwnd超过上次的一半达到ssthresh，进入congestion avoidance阶段，cwnd每RTT加一（即每次ACK cwnd=cwnd+1/cwnd）
   超时(timeout)或者立即重传(3个duplicate ACK)时，将ssthresh设为当前cwnd的一半，并将cwnd重置为 1，重新进入slow start
2. **TCP Reno**
   tahoe的问题在于，每次windows从1重来太保守；而且水位线ssthresh一直在变动高高低低，我们希望它稳定的高
   实际上，timeout和3 duplicate ACK两者的严重程度是不同的，timeout说明连接可能彻底断了，而duplicate ACK只说明丢了一点包
   **Reno的实现**：
   先指数增长，摸到容量的上限，之后：
   如果3 duplicate ACK，cwnd=ssthresh=0.5cwnd
   如果timeout：ssthresh=0.5cwnd，cwnd=1
   之后，维持线性增长即可
   **fast revovery** 发了1234，2丢包，一直ack1，这时cwnd=4，空中的234没有ack，则会出现“活锁”，（因为TCP`发送的数据包总量，不能超过cwnd和awnd的最小值`，这时候窗口太小，没法重传，而接收方又一直dupACK）能传包，但是要在重传2等收到ACK2，这需要很久。我们需要膨胀
   每个dupACK都代表一个数据包已成功离开管道（被接收端收到）
   因此可以：`ssthresh = max(flightsize/2, 2)`；同时重传dup ACK的包；同时$cwnd←ssthresh+n_{dup}$;现在的dup数量是3，后续若继续收到dupACK，cwnd还会继续加1
   直到non-dup ACK，则把膨胀的值放掉(deflation)，cwnd=ssthresh
3. **TCP NewReno**
   当TCP Reno遇到多个丢包时，即使重传了第一个丢的，还有大量未确认包，最后只能一个一个等，一次一次慢启动
   e.g 发1-10，收到2468，当3 dupACK收到时，重传1，sshthresh=5，cwnd膨胀到5+3=8，之后发送方一直等待，直到1被收到，结合收到的2会发送ACK2，sshthresh=5，cwnd退回5，但是未确认的包有3456..10共8个，出现问题：cwnd被占满，ACK都没有办法发过来。于是，只能等待timeout
   但是实际上冗余的ACK也是有信息的，我们什么时候推出FR(fast recovery？)（Partial ACK）：确认的数据包序号，比 “进入 FR 时已确认的序号” 大（即收到ACK2没收到ACK10），仍然不退出FR
   继续cwnd = ssthresh + PartialACK数量，继续膨胀；同时立即重传3
4. **TCP Vegas**
   之前的tahoe reno newreno都只是遇到拥塞再解决，不能预防
   vegas通过RTT变化改变窗口大小：
   传输过快：会引发拥塞，导致 RTT 增加: 减小窗口
   传输过慢：网络无拥塞，RTT 无明显增长: 增大窗口
   **三个速率相关的指标**
   Max（理想最大速率）：\( \frac{W}{RTT_{\text{min}}} \)
   \( RT T_{\text{min}} \) 是网络无拥塞时的最小 RTT(理想传输能力)
   **Real（实际速率）**：\( \frac{W}{RTT} \)
   \( RTT \) 是当前实际的往返时间，反映网络当前的负载
   **Difference（速率差，\( diff \)）**：\( diff = W \left( \frac{1}{RTT_{\text{min}}} - \frac{1}{RTT} \right) \)
   \( diff \) 越小，说明实际速率越接近理想速率（网络越空闲）；
   \( diff \) 越大，说明实际速率远低于理想速率（网络可能拥塞，RTT 增长）
   
   Vegas 定义了两个阈值 \( a \) 和 \( b \)（通常 \( a=1 \)，\( b=3 \)，可配置），根据 \( diff \) 落在的区间调整窗口：
   **\( diff < a \)**：RTT 接近 \( RT T_{\text{min}} \)，网络无拥塞  W++增大窗口
   **\( diff > b \)**：RTT 明显增长，网络可能拥塞 W-- 减小窗口
   **\( a < diff < b \)**：速率与网络容量匹配，窗口不变

### 回到TCP
回顾了tcp历史，就可以理解现在的tcp了
**拥塞控制：AIMD:additive increase/multiplicative decrease**
每个 RTT 增加 1 个最大报文段大小的发送速率，直到检测到丢包为止
每次丢包时将发送速率减半
锯齿行为：探测带宽

#### 实现细节
**乘性减细节：**
当通过三重重复 ACK 检测到丢包时，发送速率减半（TCP Reno）
当通过超时检测到丢包时，发送速率减至 1 MSS（最大报文段大小）（TCP Tahoe）
**TCP 发送行为：**
大致：发送 cwnd 字节，在接下来的 RTT 时间内等待ACK，然后发送更多字节

依旧状态机：
![alt text](assets/tcp_congest_control.png)
***
#### TCP Cubic
*linux中常用*
有没有比 AIMD 更好的 “探测 ”可用带宽的方法？
Wmax: 检测到拥塞丢包时的发送速率
瓶颈链路的拥塞状态可能没有太大变化
用k时tcp窗口大小将达到Wmax的时间点
如果时间比较长，那可以激进一点增加的快一点，由三次函数控制
即：离 K 越远，W 的增幅越大；离 K 越近，W 的增幅越小


