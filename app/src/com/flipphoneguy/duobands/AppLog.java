package com.flipphoneguy.duobands;

import android.content.Context;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Timestamped log in app data (files/f21duo.log), mirrored to the screen. Every line is fsynced, since the flash ends in a hard reboot. */
public final class AppLog {

    public interface Listener {
        void onLine(String line);
    }

    private final File file;
    private final Listener listener;
    private final SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);

    public AppLog(Context ctx, Listener listener) {
        this.file = file(ctx);
        this.listener = listener;
    }

    public static File file(Context ctx) {
        return new File(ctx.getFilesDir(), "f21duo.log");
    }

    public String path() { return file.getAbsolutePath(); }

    public synchronized void line(String msg) {
        String l = fmt.format(new Date()) + "  " + msg;
        try (FileOutputStream out = new FileOutputStream(file, true)) {
            out.write((l + "\n").getBytes("UTF-8"));
            out.getFD().sync();
        } catch (IOException ignored) {}
        if (listener != null) listener.onLine(l);
    }
}
