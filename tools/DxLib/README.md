#
原项目地址：https://github.com/regomne/chinesize/tree/master/DxLib/exBin
#
* 作者调用的DxLib官方开源库，但是我编译的时候图片绘制函数有报错，就注释掉了，应该不会影响解包。
* 只有解包功能，测试的这个游戏把bin包删除掉就是免封包。
#
* 测试游戏：`黒愛HD`
* bin版本头部签名：`DX\x08\x00`
* 解包命令：`exDxBin.exe -e -dxarc KuroaiHD_dl.bin -o KuroaiHD_dl -key _ppiixxeell_`
* 密钥搜索：`pix.xml`配置是明文，键`datafolder`的值是包名（无后缀），ida反编译exe搜索`datafolder`向上调用跳转两次，就看到了函数内的密钥字符串`_ppiixxeell_`。
（密钥附近也有字节流`bin`可以作为搜索依据）
