using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

/// <summary>
/// ArkEngine scripts.bin / scripts.idx packer
///
/// Critical game requirement (DataEncrypt.DecryptBinFile out string):
///   AES-decrypt(payload) MUST be MessagePack-encoded UTF-8 string,
///   then ObjectPacker.Unpack&lt;string&gt;().
/// Packing raw text without the MsgPack wrapper freezes boot.
/// </summary>
static class ScriptsPackTool
{
    static readonly byte[] EncryptKey = Encoding.UTF8.GetBytes("c6eahbq9sjuawhvdr9kvhpsm5qv393ga");
    static readonly byte[] PackIv = Encoding.UTF8.GetBytes("ARC-PACKPASSWORD");
    const string DefaultPrefix = "/scripts/";

    static int Main(string[] args)
    {
        if (args.Length == 0 || args[0] is "-h" or "--help" or "/?")
        {
            PrintHelp();
            return args.Length == 0 ? 1 : 0;
        }
        try
        {
            return args[0].ToLowerInvariant() switch
            {
                "pack" => CmdPack(args.Skip(1).ToArray()),
                "unpack" => CmdUnpack(args.Skip(1).ToArray()),
                "list" => CmdList(args.Skip(1).ToArray()),
                "verify" => CmdVerify(args.Skip(1).ToArray()),
                "selftest" => CmdSelfTest(),
                _ => Fail("Unknown command: " + args[0])
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("ERROR: " + ex.Message);
            Console.Error.WriteLine(ex);
            return 2;
        }
    }

    static void PrintHelp()
    {
        Console.WriteLine(@"scripts_pack_tool - ArkEngine scripts.bin + scripts.idx

Commands:
  unpack <bin> <idx> <out_dir>           # decrypt + unwrap MsgPack -> editable .snr text
  pack   <input_dir> <out_bin> <out_idx> [--prefix /scripts/] [--recursive]
                                         # wrap text as MsgPack string, AES, rebuild idx
  list   <bin> <idx>
  verify <bin> <idx>                     # round-trip original archive byte-identical
  selftest

Important:
  Game calls DecryptBinFile(..., out string) which does AES then MsgPack.Unpack<string>.
  So bin payload = AES( MessagePack(string) ), NOT AES(raw text).
");
    }

    static int Fail(string msg)
    {
        Console.Error.WriteLine(msg);
        PrintHelp();
        return 1;
    }

    // ---------------- AES ----------------
    static byte[] AesEncrypt(byte[] plain)
    {
        using var aes = Aes.Create();
        aes.Key = EncryptKey;
        aes.IV = PackIv;
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.PKCS7;
        using var enc = aes.CreateEncryptor();
        return enc.TransformFinalBlock(plain, 0, plain.Length);
    }

    static byte[] AesDecrypt(byte[] cipher)
    {
        using var aes = Aes.Create();
        aes.Key = EncryptKey;
        aes.IV = PackIv;
        aes.Mode = CipherMode.CBC;
        aes.Padding = PaddingMode.PKCS7;
        using var dec = aes.CreateDecryptor();
        return dec.TransformFinalBlock(cipher, 0, cipher.Length);
    }

    // ---------------- MessagePack string (MsgPackWriter.Write(string)) ----------------
    static byte[] MsgPackEncodeString(string text)
    {
        byte[] utf8 = Encoding.UTF8.GetBytes(text);
        using var ms = new MemoryStream(3 + utf8.Length);
        WriteRawHeader(ms, utf8.Length);
        ms.Write(utf8, 0, utf8.Length);
        return ms.ToArray();
    }

    static string MsgPackDecodeString(byte[] data)
    {
        int p = 0;
        // skip trailing zeros from game-style buffers if present
        int end = data.Length;
        // don't trim before parse; parser only consumes string payload
        if (p >= end) throw new InvalidDataException("empty msgpack string");
        int id = data[p++];
        int len;
        if (id >= 0xA0 && id <= 0xBF) len = id & 0x1F;
        else if (id == 0xD9) len = data[p++];
        else if (id == 0xDA) { len = (data[p] << 8) | data[p + 1]; p += 2; }
        else if (id == 0xDB) { len = (data[p] << 24) | (data[p + 1] << 16) | (data[p + 2] << 8) | data[p + 3]; p += 4; }
        else throw new InvalidDataException($"not a msgpack string tag 0x{id:X2}");
        if (p + len > data.Length) throw new InvalidDataException("truncated msgpack string");
        return Encoding.UTF8.GetString(data, p, len);
    }

    static bool LooksLikeMsgPackString(byte[] data)
    {
        if (data == null || data.Length == 0) return false;
        int id = data[0];
        try
        {
            if (id >= 0xA0 && id <= 0xBF)
            {
                int len = id & 0x1F;
                return 1 + len <= data.Length;
            }
            if (id == 0xD9 && data.Length >= 2)
            {
                int len = data[1];
                return 2 + len <= data.Length;
            }
            if (id == 0xDA && data.Length >= 3)
            {
                int len = (data[1] << 8) | data[2];
                return 3 + len <= data.Length;
            }
            if (id == 0xDB && data.Length >= 5)
            {
                int len = (data[1] << 24) | (data[2] << 16) | (data[3] << 8) | data[4];
                return 5 + len <= data.Length;
            }
        }
        catch { }
        return false;
    }

    /// <summary>
    /// Prepare AES plaintext for a bin entry from a file on disk.
    /// - If file already starts with MsgPack string header (raw payload from old unpackers), keep as-is.
    /// - Otherwise treat file as editable UTF-8 text and wrap with MsgPack string.
    /// </summary>
    static byte[] PrepareBinPlain(byte[] fileBytes)
    {
        if (LooksLikeMsgPackString(fileBytes))
            return fileBytes;
        // UTF-8 text (allow BOM)
        string text;
        if (fileBytes.Length >= 3 && fileBytes[0] == 0xEF && fileBytes[1] == 0xBB && fileBytes[2] == 0xBF)
            text = Encoding.UTF8.GetString(fileBytes, 3, fileBytes.Length - 3);
        else
            text = Encoding.UTF8.GetString(fileBytes);
        return MsgPackEncodeString(text);
    }

    static void WriteRawHeader(Stream s, int n)
    {
        if (n < 32) s.WriteByte((byte)(0xA0 | n));
        else if (n < 65536)
        {
            s.WriteByte(0xDA);
            s.WriteByte((byte)(n >> 8));
            s.WriteByte((byte)n);
        }
        else
        {
            s.WriteByte(0xDB);
            s.WriteByte((byte)(n >> 24));
            s.WriteByte((byte)(n >> 16));
            s.WriteByte((byte)(n >> 8));
            s.WriteByte((byte)n);
        }
    }

    static void WriteMpString(Stream s, string value)
    {
        byte[] utf8 = Encoding.UTF8.GetBytes(value);
        WriteRawHeader(s, utf8.Length);
        s.Write(utf8, 0, utf8.Length);
    }

    static void WriteMpInt(Stream s, int x)
    {
        // MsgPackWriter.Write(int) -> short -> sbyte
        if (x >= short.MinValue && x <= short.MaxValue) { WriteMpShort(s, (short)x); return; }
        s.WriteByte(0xD2);
        s.WriteByte((byte)(x >> 24));
        s.WriteByte((byte)(x >> 16));
        s.WriteByte((byte)(x >> 8));
        s.WriteByte((byte)x);
    }

    static void WriteMpShort(Stream s, short x)
    {
        if (x >= sbyte.MinValue && x <= sbyte.MaxValue) { WriteMpSByte(s, (sbyte)x); return; }
        s.WriteByte(0xD1);
        s.WriteByte((byte)(x >> 8));
        s.WriteByte((byte)x);
    }

    static void WriteMpSByte(Stream s, sbyte x)
    {
        if (x >= -32 && x <= -1) { s.WriteByte((byte)(0xE0 | (byte)x)); return; }
        if (x >= 0) { s.WriteByte((byte)x); return; }
        s.WriteByte(0xD0);
        s.WriteByte((byte)x);
    }

    static byte[] PackInfoMsgPack(string fileName, int size, int index)
    {
        using var ms = new MemoryStream();
        ms.WriteByte(0x83);
        WriteMpString(ms, "fileName");
        WriteMpString(ms, fileName);
        WriteMpString(ms, "size");
        WriteMpInt(ms, size);
        WriteMpString(ms, "index");
        WriteMpInt(ms, index);
        return ms.ToArray();
    }

    static Dictionary<string, object> ReadMsgPackMap(byte[] data)
    {
        int p = 0;
        int id = data[p++];
        if (id < 0x80 || id > 0x8F) throw new InvalidDataException($"not fixmap 0x{id:X2}");
        int count = id & 0xF;
        var map = new Dictionary<string, object>(count);
        for (int i = 0; i < count; i++)
        {
            string key = ReadMpString(data, ref p);
            map[key] = ReadMpValue(data, ref p);
        }
        return map;
    }

    static string ReadMpString(byte[] data, ref int p)
    {
        int id = data[p++];
        int len;
        if (id >= 0xA0 && id <= 0xBF) len = id & 0x1F;
        else if (id == 0xD9) len = data[p++];
        else if (id == 0xDA) { len = (data[p] << 8) | data[p + 1]; p += 2; }
        else if (id == 0xDB) { len = (data[p] << 24) | (data[p + 1] << 16) | (data[p + 2] << 8) | data[p + 3]; p += 4; }
        else throw new InvalidDataException($"str tag 0x{id:X2}");
        string s = Encoding.UTF8.GetString(data, p, len);
        p += len;
        return s;
    }

    static object ReadMpValue(byte[] data, ref int p)
    {
        int id = data[p++];
        if (id >= 0 && id < 0x80) return id;
        if (id >= 0xE0 && id <= 0xFF) return (sbyte)id;
        if (id >= 0xA0 && id <= 0xBF) { p--; return ReadMpString(data, ref p); }
        switch (id)
        {
            case 0xD0: return (sbyte)data[p++];
            case 0xD1:
                {
                    short v = (short)((data[p] << 8) | data[p + 1]); p += 2; return (int)v;
                }
            case 0xD2:
                {
                    int v = (data[p] << 24) | (data[p + 1] << 16) | (data[p + 2] << 8) | data[p + 3]; p += 4; return v;
                }
            case 0xCC: return data[p++];
            case 0xCD:
                {
                    int v = (data[p] << 8) | data[p + 1]; p += 2; return v;
                }
            case 0xCE:
                {
                    int v = (data[p] << 24) | (data[p + 1] << 16) | (data[p + 2] << 8) | data[p + 3]; p += 4; return v;
                }
            case 0xD9:
            case 0xDA:
            case 0xDB:
                p--; return ReadMpString(data, ref p);
            default:
                throw new InvalidDataException($"val tag 0x{id:X2}");
        }
    }

    // ---------------- idx/bin IO ----------------
    readonly record struct IdxEntry(string FileName, int Size, int Index);

    static List<IdxEntry> ReadIdx(string idxPath)
    {
        var list = new List<IdxEntry>();
        byte[] data = File.ReadAllBytes(idxPath);
        int p = 0;
        while (p < data.Length)
        {
            int len = BitConverter.ToInt32(data, p); p += 4;
            if (len <= 0 || p + len > data.Length) throw new InvalidDataException($"bad idx len {len} at {p - 4}");
            byte[] plain = AesDecrypt(data.AsSpan(p, len).ToArray());
            p += len;
            var map = ReadMsgPackMap(plain);
            list.Add(new IdxEntry(
                (string)map["fileName"],
                Convert.ToInt32(map["size"]),
                Convert.ToInt32(map["index"])));
        }
        return list;
    }

    static int CmdPack(string[] args)
    {
        if (args.Length < 3) return Fail("pack requires <input_dir> <out_bin> <out_idx>");
        string inputDir = Path.GetFullPath(args[0]);
        string outBin = Path.GetFullPath(args[1]);
        string outIdx = Path.GetFullPath(args[2]);
        string prefix = DefaultPrefix;
        bool recursive = false;
        for (int i = 3; i < args.Length; i++)
        {
            if (args[i] == "--prefix" && i + 1 < args.Length) { prefix = args[++i]; continue; }
            if (args[i] == "--recursive") { recursive = true; continue; }
            return Fail("unknown option " + args[i]);
        }
        if (!prefix.EndsWith("/")) prefix += "/";
        if (!Directory.Exists(inputDir)) throw new DirectoryNotFoundException(inputDir);

        var files = Directory.EnumerateFiles(inputDir, "*", recursive ? SearchOption.AllDirectories : SearchOption.TopDirectoryOnly)
            .Where(f => !Path.GetFileName(f).StartsWith("."))
            .OrderBy(f => f, StringComparer.OrdinalIgnoreCase)
            .ToList();
        if (files.Count == 0) throw new InvalidOperationException("no files in " + inputDir);

        Directory.CreateDirectory(Path.GetDirectoryName(outBin)!);
        Directory.CreateDirectory(Path.GetDirectoryName(outIdx)!);

        using var binFs = File.Create(outBin);
        using var binBw = new BinaryWriter(binFs);
        using var idxFs = File.Create(outIdx);
        using var idxBw = new BinaryWriter(idxFs);

        foreach (var path in files)
        {
            byte[] fileBytes = File.ReadAllBytes(path);
            byte[] binPlain = PrepareBinPlain(fileBytes); // MsgPack string
            byte[] enc = AesEncrypt(binPlain);
            int index = checked((int)binFs.Position + 4);
            int size = enc.Length;

            binBw.Write(size);
            binBw.Write(enc);

            string rel = Path.GetRelativePath(inputDir, path).Replace('\\', '/');
            string virtualName = prefix + rel;
            byte[] idxEnc = AesEncrypt(PackInfoMsgPack(virtualName, size, index));
            idxBw.Write(idxEnc.Length);
            idxBw.Write(idxEnc);

            bool wrapped = !LooksLikeMsgPackString(fileBytes);
            Console.WriteLine($"PACK {virtualName} file={fileBytes.Length} msgpack={(wrapped ? "wrap" : "keep")} plain={binPlain.Length} enc={size} index={index}");
        }
        Console.WriteLine($"OK packed {files.Count} files -> {outBin} + {outIdx}");
        return 0;
    }

    static int CmdUnpack(string[] args)
    {
        if (args.Length < 3) return Fail("unpack requires <bin> <idx> <output_dir>");
        string binPath = Path.GetFullPath(args[0]);
        string idxPath = Path.GetFullPath(args[1]);
        string outDir = Path.GetFullPath(args[2]);
        bool keepRaw = args.Any(a => a == "--raw"); // keep MsgPack wrapper for debugging
        Directory.CreateDirectory(outDir);

        var entries = ReadIdx(idxPath);
        byte[] bin = File.ReadAllBytes(binPath);
        foreach (var e in entries)
        {
            if (e.Index < 0 || e.Index + e.Size > bin.Length)
                throw new InvalidDataException($"bad range {e.FileName}");
            int prefix = BitConverter.ToInt32(bin, e.Index - 4);
            if (prefix != e.Size)
                Console.WriteLine($"WARN size-prefix mismatch {e.FileName}: {prefix} vs {e.Size}");

            byte[] enc = new byte[e.Size];
            Buffer.BlockCopy(bin, e.Index, enc, 0, e.Size);
            byte[] mp = AesDecrypt(enc);

            string rel = e.FileName.TrimStart('/', '\\').Replace('/', Path.DirectorySeparatorChar);
            string outPath = Path.Combine(outDir, rel);
            Directory.CreateDirectory(Path.GetDirectoryName(outPath)!);

            if (keepRaw)
            {
                File.WriteAllBytes(outPath, mp);
                Console.WriteLine($"UNPACK-RAW {e.FileName} -> {outPath} bytes={mp.Length}");
            }
            else
            {
                string text = MsgPackDecodeString(mp);
                // write UTF-8 without BOM
                File.WriteAllBytes(outPath, Encoding.UTF8.GetBytes(text));
                Console.WriteLine($"UNPACK {e.FileName} -> {outPath} text={text.Length}");
            }
        }
        Console.WriteLine($"OK unpacked {entries.Count} files -> {outDir}");
        return 0;
    }

    static int CmdList(string[] args)
    {
        if (args.Length < 2) return Fail("list requires <bin> <idx>");
        var entries = ReadIdx(Path.GetFullPath(args[1]));
        long binLen = new FileInfo(Path.GetFullPath(args[0])).Length;
        Console.WriteLine($"# {entries.Count} entries, bin={binLen}");
        foreach (var e in entries)
            Console.WriteLine($"{e.FileName}\tsize={e.Size}\tindex={e.Index}");
        return 0;
    }

    static int CmdVerify(string[] args)
    {
        if (args.Length < 2) return Fail("verify requires <bin> <idx>");
        string binPath = Path.GetFullPath(args[0]);
        string idxPath = Path.GetFullPath(args[1]);
        byte[] origBin = File.ReadAllBytes(binPath);
        byte[] origIdx = File.ReadAllBytes(idxPath);
        var entries = ReadIdx(idxPath);

        using var newBin = new MemoryStream();
        using var newIdx = new MemoryStream();
        using var binBw = new BinaryWriter(newBin);
        using var idxBw = new BinaryWriter(newIdx);

        foreach (var e in entries)
        {
            byte[] encIn = new byte[e.Size];
            Buffer.BlockCopy(origBin, e.Index, encIn, 0, e.Size);
            byte[] mp = AesDecrypt(encIn);              // MsgPack string bytes
            string text = MsgPackDecodeString(mp);      // unwrap
            byte[] mp2 = MsgPackEncodeString(text);     // rewrap
            if (!mp.AsSpan().SequenceEqual(mp2))
                Console.WriteLine($"WARN msgpack rewrap differs {e.FileName} {mp.Length}->{mp2.Length}");

            byte[] enc = AesEncrypt(mp2);
            int index = checked((int)newBin.Position + 4);
            int size = enc.Length;
            binBw.Write(size);
            binBw.Write(enc);
            byte[] idxEnc = AesEncrypt(PackInfoMsgPack(e.FileName, size, index));
            idxBw.Write(idxEnc.Length);
            idxBw.Write(idxEnc);
        }

        bool binOk = newBin.ToArray().AsSpan().SequenceEqual(origBin);
        bool idxOk = newIdx.ToArray().AsSpan().SequenceEqual(origIdx);
        Console.WriteLine($"bin identical: {binOk} ({newBin.Length}/{origBin.Length})");
        Console.WriteLine($"idx identical: {idxOk} ({newIdx.Length}/{origIdx.Length})");

        // also simulate game path: decrypt first entry as string and print head
        if (entries.Count > 0)
        {
            var e0 = entries[0];
            byte[] enc = new byte[e0.Size];
            Buffer.BlockCopy(origBin, e0.Index, enc, 0, e0.Size);
            string s = MsgPackDecodeString(AesDecrypt(enc));
            string head = s.Length > 60 ? s.Substring(0, 60).Replace('\n', ' ').Replace('\r', ' ') : s;
            Console.WriteLine($"sample {e0.FileName}: \"{head}...\"");
        }
        return binOk && idxOk ? 0 : 3;
    }

    static int CmdSelfTest()
    {
        // empty -> one PKCS block
        byte[] c = AesEncrypt(Array.Empty<byte>());
        if (Convert.ToHexString(c) != "813DB2C521651F5156A88BE5BA72BE3A")
            throw new Exception("aes empty vector fail " + Convert.ToHexString(c));
        if (!AesDecrypt(c).SequenceEqual(Array.Empty<byte>())) throw new Exception("aes empty roundtrip");

        c = AesEncrypt(Encoding.UTF8.GetBytes("hello"));
        if (Convert.ToHexString(c) != "FEBEA783624DD97F2960DECA287A5F80")
            throw new Exception("aes hello vector fail");

        // msgpack wrap/unwrap
        string sample = "//====\nline2\n";
        byte[] mp = MsgPackEncodeString(sample);
        if (MsgPackDecodeString(mp) != sample) throw new Exception("msgpack string fail");

        // packinfo
        byte[] pi = PackInfoMsgPack("/scripts/A01.snr", 14560, 4);
        var map = ReadMsgPackMap(pi);
        if ((string)map["fileName"] != "/scripts/A01.snr") throw new Exception("packinfo name");
        if (Convert.ToInt32(map["size"]) != 14560) throw new Exception("packinfo size");
        if (Convert.ToInt32(map["index"]) != 4) throw new Exception("packinfo index");

        // prepare: raw text wraps; already wrapped keeps
        byte[] raw = Encoding.UTF8.GetBytes("abc");
        byte[] prep = PrepareBinPlain(raw);
        if (!LooksLikeMsgPackString(prep) || MsgPackDecodeString(prep) != "abc") throw new Exception("prepare wrap");
        if (!PrepareBinPlain(prep).SequenceEqual(prep)) throw new Exception("prepare keep");

        Console.WriteLine("selftest OK");
        return 0;
    }
}
