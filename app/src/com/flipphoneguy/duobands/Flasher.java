package com.flipphoneguy.duobands;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.tukaani.xz.XZInputStream;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.concurrent.TimeUnit;

/**
 * Verifies the bundled images, then live-flashes them the way Bands Swap does (docs/live_band_swap_solution.md in f21_bands_swap): CMD0 reinit, CMD6 USR_WP, CMD8, CMD29 clear write protect, CMD31 check, dd each image from the shell's stdin onto mmcblk0, read back, sysrq-b.
 */
public final class Flasher {

    public interface Progress {
        void step(String message);
    }

    private Flasher() {}

    static final String ASSET = "f21duo.tar.xz";

    /** Decompresses the whole bundle once and checks names, order, sizes and SHA-256 against layout.json. Writes nothing. */
    public static void verify(Context ctx, JSONObject layout, AppLog log, Progress progress) throws IOException, JSONException {
        JSONArray parts = layout.getJSONArray("partitions");
        try (InputStream xz = open(ctx)) {
            for (int i = 0; i < Layout.FILES.length; i++) {
                JSONObject p = parts.getJSONObject(i);
                TarStream.Entry e = TarStream.readHeader(xz);
                if (e == null || !e.name.equals(Layout.FILES[i]) || !e.name.equals(p.getString("name"))) {
                    throw new IOException("bundle entry " + i + " is " + (e == null ? "missing" : e.name) + ", expected " + Layout.FILES[i]);
                }
                if (e.size != Layout.bytes(i) || e.size != p.getLong("size")) throw new IOException(e.name + " is " + e.size + " bytes, expected " + Layout.bytes(i));
                MessageDigest md = sha256();
                copy(xz, null, e.size, md, null, i, progress, "Checking " + e.name);
                TarStream.skipFully(xz, TarStream.padAfter(e.size));
                String got = RootRunner.hex(md.digest());
                if (!got.equals(p.getString("sha256"))) throw new IOException(e.name + " is damaged (sha256 " + got + ")");
                log.line("bundle " + e.name + " ok (sha256 " + got + ")");
            }
        }
    }

    /** Streams the bundle onto the eMMC with the patches applied. Ends in a hard reboot when it works. */
    public static void flash(Context ctx, Patches patches, AppLog log, Progress progress) throws IOException, InterruptedException {
        File probe = stageProbe(ctx);
        File script = writeScript(ctx, probe, log.path());
        log.line("unlocking eMMC write protect and writing " + Layout.FILES.length + " partitions");
        Process shell = RootRunner.execMountMasterShell("sh '" + script.getAbsolutePath() + "'");
        RootRunner.Pump err = new RootRunner.Pump(shell.getErrorStream());
        err.start();
        new RootRunner.Pump(shell.getInputStream()).start();

        IOException failed = null;
        try (InputStream xz = open(ctx); OutputStream stdin = shell.getOutputStream()) {
            for (int i = 0; i < Layout.FILES.length; i++) {
                TarStream.Entry e = TarStream.readHeader(xz);
                if (e == null || !e.name.equals(Layout.FILES[i]) || e.size != Layout.bytes(i)) throw new IOException("bundle changed since it was checked");
                MessageDigest md = sha256();
                copy(xz, stdin, e.size, md, patches, i, progress, "Writing " + Layout.NAMES[i]);
                TarStream.skipFully(xz, TarStream.padAfter(e.size));
                stdin.flush();
                log.line("sent " + Layout.NAMES[i] + " (" + patches.size(i) + " patches), sha256 " + RootRunner.hex(md.digest()));
            }
        } catch (IOException e) {
            failed = e;
        }
        // the script reads all three back and logs their hashes before it reboots, so give it time
        boolean exited = shell.waitFor(90, TimeUnit.SECONDS);
        if (failed != null || (exited && shell.exitValue() != 0)) {
            String msg = (failed != null ? failed.getMessage() : "flash script exited " + shell.exitValue());
            String stderr = err.text().trim();
            throw new IOException(stderr.isEmpty() ? msg : msg + "\n" + stderr);
        }
        progress.step("Rebooting");
    }

    /** Test path: writes the patched nvdata and nvram images to `dir` instead of the eMMC, so they can be checked offline. */
    public static void dryRun(Context ctx, Patches patches, File dir, AppLog log, Progress progress) throws IOException {
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("cannot create " + dir);
        try (InputStream xz = open(ctx)) {
            for (int i = 0; i < Layout.FILES.length; i++) {
                TarStream.Entry e = TarStream.readHeader(xz);
                if (e == null || !e.name.equals(Layout.FILES[i])) throw new IOException("unexpected bundle entry");
                MessageDigest md = sha256();
                if (i == 0) {
                    copy(xz, null, e.size, md, patches, i, progress, "Dry run " + Layout.NAMES[i]);
                } else {
                    try (OutputStream out = new FileOutputStream(new File(dir, e.name))) {
                        copy(xz, out, e.size, md, patches, i, progress, "Dry run " + Layout.NAMES[i]);
                    }
                }
                TarStream.skipFully(xz, TarStream.padAfter(e.size));
                log.line("dry run " + Layout.NAMES[i] + " (" + patches.size(i) + " patches), sha256 " + RootRunner.hex(md.digest()) + (i == 0 ? "" : ", saved"));
            }
        }
    }

    private static void copy(InputStream in, OutputStream out, long bytes, MessageDigest md, Patches patches, int part,
                             Progress progress, String label) throws IOException {
        byte[] buf = new byte[1024 * 1024];
        long pos = 0, end = bytes, lastMb = -1;
        while (pos < end) {
            int n = in.read(buf, 0, (int) Math.min(buf.length, end - pos));
            if (n < 0) throw new IOException("bundle ended early");
            if (patches != null) patches.apply(part, pos, buf, n);
            md.update(buf, 0, n);
            if (out != null) out.write(buf, 0, n);
            pos += n;
            long mb = pos / (1024 * 1024);
            if (mb / 8 != lastMb / 8 || pos == end) {
                progress.step(label + "  " + mb + " / " + (end / (1024 * 1024)) + " MB");
                lastMb = mb;
            }
        }
    }

    private static InputStream open(Context ctx) throws IOException {
        return new XZInputStream(new BufferedInputStream(ctx.getAssets().open(ASSET), 1 << 20));
    }

    private static MessageDigest sha256() throws IOException {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }

    private static File stageProbe(Context ctx) throws IOException {
        File out = new File(ctx.getFilesDir(), "mmc_probe");
        byte[] data = Identity.asset(ctx, "mmc_probe");
        try (FileOutputStream o = new FileOutputStream(out)) {
            o.write(data);
        }
        if (!out.setExecutable(true, false)) throw new IOException("cannot mark mmc_probe executable");
        return out;
    }

    private static File writeScript(Context ctx, File probe, String logPath) throws IOException {
        StringBuilder s = new StringBuilder();
        s.append("#!/system/bin/sh\n");
        s.append("set -e\n");
        s.append("PROBE='").append(probe.getAbsolutePath()).append("'\n");
        s.append("DEV='").append(Layout.MMCBLK0).append("'\n");
        s.append("LOG='").append(logPath).append("'\n");
        s.append("log() { echo \"$(date '+%Y-%m-%d %H:%M:%S')  $*\" >> \"$LOG\"; }\n");
        s.append("sync\n");
        s.append("\"$PROBE\" \"$DEV\" reinit\n");
        s.append("\"$PROBE\" \"$DEV\" switch 1 171 0x10\n");
        s.append("\"$PROBE\" \"$DEV\" ext_csd > /dev/null\n");
        s.append("\"$PROBE\" \"$DEV\" clear_wp ").append(Layout.WP_UNLOCK_SECTOR).append("\n");
        s.append("WP_LINE=\"\"\n");
        s.append("i=0\n");
        s.append("while [ $i -lt 5 ]; do\n");
        s.append("  WP_LINE=$(\"$PROBE\" \"$DEV\" read_wp ").append(Layout.WP_UNLOCK_SECTOR).append(" 2>/dev/null | grep '^WP @' || true)\n");
        s.append("  [ -n \"$WP_LINE\" ] && break\n");
        s.append("  sleep 1\n");
        s.append("  i=$((i + 1))\n");
        s.append("done\n");
        s.append("case \"$WP_LINE\" in\n");
        s.append("  *\"00 00 00 00 00 00 00 00\"*) log 'write protect cleared' ;;\n");
        s.append("  \"\") log 'write protect check gave no answer, continuing on the CMD29 result' ;;\n");
        s.append("  *) log \"write protect did not clear: $WP_LINE\"; echo 'Write protect did not clear. Power the phone fully off, wait 30 seconds, power on and try again. Nothing was written.' >&2; exit 1 ;;\n");
        s.append("esac\n");
        for (int i = 0; i < Layout.FILES.length; i++) {
            // dd reads its partition from the stdin Java writes; toybox on the F21 has no iflag=fullblock, full 4 KiB reads hold because Java keeps the pipe full
            s.append("dd of=\"$DEV\" bs=4096 seek=").append(Layout.seek4k(i)).append(" count=").append(Layout.count4k(i)).append(" conv=notrunc 2>/dev/null\n");
            s.append("log 'wrote ").append(Layout.NAMES[i]).append("'\n");
        }
        s.append("sync\n");
        // read back through mmcblk0, the device that was written: the by-name node of the mounted nvdata can still hold stale cached blocks
        for (int i = 0; i < Layout.FILES.length; i++) {
            s.append("log \"read back ").append(Layout.NAMES[i]).append(", sha256 $(dd if=\"$DEV\" bs=4096 skip=").append(Layout.seek4k(i))
             .append(" count=").append(Layout.count4k(i)).append(" 2>/dev/null | sha256sum | cut -d' ' -f1)\"\n");
        }
        s.append("log 'rebooting'\n");
        s.append("sync\n");
        s.append("sleep 2\n");
        s.append("sync\n");
        s.append("echo 1 > /proc/sys/kernel/sysrq\n");
        s.append("echo b > /proc/sysrq-trigger\n");
        File out = new File(ctx.getFilesDir(), "flash.sh");
        try (FileWriter w = new FileWriter(out)) {
            w.write(s.toString());
        }
        return out;
    }
}
