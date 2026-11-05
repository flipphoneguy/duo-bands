package com.flipphoneguy.duobands;

import java.io.IOException;

/**
 * The F21 Pro (pre-v3) partitions this app writes, and the check that this phone really has them where we expect.
 *
 * The flash writes raw offsets on mmcblk0, so the app only runs when every partition's by-name link resolves to mmcblk0 and its start and size match exactly. That rules out the M5, the F21 v3 and anything else.
 */
public final class Layout {

    private Layout() {}

    public static final String MMCBLK0 = "/dev/block/mmcblk0";

    /** Order of the partitions in the bundled tar and in the flash script. */
    public static final String[] FILES = { "md1img_a.bin", "nvdata.bin", "nvram.bin" };
    public static final String[] NAMES = { "md1img_a", "nvdata", "nvram" };

    // start and size in 512-byte sectors on mmcblk0
    static final long[] START = { 573440L, 111680L, 419840L };
    static final long[] SECTORS = { 204800L, 131072L, 131072L };

    public static long bytes(int i) { return SECTORS[i] * 512; }
    public static long seek4k(int i) { return START[i] / 8; }
    public static long count4k(int i) { return SECTORS[i] / 8; }

    /** Sector inside the band-region WP set; CMD29 here clears the power-on write protect (nvram's start, as in Bands Swap). */
    public static final long WP_UNLOCK_SECTOR = 419840L;

    /** Returns null when the layout matches, or a description of the first mismatch. */
    public static String check() throws IOException, InterruptedException {
        StringBuilder cmd = new StringBuilder();
        for (String p : NAMES) {
            cmd.append("d=$(readlink -f /dev/block/by-name/").append(p).append("); n=${d##*/}; ")
               .append("echo ").append(p).append(" $d $(cat /sys/class/block/$n/start) $(cat /sys/class/block/$n/size); ");
        }
        RootRunner.Result r = RootRunner.run(cmd.toString());
        if (r.exit != 0) return "could not read the partition table: " + r.stderr.trim();
        String[] lines = r.stdout.trim().split("\n");
        if (lines.length != NAMES.length) return "unexpected partition listing:\n" + r.stdout;
        for (int i = 0; i < NAMES.length; i++) {
            String[] f = lines[i].trim().split("\\s+");
            if (f.length != 4 || !f[0].equals(NAMES[i])) return "unexpected partition listing: " + lines[i];
            if (!f[1].startsWith(MMCBLK0 + "p")) return NAMES[i] + " is " + f[1] + ", not on " + MMCBLK0;
            long start, size;
            try {
                start = Long.parseLong(f[2]);
                size = Long.parseLong(f[3]);
            } catch (NumberFormatException e) {
                return "unexpected partition listing: " + lines[i];
            }
            if (start != START[i] || size != SECTORS[i]) {
                return NAMES[i] + " is at sector " + start + " (" + size + " sectors), expected " + START[i] + " (" + SECTORS[i] + ")";
            }
        }
        return null;
    }
}
