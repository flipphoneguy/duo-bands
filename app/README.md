# F21 Duo Bands (app)

A one-button installer for the F21 duo firmware. It writes `md1img_a`, `nvdata` and `nvram` from the running, rooted phone, keeps the phone's own IMEI, Bluetooth MAC and Wi-Fi MAC, sets up VoLTE for Israeli networks, and reboots.

Qin F21 Pro before v3 only, and it needs root (Magisk). On any other phone it refuses to write anything.

## What it does

1. **Checks the phone.** Root, then the partition table: `md1img_a`, `nvdata` and `nvram` must resolve to `/dev/block/mmcblk0` at the exact F21 Pro sectors (573440, 111680, 419840) and sizes. The flash writes raw `mmcblk0` offsets, so this check is what keeps it off the M5, the F21 v3 and everything else. It also hashes `md1img_a` to tell whether the duo firmware is already installed.
2. **Checks the battery.** At least 30%, or plugged in.
3. **Checks the bundle.** Decompresses `assets/f21duo.tar.xz` once and compares each image's name, order, size and SHA-256 with `assets/layout.json`. Nothing is written unless all three match.
4. **Keeps the phone's identity.** Reads `NVD_IMEI/LD0B_001`, `APCFG/APRDEB/BT_Addr` and `APCFG/APRDEB/WIFI` from `/mnt/vendor/nvdata` and turns them into byte patches over the images: the files' own blocks in nvdata, their copies in the NVRAM backup (`AllFile`, in nvdata and in the nvram partition), and the backup checksum in `AllMap`. A file that's missing or has an unexpected size keeps the bundled placeholder, and the log says so.
5. **VoLTE.** Sets `persist.vendor.mtk_dynamic_ims_switch 0` and adds an `ims` APN for 425-01, 02, 07, 09 and 19 where one is missing (`docs/06-f21-volte.md`).
6. **Flashes.** The live-flash sequence from [f21_bands_swap](https://github.com/flipphoneguy/f21_bands_swap) (`docs/live_band_swap_solution.md` there): CMD0 reinit, CMD6 user write-protect switch, CMD8, CMD29 clear write protect, CMD31 check, all through its `mmc_probe` under `su -mm`. Then `dd` writes each image from the shell's stdin while the app streams the bundle with the patches applied. If the write protect doesn't clear, it stops before writing.
7. **Reads back and reboots.** The flash script reads all three partitions back through `mmcblk0` and logs their SHA-256 next to the hashes of what was sent, then syncs and reboots with sysrq.

Every step goes to `files/f21duo.log` in the app's data, with timestamps, and shows on screen. The log stays after the reboot, so opening the app again shows the whole run.

The app makes no backups. Back up `md1img_a`, `nvdata` and `nvram` yourself first if you want a way back.

### Dry run

```sh
adb shell am start -n com.flipphoneguy.duobands/.MainActivity --ez dry_run true
```

Then press Install. It runs steps 1 to 4 for real and saves the patched `nvdata.bin` and `nvram.bin` to `Android/data/com.flipphoneguy.duobands/files/dryrun/` instead of writing anything, so they can be checked offline (`e2fsck`, `debugfs`, the backup checksum).

## Building

The bundle comes from the F21 duo build (see the main README). With `tmp/f21_duo/` built and verified:

```sh
python3 scripts/build_app_assets.py   # writes app/assets/f21duo.tar.xz, layout.json, AllFile.bin, AllMap.bin
cd app && ./build.sh                  # F21DuoBands.apk
```

`build.sh` is the same Termux/SDK setup as f21_bands_swap: `aapt2`, `ecj` or `javac`, `d8`, `apksigner`, `~/.android/android.jar`, `~/.android/framework-res.apk` and a debug keystore. It downloads xz-java into `libs/` on the first build. `tools/mmc_probe.c` is the source of `assets/mmc_probe`, from f21_bands_swap.
