# Blank-stick rehearsal and dedicated-stick attachment

**Howard runs this procedure only in an approved window.** The first rehearsal uses a separate, otherwise blank, formatted USB stick with one small, ordinary public marker file. Leave the identity stick unplugged for that entire rehearsal. The only public readout is pass/refuse and the reviewed source hash. Keep mount IDs, device numbers, bus IDs, account details and paths on the host.

## Establish that this route is available

Use USB/IP attachment for a USB flash drive. Microsoft documents a limitation on directly attaching flash drives with `wsl --mount`. In the private account, verify the distro is WSL2 and its running kernel supports USB/IP **and USB mass storage**. Check that the approved usbipd-win version supports the commands below (Microsoft's procedure assumes 5.0.0 or later). A device visible to `lsusb` still needs a Linux block device and a supported filesystem. If prerequisites, firewall scope or Windows automount, indexing and backup controls are unresolved, pause before inserting an identity. Installing software, enabling services or changing firewall policy needs a separate operator decision. [Microsoft disk attachment](https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk) · [Microsoft USB/IP instructions](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)

USB/IP shares the attached device with running WSL2 distributions. The private distro name does not isolate it by itself. Establish C01–C06, log out other interactive accounts, and ensure other WSL2 distros and Docker Desktop are stopped for the window. `wsl --list --running` covers the calling account only. Account for other accounts separately. Check that the USB/IP service can be reached only by the intended host/WSL client; its default firewall rule may allow LAN clients. Stop if exclusive custody or network scope cannot be established. Windows administrators remain trusted. [Microsoft USB/IP instructions](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)

## Rehearse with the public marker

1. In the private account, keep the private WSL distro running. Identify the blank stick by comparing `usbipd list` before and after insertion. In a separately elevated Windows terminal, bind that bus ID with `usbipd bind --busid <BUSID>`. Confirm its shared state. From the private account, attach it with `usbipd attach --wsl --busid <BUSID>`. Confirm attached state and identify the device in the intended Linux distro with `lsusb` and `lsblk -o NAME,TYPE,TRAN,SIZE,FSTYPE,MAJ:MIN,MOUNTPOINTS`. Verify a single expected partition by size, type and insertion change. Stop on an ambiguous disk, existing writable mount, unexpected filesystem or missing block device. Use only an existing public marker on a stick prepared by Howard. [usbipd-win WSL support](https://github.com/dorssel/usbipd-win/wiki/WSL-support)
2. Use an empty owner-only mount directory beneath the private account's Linux filesystem. In that same distro, mount the identified partition read-only. For an existing ext4 volume, use `sudo mount -t ext4 -o ro,noload,nosuid,nodev,noexec "$PARTITION" "$MOUNTPOINT"`. For an existing FAT volume, use `sudo mount -t vfat -o "ro,nosuid,nodev,noexec,uid=$(id -u),gid=$(id -g),umask=077" "$PARTITION" "$MOUNTPOINT"`. These variables denote operator-local values. Require the operator to be able to open the public marker as a standard user. Other filesystems require review of their read-only mount procedure. Do not format, repair or change permissions on an identity stick.
3. Run the following in the unprivileged operator's shell from the reviewed checkout, with the public marker as stdin. It does not read marker contents. It checks the descriptor's access mode, size, mount ID and device against the same broker functions used in the live route. The private shell variable `MARKER` identifies the ordinary public file. Use the **same mount namespace** as the harness, outside Docker.

   ```sh
   PYTHONPATH=src:. python3 -B -c 'import sys; from tools.intcalc_h3_usb_channel import mount; from tools.intcalc_h3_custody import mounted; from tools.public_age_canary import check_usb_mount; i,d=mount(0); check_usb_mount(i,d); sys.exit(0 if mounted(d,i) else 2)' < "$MARKER"
   ```

   Exit 0 is required. With `findmnt --target "$MARKER" -n -o ID,MAJ:MIN,FSTYPE,OPTIONS`, keep the ID and major:minor locally for the removal check. Verify the mount is read-only with nosuid, nodev and noexec. Rely on the actual block-device mount. A Windows drive-letter mapping, copied file, VHD or bind mount cannot establish this custody route.
4. Close the descriptor, leave the mount directory in every shell, and run `sudo umount "$MOUNTPOINT"`. In Windows use `usbipd detach --busid <BUSID>`, then in the elevated terminal `usbipd unbind --busid <BUSID>`. Check device state, physically remove the stick and recheck `lsblk`. In Linux verify absence using the previously recorded values:

   ```sh
   PYTHONPATH=src:. python3 -B -c 'import sys; from tools.intcalc_h3_custody import mounted; sys.exit(2 if mounted(sys.argv[2],int(sys.argv[1])) else 0)' "$MOUNT_ID" "$MAJOR_MINOR"
   ```

   Exit 0 is required: neither identifier may remain visible. An incomplete detach, busy mount or any ambiguity stops the rehearsal. Do not use a lazy unmount. Complete postflight and retain only the redacted observation publicly.

## Later dedicated-stick window

Proceed only after Howard reviews the blank-stick result and separately authorizes the exact live canary. Re-establish custody. Encrypt the public fixture with the USB unplugged. At the harness insertion prompt repeat the reviewed attachment using the real dedicated medium and fresh IDs. Enter the mount ID and major:minor observed from the same namespace. The existing sender supplies the already-open read-only identity fd to the pinned age child. Neither the harness nor its approval receives an identity path. Only Howard performs that existing private sender step; suppress path-bearing history and terminal capture. Do not inspect, copy or export the identity. After the decryptor exits, repeat unmount, detach, unbind, physical removal and absence checks before entering the broker's removal confirmation. Perform postflight before writing the receipt. Any refusal consumes the attempt once the operation directory exists.

The blank-stick result proves device visibility, standard-user descriptor access and removal for its tested route. The actual identity, decryptor exit and public roundtrip are established only by the separately approved canary on the dedicated stick.
