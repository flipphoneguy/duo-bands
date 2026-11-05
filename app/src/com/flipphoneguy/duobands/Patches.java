package com.flipphoneguy.duobands;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/** Byte ranges to overlay on each partition image while it streams to the eMMC. */
public final class Patches {

    private static final class Range {
        final long off;
        final byte[] data;
        Range(long off, byte[] data) { this.off = off; this.data = data; }
    }

    private final List<List<Range>> parts = new ArrayList<>();

    public Patches(int count) {
        for (int i = 0; i < count; i++) parts.add(new ArrayList<Range>());
    }

    public void add(int part, long off, byte[] data) throws IOException {
        if (off < 0 || off + data.length > Layout.bytes(part)) throw new IOException("patch outside " + Layout.NAMES[part]);
        for (Range r : parts.get(part)) {
            if (off < r.off + r.data.length && r.off < off + data.length) throw new IOException("overlapping patches in " + Layout.NAMES[part]);
        }
        parts.get(part).add(new Range(off, data));
    }

    /** Overlays the patches that fall inside buf[0..n), which holds bytes pos..pos+n of the partition. */
    public void apply(int part, long pos, byte[] buf, int n) {
        for (Range r : parts.get(part)) {
            long lo = Math.max(pos, r.off), hi = Math.min(pos + n, r.off + r.data.length);
            if (lo < hi) System.arraycopy(r.data, (int) (lo - r.off), buf, (int) (lo - pos), (int) (hi - lo));
        }
    }

    public int size(int part) { return parts.get(part).size(); }
}
