package com.flipphoneguy.duobands;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Keeps this phone's own IMEI, Bluetooth MAC and Wi-Fi MAC across the flash.
 *
 * The bundled nvdata carries placeholder identity files. Each one also has a copy inside the NVRAM backup (AllFile, checksummed by AllMap), which lives both in nvdata and in the nvram partition. This reads the phone's current files and turns them into byte patches over the image streams: the live file blocks in nvdata, the AllFile/AllMap blocks in nvdata, and AllMap/AllFile in nvram, with the backup checksum recomputed.
 */
public final class Identity {

    private Identity() {}

    static final String NVDATA = "/mnt/vendor/nvdata/";
    static final String[] FILES = { "md/NVRAM/NVD_IMEI/LD0B_001", "APCFG/APRDEB/BT_Addr", "APCFG/APRDEB/WIFI" };
    static final String[] LABELS = { "IMEI", "Bluetooth MAC", "Wi-Fi MAC" };

    /** Patches per partition index (see Layout.FILES). */
    public static Patches prepare(Context ctx, JSONObject layout, AppLog log) throws IOException, InterruptedException, JSONException {
        int bs = layout.getInt("block_size");
        JSONObject files = layout.getJSONObject("files");
        byte[] allFile = asset(ctx, "AllFile.bin");
        byte[] allMap = asset(ctx, "AllMap.bin");
        if (le32(allMap, 0) != checksum(allFile)) throw new IOException("bundled NVRAM backup checksum does not match");

        Patches p = new Patches(Layout.FILES.length);
        int kept = 0;
        for (int i = 0; i < FILES.length; i++) {
            JSONObject f = files.getJSONObject(FILES[i]);
            int size = f.getInt("size");
            byte[] mine = RootRunner.readFile(NVDATA + FILES[i]);
            if (mine == null) {
                log.line(LABELS[i] + ": not found on this phone, using the placeholder");
                continue;
            }
            if (mine.length != size) {
                log.line(LABELS[i] + ": this phone's file is " + mine.length + " bytes, expected " + size + ", using the placeholder");
                continue;
            }
            if (i == 0 && !(mine[0] == 'L' && mine[1] == 'D' && mine[2] == 'I' && mine[3] == 0)) {
                log.line(LABELS[i] + ": this phone's file is not an NVRAM record, using the placeholder");
                continue;
            }
            blocks(p, 1, f.getJSONArray("blocks"), bs, mine);
            System.arraycopy(mine, 0, allFile, f.getInt("allfile_off"), size);
            log.line(LABELS[i] + ": keeping this phone's own");
            kept++;
        }
        int sum = checksum(allFile);
        allMap[0] = (byte) sum; allMap[1] = (byte) (sum >> 8); allMap[2] = (byte) (sum >> 16); allMap[3] = (byte) (sum >> 24);
        blocks(p, 1, files.getJSONObject("AllFile").getJSONArray("blocks"), bs, allFile);
        blocks(p, 1, files.getJSONObject("AllMap").getJSONArray("blocks"), bs, allMap);
        p.add(2, layout.getLong("nvram_allmap_off"), allMap);
        p.add(2, layout.getLong("nvram_allfile_off"), allFile);
        log.line("NVRAM backup checksum " + String.format("%08x", sum) + " (" + kept + " of " + FILES.length + " identity files carried over)");
        return p;
    }

    // writes data across a file's blocks in file order; the last block keeps its slack bytes
    private static void blocks(Patches p, int part, JSONArray blocks, int bs, byte[] data) throws JSONException, IOException {
        if (blocks.length() != (data.length + bs - 1) / bs) throw new IOException("block map does not fit the file size");
        for (int b = 0; b < blocks.length(); b++) {
            int off = b * bs, len = Math.min(bs, data.length - off);
            byte[] chunk = new byte[len];
            System.arraycopy(data, off, chunk, 0, len);
            p.add(part, blocks.getLong(b) * bs, chunk);
        }
    }

    /** MediaTek's NVRAM backup checksum: XOR even words, add odd words, add a zero-padded tail, XOR with the length. */
    static int checksum(byte[] af) {
        int s = 0, n = af.length / 4;
        for (int i = 0; i < n; i++) {
            int w = le32(af, i * 4);
            s = (i % 2 == 0) ? (s ^ w) : (s + w);
        }
        int tail = af.length - n * 4;
        if (tail > 0) {
            int w = 0;
            for (int k = 0; k < tail; k++) w |= (af[n * 4 + k] & 0xff) << (8 * k);
            s += w;
        }
        return s ^ af.length;
    }

    static int le32(byte[] b, int o) {
        return (b[o] & 0xff) | (b[o + 1] & 0xff) << 8 | (b[o + 2] & 0xff) << 16 | (b[o + 3] & 0xff) << 24;
    }

    static byte[] asset(Context ctx, String name) throws IOException {
        try (InputStream in = ctx.getAssets().open(name)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }
}
