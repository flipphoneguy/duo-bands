package com.flipphoneguy.duobands;

import java.io.IOException;

/**
 * The Android-side half of VoLTE on Israeli networks, as in The-curious's no-root patch: turn MediaTek's dynamic IMS switch off, and add the IMS APN for the Israeli operators that need it. The modem-side half (the operator table) is already in the bundled md1img.
 *
 * Both are region-neutral: the switch only stops a vendor allow-list from blocking VoLTE, and the APN rows only match Israeli SIMs.
 */
public final class Volte {

    private Volte() {}

    static final String[] MNC = { "01", "02", "07", "09", "19" };

    public static void apply(AppLog log) throws IOException, InterruptedException {
        RootRunner.Result r = RootRunner.run("setprop persist.vendor.mtk_dynamic_ims_switch 0 && getprop persist.vendor.mtk_dynamic_ims_switch");
        if (r.exit != 0 || !r.stdout.trim().equals("0")) throw new IOException("could not set persist.vendor.mtk_dynamic_ims_switch: " + r.stderr.trim());
        log.line("persist.vendor.mtk_dynamic_ims_switch = 0");
        for (String mnc : MNC) {
            String numeric = "425" + mnc;
            RootRunner.Result q = RootRunner.run("content query --uri content://telephony/carriers --projection _id"
                + " --where \"numeric='" + numeric + "' AND type LIKE '%ims%'\"");
            if (q.stdout.contains("Row:")) {
                log.line("IMS APN for " + numeric + ": already there");
                continue;
            }
            RootRunner.Result ins = RootRunner.run("content insert --uri content://telephony/carriers"
                + " --bind name:s:IMS --bind apn:s:ims --bind type:s:ims"
                + " --bind mcc:s:425 --bind mnc:s:" + mnc + " --bind numeric:s:" + numeric
                + " --bind protocol:s:IPV4V6 --bind roaming_protocol:s:IPV4V6 --bind carrier_enabled:i:1");
            if (ins.exit != 0) throw new IOException("could not add the IMS APN for " + numeric + ": " + ins.stderr.trim());
            log.line("IMS APN for " + numeric + ": added");
        }
    }
}
