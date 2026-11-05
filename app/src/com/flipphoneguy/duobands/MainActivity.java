package com.flipphoneguy.duobands;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;

/** One screen: check the phone, confirm, install, reboot. */
public class MainActivity extends Activity {

    private TextView status, logView;
    private ScrollView logScroll;
    private Button install;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private volatile boolean running;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_main);
        status = findViewById(R.id.status);
        logView = findViewById(R.id.log);
        logScroll = findViewById(R.id.log_scroll);
        install = findViewById(R.id.install);
        install.setEnabled(false);
        install.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { confirm(); }
        });
        showOldLog();
        check();
    }

    private void showOldLog() {
        File f = AppLog.file(this);
        if (!f.isFile()) return;
        try (FileInputStream in = new FileInputStream(f)) {
            byte[] data = new byte[(int) f.length()];
            int off = 0, n;
            while (off < data.length && (n = in.read(data, off, data.length - off)) > 0) off += n;
            logView.setText(new String(data, 0, off, "UTF-8"));
            scrollLog();
        } catch (IOException ignored) {}
    }

    private void check() {
        setStatus("Checking this phone...");
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    if (!RootRunner.hasRoot()) {
                        setStatus("Root access is needed. Grant it in Magisk and open the app again.");
                        return;
                    }
                    String bad = Layout.check();
                    if (bad != null) {
                        setStatus("This phone doesn't have the Qin F21 Pro (before v3) partition layout, so nothing will be written.\n\n" + bad);
                        return;
                    }
                    JSONObject layout = layout();
                    String want = layout.getJSONArray("partitions").getJSONObject(0).getString("sha256");
                    final boolean done = want.equals(RootRunner.sha256Partition("/dev/block/by-name/md1img_a", Layout.bytes(0)));
                    setStatus(done ? "The duo-band firmware is already installed. Installing again redoes everything, including the VoLTE setup."
                                   : "Ready. This installs the EU + US band modem firmware.");
                    ui.post(new Runnable() {
                        @Override public void run() {
                            install.setText(done ? "Install again" : "Install");
                            install.setEnabled(true);
                            install.requestFocus();
                        }
                    });
                } catch (Exception e) {
                    setStatus("Could not check this phone: " + e.getMessage());
                }
            }
        }).start();
    }

    private void confirm() {
        if (running) return;
        Intent bat = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
        int level = bat == null ? -1 : bat.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) * 100 / Math.max(1, bat.getIntExtra(BatteryManager.EXTRA_SCALE, 100));
        boolean charging = bat != null && bat.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) != 0;
        if (level >= 0 && level < 30 && !charging) {
            new AlertDialog.Builder(this).setMessage("The battery is at " + level + "%. Charge it to at least 30% or plug it in first.")
                .setPositiveButton("OK", null).show();
            return;
        }
        new AlertDialog.Builder(this)
            .setTitle("Install duo bands?")
            .setMessage("This writes the duo-band modem firmware (md1img, nvdata, nvram) to this phone, keeps its own IMEI, Bluetooth and Wi-Fi addresses, sets up VoLTE for Israeli networks, and reboots.\n\nIt takes a few minutes. Don't touch the phone until it reboots.")
            .setPositiveButton("Install", new android.content.DialogInterface.OnClickListener() {
                @Override public void onClick(android.content.DialogInterface d, int w) { run(); }
            })
            .setNegativeButton("Cancel", null)
            .show();
    }

    private void run() {
        running = true;
        install.setEnabled(false);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        logView.setText("");
        final AppLog log = new AppLog(this, new AppLog.Listener() {
            @Override public void onLine(final String line) {
                ui.post(new Runnable() {
                    @Override public void run() {
                        logView.append(line + "\n");
                        scrollLog();
                    }
                });
            }
        });
        final Flasher.Progress progress = new Flasher.Progress() {
            @Override public void step(String message) { setStatus(message); }
        };
        new Thread(new Runnable() {
            @Override public void run() {
                boolean writing = false;
                try {
                    log.line("=== install started ===");
                    log.line("phone: " + Build.MANUFACTURER + " " + Build.MODEL + ", " + Build.DISPLAY);
                    log.line("modem before: " + RootRunner.run("getprop gsm.version.baseband").stdout.trim());
                    String bad = Layout.check();
                    if (bad != null) throw new IOException(bad);
                    log.line("partition layout ok");
                    JSONObject layout = layout();
                    setStatus("Checking the bundled firmware...");
                    Flasher.verify(MainActivity.this, layout, log, progress);
                    setStatus("Reading this phone's IMEI and addresses...");
                    Patches patches = Identity.prepare(MainActivity.this, layout, log);
                    if (getIntent().getBooleanExtra("dry_run", false)) {
                        // test only (adb shell am start -n com.flipphoneguy.duobands/.MainActivity --ez dry_run true): nothing is written or changed
                        Flasher.dryRun(MainActivity.this, patches, getExternalFilesDir("dryrun"), log, progress);
                        log.line("dry run done, nothing was written");
                        setStatus("Dry run done. Nothing was written.");
                        return;
                    }
                    setStatus("Setting up VoLTE...");
                    Volte.apply(log);
                    writing = true;
                    Flasher.flash(MainActivity.this, patches, log, progress);
                    log.line("done, the phone reboots now");
                    setStatus("Done. The phone reboots now.");
                } catch (Exception e) {
                    log.line("FAILED: " + e.getMessage());
                    setStatus((writing ? "The install stopped while writing. Check the log, and don't reboot before asking for help if it says a partition was written.\n\n"
                                       : "The install stopped before writing anything.\n\n") + e.getMessage());
                    ui.post(new Runnable() {
                        @Override public void run() {
                            running = false;
                            install.setEnabled(true);
                            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                        }
                    });
                }
            }
        }).start();
    }

    private JSONObject layout() throws Exception {
        return new JSONObject(new String(Identity.asset(this, "layout.json"), "UTF-8"));
    }

    private void setStatus(final String s) {
        ui.post(new Runnable() {
            @Override public void run() { status.setText(s); }
        });
    }

    private void scrollLog() {
        logScroll.post(new Runnable() {
            @Override public void run() { logScroll.fullScroll(View.FOCUS_DOWN); }
        });
    }
}
