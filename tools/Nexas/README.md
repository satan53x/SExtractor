## pack
- unpack: file `Script.pac` to dir `Script`
- pack: dir `Script` to file `Update.pac` (Maybe `Update2` `Update3` ...)

## assemble
- disassemble: dir `Script` to dir `ASM`
- assemble: dir `ASM` to dir `ScriptNew` (Read the dir `ASM\new` first if it exists)

## Notices
#### When unpack
- `.asm` and `.dat0` files will be generated. Only need to edit the `.asm`.
- If there are additional unmatched strings, `.json` will be generated. (Only edit the text, don't modify `true/false`)

#### When assemble
if you want to auto split text with image width, you need to:
- Add param `font.ttf` in cmd `python Script_assembler_re.py [*.asm folder] [font filepath]`.
- Set `half_width = 0` in `Script_assembler.py`.
- Run `pip install pyvips` and decompress `vips-dev.7z`.

## References
- [akiWagashi/GIGA_NeXAS](https://github.com/akiWagashi/GIGA_NeXAS)
- [masagrator/NXGameScripts](https://github.com/masagrator/NXGameScripts/tree/main/Aonatsu%20Line)
