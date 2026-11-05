package com.flipphoneguy.duobands;

import java.io.IOException;
import java.io.InputStream;

/** Minimal USTAR reader for the bundled image tar (from Bands Swap). 512-byte header, body, zero pad to 512, two zero blocks at the end. */
public final class TarStream {

    private static final int BLOCK = 512;

    private TarStream() {}

    public static final class Entry {
        public final String name;
        public final long size;
        Entry(String name, long size) { this.name = name; this.size = size; }
    }

    /** Reads a header block. Returns null at archive end. */
    public static Entry readHeader(InputStream in) throws IOException {
        byte[] hdr = new byte[BLOCK];
        if (!readFully(in, hdr)) return null;
        boolean allZero = true;
        for (byte b : hdr) {
            if (b != 0) { allZero = false; break; }
        }
        if (allZero) return null;
        int nameLen = 0;
        while (nameLen < 100 && hdr[nameLen] != 0) nameLen++;
        return new Entry(new String(hdr, 0, nameLen, "UTF-8"), parseOctal(hdr, 124, 12));
    }

    public static long padAfter(long size) {
        return (BLOCK - (size % BLOCK)) % BLOCK;
    }

    public static void skipFully(InputStream in, long count) throws IOException {
        long remaining = count;
        byte[] junk = new byte[BLOCK];
        while (remaining > 0) {
            int n = in.read(junk, 0, (int) Math.min(junk.length, remaining));
            if (n < 0) throw new IOException("Unexpected EOF skipping tar pad");
            remaining -= n;
        }
    }

    private static boolean readFully(InputStream in, byte[] buf) throws IOException {
        int total = 0;
        while (total < buf.length) {
            int n = in.read(buf, total, buf.length - total);
            if (n < 0) {
                if (total == 0) return false;
                throw new IOException("Unexpected EOF mid-header");
            }
            total += n;
        }
        return true;
    }

    private static long parseOctal(byte[] buf, int off, int len) {
        long val = 0;
        for (int i = off; i < off + len; i++) {
            int c = buf[i] & 0xff;
            if (c == 0 || c == ' ') continue;
            if (c < '0' || c > '7') break;
            val = (val * 8) + (c - '0');
        }
        return val;
    }
}
