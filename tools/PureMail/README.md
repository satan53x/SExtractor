### dat_repack
由`Steins;Gate`提供
* 解包: Garbro: https://github.com/satan53x/GARbro/releases/tag/diff-v5
* 封包: python dat_repack.py <原始.dat> <obj文件目录> [输出.dat]

### obj_processor
默认原始obj文件所在目录为`script`，可通过`-i script`参数调整
* 提取: python obj_processor.py extract
* 导入: python obj_processor.py rebuild

### 说明
* dat和obj都有不同的版本，但是dat的version与obj的version不是绑定关系。
* 如果dat是V2，则需使用上述的改版Garbro才能正常解包。（当Garbro左下角显示V2时，封包也需要使用`dat_repack_v2.py`）
