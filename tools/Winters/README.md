## pack
由`Steins;Gate`提供
* dat封包命令: python dat_pack.py 文件夹路径 输出文件.dat
* ifp封包命令: python ifp_pack.py 文件夹路径 封包.ifp

## 说明
* dat包的版本，修改后的isd不能超过原始大小，然后再对isd进行字节填充，即保持文件字节大小不变：python bytes_pad.py 1.isd 2.isd
