### 解封包
由`瑜瑜`&`Steins;Gate`提供，针对引擎`FrontWing ADV System`
* python pak_tool.py unpack <input.pak> [output_dir]
* python pak_tool.py pack   <input_dir> <output.pak>
* 测试游戏: `セパレイトブルー`, `アズラエル`

### 文本处理
* 批量提取: python csb_extract.py <input_dir> [output_dir]
* 批量导入: python csb_inject.py <orig_dir> <json_dir> [output_dir]
* 导入默认编码为`cp932`，可加参数`--encoding gbk`
