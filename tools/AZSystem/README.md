### asb_decrypt & asb_encrypt
* v1，v2，v3用于不同版本的asb解密，如果garbro解包之后看不到明文才需要decrypt
* asb是免封包的，再进行一次encrypt后放入游戏根目录即可
* v1和v3用于文件头`ASB\x1A`，v2用于非`\x1A`的某些版本

### AZsystemToolcp932
* 由`sdj123`提供，用于某个版本的asb文本提取和导入
* 和SE一样，都需要先解密，能看到明文，才能进行提取
