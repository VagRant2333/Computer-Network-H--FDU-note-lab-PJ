# <center>计算机网络(H) Lab4 实验报告</center>
> **姓名：** 邱深凌
>
> **学号：** 24300240123

## 作业要求
实现 Go Back N（GBN） 和 Selective Repeat（SR）两种重传策略，以及基于丢包和基于延迟的任意两种拥塞控制算法；
完成模拟环境和真实环境测试，要求对每个测试内容获取不少于 4 组数据，以统计图的方式呈现结果
***
## 代码实现和解释
### Server.py
数据包是文件而不是上次lab的字符串，因此必须用bytes来保存
同时，为了实现类似于tcp报文头的效果，我在udp数据段的开始增加了序列号 flag ACK等等。这部分的实现方式类似于上次lab的读写报头部分（当然，端口号不太需要，毕竟能读到说明udp已经送到）

在md5中，考虑到bomb.tar比较大，需要使用分块计算

用 socketControl 处理请求命令（如上传 / 下载指令），用临时的 socketData 传输实际文件数据，避免命令与数据混杂
### Client.py


***
## 性能测试和结果
![alt text](<屏幕截图 2025-11-01 124836.png>)
 ![alt text](<屏幕截图 2025-11-01 130814.png>)
  ![alt text](<屏幕截图 2025-11-01 155902.png>) 
  ![alt text](<屏幕截图 2025-11-01 163207.png>)

***
## <center>附录</center>

### 参考资料
**socket - UDP使用参考**
https://realpython.com/python-sockets/
https://zhuanlan.zhihu.com/p/376432909
https://blog.51cto.com/u_16213402/7495842
https://www.digitalocean.com/community/tutorials/python-socket-programming-server-client
https://blog.csdn.net/sinat_20904903/article/details/132680015


**重传参考**
https://github.com/ZyangLee/Go-Back-N
https://www.tutorialspoint.com/a-protocol-using-selective-repeat
https://github.com/chetanborse007/SelectiveRepeat
https://github.com/sayalideo/SelectiveRepeat-Program

**拥塞控制参考**
https://intronetworks.cs.luc.edu/current/uhtml/newtcps.html
https://github.com/huangyt39/LFTP
https://www.xiaolincoding.com/network/3_tcp/tcp_feature.html
https://github.com/jahnabiroy/TCP-like-UDP

**其他参考**
https://www.geeksforgeeks.org/python/md5-hash-python/
https://www.cnblogs.com/xiaodekaixin/p/11203857.html
https://developer.aliyun.com/article/1598180
https://zhuanlan.zhihu.com/p/452037383
https://zhuanlan.zhihu.com/p/68466363

password = 930930