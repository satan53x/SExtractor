## 说明
* 密钥文件`database.json`的内容取自`Garbro`。
* 目前支持`cfi`和`camellia`加密。
* 原包内的对齐填充并不是00，但尚不清楚生成方式，故封包时都写00，请自行测试。
* `ExpectHeader`设置为原始包的第`0x10~0x18`字节数据，则会自动检测可能的加密。
* 如果想指定游戏名`GameType`请把`ExpectHeader`设置为空。
