package com.flipphoneguy.duobands;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** `su -c` helpers, and `su -mm` for the flash shell that needs the mount-master SELinux domain to open mmcblk0. */
public final class RootRunner {

    private RootRunner() {}

    public static boolean hasRoot() {
        try {
            Result r = run("id");
            return r.exit == 0 && r.stdout.contains("uid=0");
        } catch (IOException | InterruptedException e) {
            return false;
        }
    }

    public static Result run(String cmd) throws IOException, InterruptedException {
        Process p = Runtime.getRuntime().exec(new String[]{"su", "-c", cmd});
        p.getOutputStream().close();
        Pump err = drainLater(p.getErrorStream());
        String stdout = new String(drain(p.getInputStream()));
        int exit = p.waitFor();
        try { err.join(2000); } catch (InterruptedException ignored) {}
        return new Result(exit, stdout, errText(err));
    }

    /** Raw bytes of a file readable only by root, or null if it doesn't exist. */
    public static byte[] readFile(String path) throws IOException, InterruptedException {
        Result t = run("[ -f '" + path + "' ] && echo yes");
        if (!t.stdout.trim().equals("yes")) return null;
        Process p = Runtime.getRuntime().exec(new String[]{"su", "-c", "cat '" + path + "'"});
        p.getOutputStream().close();
        Pump err = drainLater(p.getErrorStream());
        byte[] data = drain(p.getInputStream());
        int exit = p.waitFor();
        try { err.join(2000); } catch (InterruptedException ignored) {}
        if (exit != 0) throw new IOException("cat " + path + " exited " + exit + ": " + errText(err));
        return data;
    }

    /** SHA-256 of the first `bytes` bytes of a block device. */
    public static String sha256Partition(String device, long bytes) throws IOException, InterruptedException {
        MessageDigest md;
        try {
            md = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
        Process p = Runtime.getRuntime().exec(new String[]{"su", "-c",
            "dd if=" + device + " bs=1048576 count=" + (bytes / 1048576) + " 2>/dev/null"});
        p.getOutputStream().close();
        try (InputStream in = p.getInputStream()) {
            byte[] buf = new byte[1024 * 1024];
            long remaining = bytes;
            int n;
            while (remaining > 0 && (n = in.read(buf, 0, (int) Math.min(buf.length, remaining))) > 0) {
                md.update(buf, 0, n);
                remaining -= n;
            }
            if (remaining != 0) throw new IOException("short read hashing " + device);
        }
        if (p.waitFor() != 0) throw new IOException("dd " + device + " failed");
        return hex(md.digest());
    }

    public static Process execMountMasterShell(String cmd) throws IOException {
        return Runtime.getRuntime().exec(new String[]{"su", "-mm", "-c", cmd});
    }

    public static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    private static byte[] drain(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16 * 1024];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toByteArray();
    }

    /** Drains a stream on its own thread (so a chatty su can't fill the pipe and block stdout) and keeps what it read. */
    static final class Pump extends Thread {
        private final InputStream in;
        private final ByteArrayOutputStream buf = new ByteArrayOutputStream();
        Pump(InputStream in) { this.in = in; setDaemon(true); }
        @Override public void run() {
            try {
                byte[] b = new byte[4096];
                int n;
                while ((n = in.read(b)) > 0) {
                    synchronized (buf) { buf.write(b, 0, n); }
                }
            } catch (IOException ignored) {}
        }
        String text() { synchronized (buf) { return buf.toString(); } }
    }

    private static Pump drainLater(InputStream in) {
        Pump p = new Pump(in);
        p.start();
        return p;
    }

    private static String errText(Pump p) { return p.text(); }

    public static final class Result {
        public final int exit;
        public final String stdout;
        public final String stderr;
        Result(int exit, String stdout, String stderr) {
            this.exit = exit;
            this.stdout = stdout;
            this.stderr = stderr;
        }
    }
}
