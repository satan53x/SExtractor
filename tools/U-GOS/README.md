### unpack & pack
由`Cosetto`提供，详见[issue](https://github.com/satan53x/SExtractor/issues/127)
* 引擎为`μ-GameOpertionSystem`，社团为`M de Pink`
* 解包: python det_tool.py -u <archive_base_name> <output_folder>
* 封包: python det_tool.py -p <input_folder> <archive_base_name>

### extract & import
由`朝比奈真冬`提供批量
* 提取文本: python o_tool.py export <input.o> <output.json>
* 导入文本: python o_tool.py import <input.o> <translated.json> <output.o>
* 批量提取: python o_tool.py export-dir <in_folder> <out_json_folder>
* 批量导入: python o_tool.py import-dir <in_folder> <trans_json_folder> <out_folder>
